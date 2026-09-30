"""One model loaded once; sequential requests; diagnostic stage replay separate."""
import os,sys,json,time,resource,subprocess,cProfile
from pathlib import Path
from common import save,sha,Profiler

def main():
 START=time.perf_counter();cfg=json.loads(Path(sys.argv[1]).read_text());engine=sys.argv[2];out=Path(sys.argv[3]);variant=sys.argv[4];out.mkdir(parents=True,exist_ok=False)
 root=Path(os.environ['NANOHUNTER_ROOT']);sys.path.insert(0,str(root/'scripts'))
 os.environ.update(MPLCONFIGDIR=str(out/'mpl'),NUMBA_CACHE_DIR=str(out/'numba'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
 import torch
 assert torch.backends.mps.is_available() and os.environ['PYTORCH_ENABLE_MPS_FALLBACK']=='0'
 torch.set_num_threads(1 if engine.startswith('intellifold') else 4);torch.set_num_interop_threads(1)
 sync=torch.mps.synchronize
 if engine.startswith('esm') or engine=='openfold3':
  import mlx.core as mx
  def sync():torch.mps.synchronize();mx.synchronize()
 p=Profiler(sync);spec=cfg['engines'][engine];loadstart=time.perf_counter()
 # Freeze the shipped policy with this experiment before importing the resident adapter.
 import importlib.util
 policy_spec=importlib.util.spec_from_file_location('intellifold_padding',Path(__file__).with_name('intellifold_padding.py'))
 policy=importlib.util.module_from_spec(policy_spec);policy_spec.loader.exec_module(policy);sys.modules['intellifold_padding']=policy
 import resident_predictor as rp
 config=dict(root=str(root),seed=42,samples=1,use_msa=False)
 if engine=='boltz':
  config.update(engine_args=['--accelerator','gpu','--devices','1','--num_workers','0','--output_format','mmcif','--recycling_steps','3','--sampling_steps','200','--diffusion_samples','1','--write_full_pae','--cache',str(root/'models/boltz2')],use_potentials=False)
  s=rp.BoltzSession(config);model=s.model
  p.wrap(model,'predict_step','model_total',True,features=True)
  p.wrap(s.boltz_main,'process_inputs','preprocessing',True,False)
  from boltz.data.module.inference import PredictionDataset
  p.wrap(PredictionDataset,'__getitem__','featurization',True,False)
  for n in ('input_embedder','msa_module','pairformer_module','confidence_module'):
   if hasattr(model,n):p.wrap(getattr(model,n),'forward',n)
  p.wrap(model.structure_module,'sample','diffusion')
 elif engine.startswith('intellifold'):
  config.update(model='v2-flash' if engine.endswith('flash') else 'v2',engine_args=['--seed','42','--num_workers','0','--recycling_iters','10','--sampling_steps','200','--num_diffusion_samples','1','--precision','no'])
  s=rp.IntelliFoldSession(config);model=s.model
  p.wrap(model,'forward','model_total',True,features=True)
  p.wrap(s.upstream,'process_inputs','preprocessing',True,False)
  p.wrap(model,'sample_diffusion','diffusion');p.wrap(model.backbone_trunk,'forward','trunk');p.wrap(model.confidence_head,'forward','confidence')
  # Dataset features include CPU alignment/token preparation.
  from intellifold.data.module.inference import PredictionDataset
  p.wrap(PredictionDataset,'__getitem__','featurization',True,False)
 elif engine.startswith('protenix'):
  config['model']={'protenix_v2':'v2','protenix_mini':'mini','protenix_constraint':'constraint'}[engine]
  s=rp.ProtenixSession(config);model=s.runner.model
  p.wrap(s.runner,'predict','model_total',True,features=True)
  p.wrap(model,'get_pairformer_output','trunk');p.wrap(model,'sample_diffusion','diffusion');p.wrap(model,'run_confidence_head','confidence')
  import runner.inference as ri
  p.wrap(ri,'get_inference_dataloader','preprocessing',True,False)
  from protenix.data.inference.infer_dataloader import InferenceDataset
  p.wrap(InferenceDataset,'__getitem__','featurization',True,False)
 elif engine.startswith('esm'):
  import esmfold2_predict as ep
  profile='fast' if engine.endswith('fast') else 'full';s=ep.Session(root,profile);model=s.model
  p.wrap(type(model),'__call__','model_total',True,features=True)
  p.wrap(s.builder,'prepare_input','preprocessing',True,False)
  p.wrap(s.builder,'decode','decode',True,False)
  p.wrap(model,'compute_lm_hidden_states','sequence_embedding',evaluate=mx.eval)
  p.wrap(model,'trunk','trunk_including_embedding',evaluate=mx.eval)
  p.wrap(model.structure_head,'sample','diffusion',evaluate=mx.eval)
  p.wrap(model,'confidence','confidence',evaluate=mx.eval)
 elif engine=='openfold3':
  os.environ['OPENFOLD_CACHE']=str(root/'models/openfold3')
  from openfold3.run_openfold import _torch_gpu_setup
  _torch_gpu_setup()
  from openfold3.entry_points.experiment_runner import InferenceExperimentRunner
  from openfold3.entry_points.validator import InferenceExperimentConfig
  from openfold3.projects.of3_all_atom.config.inference_query_format import InferenceQuerySet
  from openfold_runner_yaml import GPU
  import yaml
  ec=InferenceExperimentConfig(inference_ckpt_path=root/'models/openfold3/of3_ft3_v1.pt',**yaml.safe_load(GPU))
  s=InferenceExperimentRunner(ec,1,1,False,False,out/'predictions');s.setup();model=s.lightning_module.model
  p.wrap(model,'forward','model_total',True,features=True);p.wrap(model,'run_trunk','trunk');p.wrap(model,'_rollout','diffusion')
  for n in ('msa_module','pairformer','aux_heads'):
   if hasattr(model,n):p.wrap(getattr(model,n),'forward',n)
 else:raise ValueError(engine)
 from optimizations import ExperimentHooks
 hooks=ExperimentHooks(engine,variant,s,model,p,out)
 sync();loadsecs=time.perf_counter()-loadstart;identity=id(model)
 save(out/'load.json',dict(seconds=loadsecs,imports_and_setup_seconds=time.perf_counter()-START,pid=os.getpid(),model_identity=identity,torch=torch.__version__,threads=torch.get_num_threads(),engine=engine))
 rows=[];first=True
 for msa in ['128']:
  for budget,steps in [('reduced',spec['reduced'])]:
   schedule=[(42,variant,True,False)]+[(seed,variant,False,False) for seed in range(42,47)]+[(42,variant,False,True)]
   if variant=='ccd_interleaved':
    schedule=[(42,variant,True,False)]+[(seed,mode,False,False) for seed in range(42,47) for mode in (['baseline_interleaved','ccd_interleaved'] if seed%2==0 else ['ccd_interleaved','baseline_interleaved'])]
   for i,(seed,measured_variant,warmup,diagnostic) in enumerate(schedule):
    hooks.cache_enabled=measured_variant!='baseline_interleaved'
    tag=f'{msa}_{budget}_{seed}'+('_profile' if diagnostic else '_warmup' if warmup else '')
    if variant=='ccd_interleaved':tag+='_'+measured_variant
    unit=out/tag;unit.mkdir()
    path='empty' if msa=='none' else cfg['msas'][msa]
    if path!='empty':assert sha(path)==cfg['msa_hashes'][msa]
    source=unit/'input';source.mkdir();name='sumo';inp=source/'sumo.yaml'
    inp.write_text('version: 1\nsequences:\n  - protein:\n      id: A\n      sequence: '+cfg['sequence']+'\n      msa: '+path+'\n')
    p.diagnostic=diagnostic;p.reset();torch.manual_seed(seed)
    if engine=='boltz':
     s.request_seed=seed;s.model.predict_args['sampling_steps']=steps
     # Native resident full-depth cap remains1024; low-MSA arms have <=128 rows.
    elif engine.startswith('intellifold'):
     s.seeds=[seed];s.args.seed=str(seed);s.args.sampling_steps=steps;model.sample_config.no_sample_steps_T=steps
    elif engine.startswith('protenix'):
     s.config['use_msa']=msa!='none';s.seeds=[seed]
     for c in (s.runner.configs,model.configs):c.seeds=[seed];c.use_msa=msa!='none';c.sample_diffusion.N_step=steps
    elif engine.startswith('esm'):
     ep.PROFILES[profile]=(spec['recycles'],steps);mx.random.seed(seed)
    elif engine=='openfold3':
     model.shared.diffusion.no_full_rollout_steps=steps
     for k in ('lightning_data_module','data_module_config'):s.__dict__.pop(k,None)
     s.seeds=[seed]
     query=unit/'query.json';qname=tag.replace('_','-')
     # Use the same lossless MSA filename adapter as Studio Predict/Protein Hunter.
     helper=Path(__file__).with_name('openfold_query_json.py')
     subprocess.run([sys.executable,str(helper),str(inp),cfg['sequence'],qname,str(query),'','',str(seed)],check=True)
     if msa!='none':
      staged=json.loads(query.read_text())['queries'][qname]['chains'][0]['main_msa_file_paths'][0]
      assert sha(staged)==cfg['msa_hashes'][msa]
    sync();trace=cProfile.Profile() if diagnostic else None
    if trace:trace.enable()
    start=time.perf_counter();cpu=time.process_time()
    if engine.startswith('esm'):
     destination=unit/'prediction';destination.mkdir();s.predict([dict(id='A',kind='protein',sequence=cfg['sequence'],msa=path)],seed,1,destination,name)
    elif engine=='openfold3':s.run(InferenceQuerySet.from_json(query))
    else:s.predict(source,unit/'prediction',1)
    sync();seconds=time.perf_counter()-start
    if trace:trace.disable();trace.dump_stats(str(unit/'cpu_profile.prof'))
    assert id(model)==identity
    if engine=='openfold3':
     msa_shapes=[f['msa'] for f in p.features if 'msa' in f]
     assert msa_shapes and all(v[-2]==len(cfg['sequence']) for v in msa_shapes),p.features
     assert all((v[-3]==1 if msa=='none' else v[-3]>1) for v in msa_shapes),p.features
    structroot=(out/'predictions'/qname) if engine=='openfold3' else unit/'prediction'
    if engine.startswith('intellifold'):
     assert p.features and all(shape['msa'][-2]==len(cfg['sequence']) for shape in p.features if 'msa' in shape),p.features
    structures=[f for f in structroot.rglob('*.cif') if 'processed' not in f.parts]
    # Protenix's normalized output may point to the same structure twice.
    real={f.resolve():f for f in structures};assert len(real)==1,(engine,list(real))
    structure=next(iter(real));from validate_prediction_geometry import inspect_geometry
    geometry=inspect_geometry(structure);assert not geometry['errors'],geometry
    row=dict(variant=measured_variant,model_device_after=str(next(model.parameters()).device) if hasattr(model,"parameters") else "mlx",engine=engine,msa=msa,budget=budget,steps=steps,recycles=spec['recycles'],seed=seed,diagnostic=diagnostic,first_model_request=first,request_seconds=seconds,cpu_seconds=time.process_time()-cpu,stages=p.rows,feature_shapes=p.features,structure=str(structure),geometry=geometry,model_load_count=1,pid=os.getpid(),mps_bytes=torch.mps.driver_allocated_memory(),rss_peak_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    save(unit/'measurement.json',row);rows.append(str(unit/'measurement.json'));first=False
    save(out/'progress.json',dict(completed=len(rows),last=tag))
    print('MATRIX_UNIT '+json.dumps({k:row[k] for k in ('engine','msa','steps','seed','diagnostic','request_seconds')}),flush=True)
 hooks.close()
 save(out/'completed.json',dict(rows=rows,load_seconds=loadsecs,process_seconds=time.perf_counter()-START,pid=os.getpid(),model_load_count=1))

if __name__ == '__main__':
 main()
