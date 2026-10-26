"""Use the pinned upstream BeamSearchStrategy, changing only its score provider.

All branch integration, completed rollouts, stable selection, and continuation
are upstream code. Score cache is keyed by rollout identity AND sequence.
"""
import json, os, sys, subprocess, time, uuid
from pathlib import Path
from .contract import atomic as save, sha, seal as seal_files, verify

def verified(directory):
    marker = Path(directory) / 'completed.json'
    return verify(marker) if marker.exists() else None

def seal(directory, result, relative_root=None):
    directory = Path(directory)
    oracles = []
    if (directory / 'rows.json').is_file():
        for row in json.loads((directory / 'rows.json').read_text()).values(): oracles += row['receipts']
    seal_files(directory / 'completed.json', result,
               [p for p in directory.rglob('*') if p.is_file() and p != directory / 'completed.json'] + oracles,
               relative_root=relative_root)

def audit_rows(output, rows):
    root = Path(output).resolve()
    for row in rows.values():
        for receipt in row['receipts']:
            path = Path(receipt).resolve()
            if root not in path.parents: raise ValueError('Oracle receipt escaped its campaign.')
            verify(path, relative_root=root)

def policies(steps, ligand):
    rewards = {'boltz.pbind': {'weight': 1.0}, 'boltz.ligand_plddt': {'weight': .01}} if ligand else {'protein.ipsae_min': {'weight': 1.0}}
    return {str(s): dict(metrics=['boltz'], use_clean_prediction=False, rewards=rewards) for s in steps}


def compose(cfg, root, dest):
    from hydra import initialize_config_dir, compose as hydra_compose
    from omegaconf import OmegaConf
    os.environ['DATA_PATH']=cfg['upstream']
    with initialize_config_dir(config_dir=str(Path(cfg['upstream'])/'configs'),version_base='1.3'):
        native=hydra_compose(config_name='inference',overrides=[
            'inputs='+root['input'], 'out_dir='+str(dest),
            'hf_ckpt_path='+cfg['native_model'], '~metrics', 'compile_lengths=null',
            'num_workers=0', 'batch_size=1','num_replicates=1',
            'seed='+str(root['generation_seed']), 'recycle_strategy=medium/midpeak',
            'generation.args.partial_trajectory_fraction_steps='+str(cfg['fraction'])])
    # The subclass provides the oracle rather than Hydra's AF2/AF3 providers.
    native.search.checkpoints=None
    return native


def batch_for(native):
    from rfproteina.generate import get_dataset_from_cfg
    from rfproteina.datapipes.collate import collate_batch
    dataset=get_dataset_from_cfg(native,0)
    if len(dataset)!=1: raise RuntimeError('Expected exactly one source backbone')
    return collate_batch([dataset[0]],schema='rfproteina.datapipes.schema.proteina.ProteinaDataSample')


class Scorer:
    def __init__(self,cfg):
        self.cfg=cfg; self.q=Path(cfg['output'])/'score_sessions'/uuid.uuid4().hex
        (self.q/'requests').mkdir(parents=True); (self.q/'responses').mkdir()
        save(self.q/'config.json',{**cfg,'score_queue':str(self.q)})
        self.log=(self.q/'worker.log').open('w')
        self.proc=subprocess.Popen([cfg['python'],'-B',str(Path(__file__).resolve().parents[1]/'rfd4_cli.py'),'oracle','--root',os.environ['NANOHUNTER_ROOT'],'--config',str(self.q/'config.json'),'--output',cfg['output']],stdout=self.log,stderr=subprocess.STDOUT)
        self.wait(self.q/'ready.json')
    def wait(self,path):
        deadline=time.monotonic()+7200
        while not path.exists():
            if self.proc.poll() is not None: raise RuntimeError('Boltz scorer exited: '+str(self.q))
            if time.monotonic()>deadline: raise RuntimeError('Boltz scoring timeout: '+str(self.q))
            time.sleep(.2)
        return json.loads(path.read_text())
    def run(self,key,structures):
        name=uuid.uuid4().hex+'.json'
        save(self.q/'requests'/name,{'key':key,'structures':structures})
        result=self.wait(self.q/'responses'/name)
        if not result['ok']: raise RuntimeError(result['error'])
        return result['rows']
    def close(self):
        save(self.q/'stop.json',{})
        try: self.proc.wait(timeout=60)
        except subprocess.TimeoutExpired: self.proc.terminate();self.proc.wait(timeout=30)
        self.log.close()


