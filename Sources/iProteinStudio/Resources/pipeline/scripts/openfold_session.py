"""OpenFold residency ported from the qualified prediction-scale worker.

One model; sequential single-query requests preserve the validated zero-worker
feature RNG. Receipts include input dependencies and every seed/sample artifact.
"""
import json,os,shutil,subprocess,sys,time,uuid
from pathlib import Path
from prediction_resume import atomic,digest,input_identity
from prediction_profiles import profile, normalize

class OpenFoldSession:
    def __init__(self, config):
        from resident_predictor import require_mps
        self.config=config; self.root=Path(config['root']); self.torch=require_mps()
        self.settings=normalize(config['prediction_settings'])['openfold-3-mlx'] if config.get('prediction_settings') is not None else profile('openfold-3-mlx')
        self.seeds=[int(x) for x in str(config.get('seed','42')).split(',')]
        self.samples=int(config.get('samples',1))
        if not self.seeds or self.samples<1:raise ValueError('OpenFold needs seeds and positive samples')
        if config.get('use_template'):raise ValueError('OpenFold template guidance is not supported')
        if config.get('engine_args'):raise ValueError('Resident OpenFold uses explicit profiles; unsupported extra CLI flags')
        self.work=Path(config.get('queue') or config['work_dir'])/'openfold_session'
        self.work.mkdir(parents=True,exist_ok=True)
        os.environ['OPENFOLD_CACHE']=str(self.root/'models/openfold3')
        from openfold3.run_openfold import _torch_gpu_setup
        _torch_gpu_setup()
        import yaml
        from openfold3.entry_points.experiment_runner import InferenceExperimentRunner
        from openfold3.entry_points.validator import InferenceExperimentConfig
        from openfold_runner_yaml import GPU
        from inference_optimizations import OpenFoldPreparation,ResidentModels
        ckpt=Path(os.environ.get('OPENFOLD_CHECKPOINT_PATH',self.root/'models/openfold3/of3_ft3_v1.pt'))
        self.identity=dict(schema=1,checkpoint=digest(ckpt),adapter={name:digest(Path(__file__).with_name(name)) for name in ('openfold_session.py','openfold_query_json.py','openfold_mps.py','openfold_positions.py','inference_optimizations.py','openfold_runner_yaml.py')},settings=self.settings,seeds=self.seeds,samples=self.samples)
        ec=InferenceExperimentConfig(inference_ckpt_path=ckpt,**yaml.safe_load(GPU))
        self.runner=InferenceExperimentRunner(ec,self.samples,len(self.seeds),False,False,self.work/'predictions')
        shared=self.runner.model_config.architecture.shared
        shared.num_recycles=self.settings['recycles'];shared.diffusion.no_full_rollout_steps=self.settings['diffusion_steps']
        self.runner.seeds=self.seeds
        self.preparation=OpenFoldPreparation(InferenceExperimentRunner)
        self.residency=ResidentModels()
        try:
            self.runner.setup();self.model=self.runner.lightning_module.model
            self.residency.add(self.runner.lightning_module)
        except BaseException:
            self.close();raise
        self.model_load_count=1;self.device='mps'

    def close(self):
        self.preparation.close();self.residency.close()

    def predict(self, source, output, expected):
        import yaml
        from openfold_mps import prepare_query
        from openfold3.projects.of3_all_atom.config.inference_query_format import InferenceQuerySet
        from storage_policy import relative_symlink
        from validate_prediction_geometry import inspect_geometry
        from prediction_profiles import record
        source,output=Path(source),Path(output);paths=sorted(source.glob('*.yaml'))
        if len(paths)!=expected:raise ValueError('OpenFold directory cardinality mismatch')
        output.mkdir(parents=True,exist_ok=True);record(output,'openfold-3-mlx',self.settings)
        for index,path in enumerate(paths,1):
            leaf=output/path.stem;leaf.mkdir(parents=True,exist_ok=True);done=leaf/'openfold_complete.json'
            identity=dict(model=self.identity,input=input_identity(path))
            reused=False
            if done.exists():
                saved=json.loads(done.read_text())
                if saved['identity']!=identity:raise ValueError('OpenFold saved input/settings changed: '+str(path))
                if not saved['files'] or any(not Path(p).is_file() or digest(Path(p))!=h for p,h in saved['files'].items()):
                    raise ValueError('OpenFold saved artifacts changed: '+str(done))
                reused=True
            else:
                # Keep incomplete attempts, but never mix their files into a retry.
                if any(leaf.iterdir()):
                    archive=self.work/'interrupted'/uuid.uuid4().hex
                    archive.parent.mkdir(parents=True,exist_ok=True)
                    shutil.move(str(leaf),archive);leaf.mkdir()
                # Never let upstream skip an incomplete previous query by existence.
                qname='q_'+uuid.uuid4().hex;attempt=self.work/'requests'/qname;attempt.mkdir(parents=True)
                data=yaml.safe_load(path.read_text());binder=next((x['protein']['sequence'] for x in data['sequences'] if x.get('protein',{}).get('id')=='A'),'')
                binder=''.join(c if c in 'ACDEFGHIKLMNPQRSTVWY' else 'A' for c in binder)
                query=attempt/'query.json'
                cmd=[sys.executable,str(Path(__file__).with_name('openfold_query_json.py')),str(path),binder,qname,str(query),'','',str(self.seeds[0])]
                result=subprocess.run(cmd,check=True,capture_output=True,text=True)
                if result.stdout.strip()!='false':raise ValueError('OpenFold resident input requires explicit cached or empty MSA; no implicit search')
                query=prepare_query(query,attempt,self.settings)
                payload=json.loads(query.read_text());payload['seeds']=self.seeds;atomic(query,payload)
                for key in ('lightning_data_module','data_module_config'):self.runner.__dict__.pop(key,None)
                self.runner.seeds=self.seeds
                self.torch.manual_seed(self.seeds[0]);started=time.perf_counter()
                self.runner.run(InferenceQuerySet.from_json(query))
                self.torch.mps.synchronize()
                native=self.work/'predictions'/qname;files=[];models=[];confs=[]
                for seed in self.seeds:
                    src=native/f'seed_{seed}';dst=leaf/f'seed_{seed}';dst.mkdir(exist_ok=True)
                    structures=sorted(src.glob('*_model.cif'));confidence=sorted(src.glob('*_confidences_aggregated.json'))
                    if len(structures)!=self.samples or len(confidence)!=self.samples:raise ValueError('OpenFold output cardinality mismatch: '+str(src))
                    for p in structures:
                        if inspect_geometry(p)['errors']:raise ValueError('Invalid OpenFold coordinates: '+str(p))
                    for p in confidence:
                        value=json.loads(p.read_text());json.dumps(value,allow_nan=False)
                        if not value:raise ValueError('Empty OpenFold confidence')
                    for p in src.iterdir():
                        if p.is_file():
                            # Publish real files in the caller's output tree. Native
                            # callbacks retain links; app scanners see one copy.
                            destination=dst/p.name
                            shutil.move(str(p),destination)
                            relative_symlink(destination,p,replace=True)
                            files.append(destination)
                    models+= [dst/p.name for p in structures];confs += [dst/p.name for p in confidence]
                pred=leaf/'pred_min';pred.mkdir(exist_ok=True)
                relative_symlink(models[0],pred/'model_0.cif',replace=True);relative_symlink(confs[0],pred/'confidence.json',replace=True)
                if input_identity(path)!=identity['input']:raise ValueError('OpenFold input changed during prediction')
                atomic(done,dict(identity=identity,files={str(p.absolute()):digest(p) for p in files+[pred/'model_0.cif',pred/'confidence.json']},seconds=time.perf_counter()-started,pid=os.getpid(),model_load_count=1))
                from live_structure_events import invalidate,publish,pairs_in
                for seed in self.seeds:
                    invalidate(native/f'seed_{seed}')
                    published=leaf/f'seed_{seed}'
                    publish(published,path.stem,'openfold-3-mlx',pairs_in(published,'openfold-3-mlx',path.stem))
            if getattr(self,'publish_iterative_results',False):
                from live_iterative_results import LiveIterativeResults
                LiveIterativeResults(source,getattr(self,'iterative_binder_chain','A')).publish_structure(path.stem,leaf/'pred_min/model_0.cif',leaf/'pred_min/confidence.json','openfold-3-mlx')
            if getattr(self,'report_progress',None):self.report_progress(index,expected,int(reused))
            print('OPENFOLD|'+('reused|' if reused else 'completed|')+path.stem,flush=True)


def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--nanohunter-root',type=Path,required=True);p.add_argument('--seeds',default='42');p.add_argument('--samples',type=int,default=1);a=p.parse_args()
    session=OpenFoldSession(dict(root=str(a.nanohunter_root),seed=a.seeds,samples=a.samples,work_dir=str(a.output/'_resident')))
    try:session.predict(a.inputs,a.output,len(list(a.inputs.glob('*.yaml'))))
    finally:session.close()
if __name__=='__main__':main()
