"""Real NESSO/PSICHIC -> ESMFold2 -> geometry -> MPNN -> later request checks."""
import argparse, json, os, sys
from pathlib import Path
from types import SimpleNamespace

def run(config):
    cfg=json.loads(Path(config).read_text());out=Path(cfg['output']);root=Path(cfg['root']);scripts=Path(cfg['adapter']).parent
    os.environ.update(NANOHUNTER_ROOT=str(root), PYTORCH_ENABLE_MPS_FALLBACK='0', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', IPROTEINSTUDIO_LIVE_RESULTS_ROOT=str(out))
    sys.path[:0]=[str(scripts/'nise'),str(scripts)]
    from runtime import atomic
    from contract import normalize
    from esmfold_runtime import ESMBackend
    from ligand_atoms import resolve
    import yaml
    data=yaml.safe_load((Path(cfg['inputs'])/'c_biotin.yaml').read_text())
    seq=data['sequences'][0]['protein']['sequence'];smiles=data['sequences'][1]['ligand']['smiles']
    manifest=resolve(smiles);smiles=manifest['smiles_used']
    rows=[]
    for model,engine in [('fast','nesso'),('full','psichic')]:
        directory=out/(model+'-'+engine);directory.mkdir()
        settings=normalize(dict(smiles=smiles, scoring_mode='screening',screening_engine=engine,
            folding_engine='esmfold2-'+model+'-mlx', nesso_screen=True,phase0_nesso_screen=True,
            phase0_seqs1=2,phase0_nesso_refine_top_k=2, nesso_top_k=2, beam=1, trajectories=1,
            scheduler='resident',exposure_mode='biotin-carboxamide-v1',geometry_workers=2))
        backend=ESMBackend(root,directory,settings,scripts);backend.ligand_manifest=manifest
        args=SimpleNamespace(seed=42,use_potentials=True,boltz_phase='structure',skip_nesso=True,
            fs_distance=10.0,ala_budget=2,gly_budget=0)
        try:
            # A real score before folding, with both screening contracts exercised.
            selected=backend.screen_initial({'test0':seq},smiles,directory/'screen',{'test0':'L0'},'refinement')
            scores={name:backend.objective_score(name) for name in selected}
            folded=backend.fold(selected,smiles,directory/'fold',args,pocket={'binder':'B','contacts':[['B',manifest['atoms'][0]['name']]],'max_distance':6.0})
            session=backend.esm_worker;pid=session.process.pid
            checks=backend.check_atom_requirements_batch(folded)
            pred=folded['test0']
            sampled=backend.design(pred.pdb,directory/'mpnn',1,smiles,args,.5,.7,42,'all',False)
            later=backend.fold({'later0':sampled[0]},smiles,directory/'later',args)
            if backend.esm_worker is not session or session.process.pid!=pid:raise RuntimeError('ESMFold2 model was reloaded between producer requests')
            resumed=backend.fold({'later0':sampled[0]},smiles,directory/'later',args)
            if resumed['later0'].pdb!=later['later0'].pdb:raise RuntimeError('NISE checkpoint reuse failed')
            if any(p.pbind is not None for p in [*folded.values(),*later.values()]):raise RuntimeError('Unexpected affinity score')
            # Independent CPU atom-map and geometry checks run on both folds.
            later_checks=backend.check_atom_requirements_batch(later)
            rows.append(dict(model=model,objective=engine,scores=scores,first_geometry=checks,later_geometry=later_checks,
                atom_checks=backend.atom_checks,mpnn_sequences=sampled,session=str(session.queue),pid=pid,model_load_count=session.ready['model_load_count'],checkpoint_reused=True))
            atomic(out/'route_progress.json',dict(rows=rows))
        finally:backend.close()
    # Full's declared optional MSA support uses the cached real alignment.
    import subprocess
    full_input=out/'full_msa';full_input.mkdir()
    monomer=yaml.safe_load((Path(cfg['inputs'])/'a_monomer.yaml').read_text())
    monomer['sequences'][0]['protein']['msa']=str(out/'msa/smt3.a3m')
    (full_input/'with_msa.yaml').write_text(yaml.safe_dump(monomer))
    with (out/'full_msa.log').open('w') as log:
        subprocess.run([cfg['python'],cfg['adapter'],'--inputs',str(full_input),'--output',str(out/'full_msa_output'),
            '--nanohunter-root',str(root),'--model','full'],check=True,stdout=log,stderr=subprocess.STDOUT)
    atomic(out/'completed.json',dict(routes=rows,full_cached_msa=True))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);a=p.parse_args();run(a.config)