def sequence_of(array):
    import biotite.structure as bs
    from biotite.sequence import ProteinSequence
    protein = array[bs.filter_amino_acids(array)]
    sequences = {}
    for chain in sorted(set(protein.chain_id)):
        _, names = bs.get_residues(protein[protein.chain_id == chain])
        sequence = ''.join(ProteinSequence.convert_letter_3to1(x) for x in names)
        if not sequence or set(sequence)-set('ACDEFGHIKLMNPQRSTVWY'):
            raise ValueError('Invalid generated native sequence')
        sequences[str(chain)] = sequence
    if not sequences: raise ValueError('Native rollout contains no protein.')
    return sequences


def write_array(path,array):
    import biotite.structure.io.pdbx as pdbx
    cif=pdbx.CIFFile();pdbx.set_structure(cif,array);cif.write(path)


def strategy(cfg, scorer, directory):
    import torch
    from rfproteina.search.beam_search import BeamSearchStrategy
    class BoltzBeam(BeamSearchStrategy):
        def configure_metrics(self,model):
            for s,p in self.checkpoints.items():
                if p.get('use_clean_prediction') or p['metrics']!=['boltz']:
                    raise ValueError('Boltz requires completed rollouts')
        def _compute_rewards(self,model,atom_array_results,reward_model,output_base_dir=None,
                             design_ids=None,run_oracles=True,metric_names=None):
            if not run_oracles or metric_names!=['boltz']: raise ValueError('Missing Boltz rollout scoring')
            ids=design_ids or [r['example_id'] for r in atom_array_results]
            seqs={key:sequence_of(r['generated_atom_array']) for key,r in zip(ids,atom_array_results,strict=True)}
            if len(seqs)!=len(ids): raise ValueError('Duplicate rollout identity')
            key=ids[0].rsplit('_',1)[0]
            unit=directory/'scores'/key
            cached=verified(unit)
            if cached:
                if cached['sequences']!=seqs: raise RuntimeError('Replay changed native rollout sequences')
                rows=json.loads((unit/'rows.json').read_text())
            else:
                from .budget import checkpoint
                checkpoint()
                unit.mkdir(parents=True,exist_ok=True)
                for name,result in zip(ids,atom_array_results,strict=True):
                    write_array(unit/(name+'.cif'),result['generated_atom_array'])
                # Synchronize RFD4 before dispatching Boltz; no overlapping inference.
                torch.mps.synchronize()
                rows=scorer.run(directory.name+'_'+key,{name:str(unit/(name+'.cif')) for name in ids})
                save(unit/'rows.json',rows)
                seal(unit,{'sequences':seqs,'count':len(seqs)}, cfg['output'])
            audit_rows(cfg['output'],rows)
            metrics=[];rewards=[]
            for name in ids:
                m=rows[name]['metrics']
                reward=reward_model.aggregate_metrics_output(m)
                if abs(reward-rows[name]['score'])>1e-7:
                    raise RuntimeError('Native reward aggregation changed score')
                metrics.append({**m,'search.reward':reward});rewards.append(reward)
            save(directory/'progress.json',{'checkpoint':key,'scored':len(ids),'max_reward':max(rewards)})
            return torch.tensor(rewards,device=model.device,dtype=torch.float32),metrics
    return BoltzBeam(checkpoints=policies(cfg['checkpoints'], cfg['settings']['task']=='ligand'),beam_width=cfg['beam_width'],
                    n_branch=cfg['n_branch'],save_rollouts=True,save_states=True)


def run_family(cfg,root,model,scorer):
    import torch, random, numpy as np
    from lightning.fabric.utilities.apply_func import move_data_to_device
    from rfproteina.generate import load_ckpt_n_configure_inference
    directory=Path(cfg['output'])/'families'/root['family']
    done=verified(directory/'final')
    if done:
        for key,digest in done['score_receipts'].items():
            unit=directory/'scores'/key
            if sha(unit/'completed.json')!=digest:raise RuntimeError('Changed search score receipt')
            verified(unit)
            audit_rows(cfg['output'],json.loads((unit/'rows.json').read_text()))
        return done
    native=compose(cfg,root,directory)
    model=load_ckpt_n_configure_inference(native,model=model)
    torch.manual_seed(root['generation_seed']);random.seed(root['generation_seed']);np.random.seed(root['generation_seed'])
    model.inference_seed=root['generation_seed']
    batch=batch_for(native)
    batch=move_data_to_device(batch,torch.device('mps'))
    model._current_output_base_dir=directory/'designs';model._current_output_suffix=''
    model.search_strategy=strategy(cfg,scorer,directory)
    started=time.monotonic()
    with torch.inference_mode(),torch.autocast('mps',dtype=torch.bfloat16):
        results=model.predict_step(batch,0)
    # Upstream finishes the two last survivors once, without further selection.
    # Score these finished designs for reporting using the same Boltz oracle.
    unscored=[r for r in results if r.get('reward') is None]
    if unscored:
        from rfproteina.rewards.reward_model import RewardModel
        reward=RewardModel(policies([1], cfg['settings']['task']=='ligand')['1']['rewards'])
        values,_=model.search_strategy._compute_rewards(model,unscored,reward,
            design_ids=[r['example_id'] for r in unscored],metric_names=['boltz'])
        for r,v in zip(unscored,values.tolist(),strict=True):r['reward']=v
    final=directory/'final'; final.mkdir(parents=True,exist_ok=True)
    feedback = {}
    for score_path in (directory/'scores').glob('*/rows.json'):
        verify(score_path.parent/'completed.json')
        feedback.update(json.loads(score_path.read_text()))
    records=[]
    for i,result in enumerate(results):
        name=result['example_id']; seq=sequence_of(result['generated_atom_array'])
        write_array(final/(name+'.cif'),result['generated_atom_array'])
        oracle = feedback[name]
        records.append(dict(id=name, family=root['family'], sequences=seq, structure=str(final/(name+'.cif')),
                            structure_sha256=sha(final/(name+'.cif')), score=result.get('reward'),
                            metrics=oracle['metrics'], oracle_structure=oracle['structure'],
                            oracle_structure_sha256=oracle['structure_sha256'], score_receipts=oracle['receipts'],
                            score_role='native_rollout_feedback', engine='RFD4 native beam',
                            **({'ipsae_min':result.get('reward')} if cfg['settings']['task']!='ligand' else {})))
    expected=cfg['beam_width']*(cfg['n_branch']*len(cfg['checkpoints'])+int(cfg['checkpoints'][-1] < round(60*cfg['fraction'])))
    if len(records)!=expected: raise RuntimeError(f'Expected all {expected} scored rollouts; got {len(records)}')
    save(final/'results.json',records)
    result={'family':root['family'],'outputs':len(records),'seconds':time.monotonic()-started,
            'score_receipts':{p.parent.name:sha(p) for p in (directory/'scores').glob('*/completed.json')}}
    seal(final,result)
    return result


def main(path, first_only=False):
    from .prepare import runtime
    from .contract import atomic, prediction_budget
    config = json.loads(Path(path).read_text())
    output = Path(config['output'])
    if not (output/'studio_job.json').is_file(): raise ValueError('Native RFD4 requires a managed job.')
    rt = runtime(Path(os.environ['NANOHUNTER_ROOT']))
    cfg = dict(config, upstream=str(rt/'sources/RFD4-Proteina'), native_model=str(Path(os.environ['NANOHUNTER_ROOT'])/'models/rfd4/native'),
               fraction=config['settings']['native_partial_fraction'], checkpoints=config['settings']['native_checkpoints'],
               beam_width=config['settings']['native_beam_width'], n_branch=config['settings']['native_branches'],
               python=str(Path(os.environ['NANOHUNTER_ROOT'])/('venvs/NanoHunter_boltz/bin/python' if config['settings']['task']=='ligand' or config['settings']['predictor']=='boltz' else 'venvs/NanoHunter_esmfold2/bin/python')))
    os.environ.update(DEBUG='false', PROJECT_ROOT=cfg['upstream'], DATA_PATH=cfg['upstream'], PYTORCH_ENABLE_MPS_FALLBACK='0', HF_HUB_OFFLINE='1')
    import torch
    from rfproteina.proteina import Proteina
    if not torch.backends.mps.is_available(): raise RuntimeError('Native RFD4 requires Apple MPS.')
    torch.set_num_threads(4)
    model=Proteina.from_pretrained(cfg['native_model'],local_files_only=True,
        nn_overrides={'tri_mult_backend':'torch','attention_type':'torch'}).to('mps').eval().requires_grad_(False)
    scorer=Scorer(cfg)
    starts=json.loads((output/'generated.json').read_text())
    if first_only: starts=starts[:1]
    records=[]
    try:
        for index, start in enumerate(starts):
            root=dict(family=start['family'],input=start.get('native_structure', start['structure']),generation_seed=start['seed'])
            result=run_family(cfg,root,model,scorer)
            if index==0 and run_family(cfg,root,model,scorer)!=result: raise ValueError('Native family replay changed.')
            records += json.loads((output/'families'/root['family']/'final/results.json').read_text())
            atomic(output/'results.json',records)
            atomic(output/'progress.json',dict(stage='native-search',completed=index+1,total=len(starts)))
    finally: scorer.close()
    expected = prediction_budget(dict(cfg['settings'], count=len(starts)))
    if len(records)!=expected: raise ValueError('Incomplete native rollout budget.')
    if first_only: return
    seal_files(output/'native_search_completed.json',dict(families=len(starts),rollouts=len(records)),
        [output/'results.json']+list((output/'families').glob('*/final/completed.json'))
        +list((output/'families').glob('*/scores/*/completed.json')))
