"""ESM600 arm using Figure2a's resident, synchronized timing and audit helpers."""
import json,os,sys,time,traceback
from pathlib import Path
from common import Profiler,save,sha
from memory import Sampler,summarize

def main():
 cfg=json.loads(Path(sys.argv[1]).read_text());block=cfg['blocks'][int(sys.argv[2])]
 out=Path(cfg['output'])/'blocks'/block['id'];out.mkdir(parents=True,exist_ok=True)
 session=out/'sessions'/str(time.time_ns());session.mkdir(parents=True)
 root=Path(os.environ['NANOHUNTER_ROOT'])
 assert (root/'view.json').is_file() and (root/'assets.json').is_file(), 'Benchmark requires the broker-retained runtime view'
 assert os.environ.get('IPROTEINSTUDIO_RUNTIME_BINDINGS'), 'Missing immutable runtime bindings'
 print('RUNTIME_VIEW',root,flush=True);sys.path.insert(0,str(root/'scripts'))
 os.environ.update(MPLCONFIGDIR=str(session/'mpl'),NUMBA_CACHE_DIR=str(session/'numba'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
 memory=Sampler(session/'memory.jsonl');profiler=None
 try:
  start=time.perf_counter()
  from esmfold2_600 import validate_assets
  assets=validate_assets(root);asset_seconds=time.perf_counter()-start
  start=time.perf_counter()
  import torch,mlx.core as mx
  assert torch.backends.mps.is_available() and mx.metal.is_available()
  assert os.environ['PYTORCH_ENABLE_MPS_FALLBACK']=='0'
  torch.set_num_threads(4);torch.set_num_interop_threads(1)
  def sync():torch.mps.synchronize();mx.synchronize()
  import prediction_profiles as profiles,esmfold2_predict as ep
  settings=dict(msa_depth=0,recycles=cfg['protocol']['recycles'],diffusion_steps=cfg['protocol']['diffusion_steps'],chunk_size=block['chunk_size'],cache_limit_mib=block['cache_limit_mib'])
  profiles.activate({'esmfold2-600-mlx':settings})
  load_start=time.perf_counter();s=ep.Session(root,'600');model=s.model;sync();load_seconds=time.perf_counter()-load_start
  profiler=Profiler(sync);p=profiler
  p.wrap(type(model),'__call__','model_total',True,features=True)
  p.wrap(s.builder,'prepare_input','preprocessing',True,False);p.wrap(s.builder,'decode','decode',True,False)
  p.wrap(ep,'atomic','confidence_write',True,False)
  from esm.utils.structure.molecular_complex import MolecularComplex
  p.wrap(MolecularComplex,'to_mmcif','structure_serialization',True,False)
  p.wrap(model,'compute_lm_hidden_states','sequence_embedding',evaluate=mx.eval)
  p.wrap(model,'trunk','trunk_including_embedding',evaluate=mx.eval)
  p.wrap(model.structure_head,'sample','diffusion',evaluate=mx.eval)
  p.wrap(model,'confidence','confidence',evaluate=mx.eval)
  memory.stage=lambda:p.stack[-1] if p.stack else 'request_other'
  memory.gpu=lambda:dict(mps_active_bytes=torch.mps.current_allocated_memory(),mps_driver_bytes=torch.mps.driver_allocated_memory(),mlx_active_bytes=mx.get_active_memory(),mlx_cache_bytes=mx.get_cache_memory(),mlx_peak_bytes=mx.get_peak_memory())
  save(session/'load.json',dict(load_seconds=load_seconds,initialization_seconds=time.perf_counter()-start,asset_verify_seconds=asset_seconds,pid=os.getpid(),model_identity=id(model),runtime_view=str(root),adapter_sha256=sha(ep.__file__),torch_version=torch.__version__,assets=assets,settings=settings,memory=summarize(memory.path,'initialization')))
  identity=id(model);target=cfg['targets'][block['target']];outputs=[]
  from quality import audit
  for seed,warmup in [(cfg['protocol']['warmup_seed'],True)]+[(seed,False) for seed in cfg['protocol']['seeds']]:
   tag=('warmup_' if warmup else 'seed_')+str(seed);unit=out/tag
   if not warmup and (unit/'complete.json').exists():
    receipt=json.loads((unit/'complete.json').read_text());assert all(sha(k)==v for k,v in receipt['files'].items());outputs.append(str(unit/'measurement.json'));continue
   if unit.exists():unit=out/(tag+'_attempt_'+session.name)
   unit.mkdir();dest=unit/'prediction';dest.mkdir();memory.scope=unit.name
   chains=[dict(id=c,kind='protein',sequence=target['sequence'],msa='empty') for c in 'AB'[:target['copies']]]
   # Explicit research-only dimer: no app planner restrictions are broadened.
   assert target['length'] in (96,164,370,916) and len(chains)==target['copies']
   save(unit/'input.json',dict(chains=chains,seed=seed,samples=1,settings=settings))
   save(out/'active.json',dict(unit=str(unit),seed=seed,warmup=warmup,pid=os.getpid(),status='running'))
   print('UNIT_START',block['id'],unit.name,flush=True);p.reset();p.diagnostic=True
   torch.manual_seed(seed);mx.random.seed(seed);mx.reset_peak_memory();sync()
   start=time.perf_counter();cpu=time.process_time();start_unix=time.time()
   s.predict(chains,seed,1,dest,'protein');sync()
   seconds=time.perf_counter()-start;cpu_seconds=time.process_time()-cpu;end_unix=time.time()
   allocator=dict(mlx_peak_bytes=mx.get_peak_memory(),mlx_active_bytes=mx.get_active_memory(),mlx_cache_bytes=mx.get_cache_memory())
   assert identity==id(model)
   structures=list(dest.glob('*.cif'));assert len(structures)==1
   memory.scope='audit';audit_start=time.perf_counter();check=audit(structures[0],target)
   assert not check['geometry']['errors'],check['geometry']
   row=dict(block=block,seed=seed,warmup=warmup,pid=os.getpid(),model_identity=identity,model_load_count=1,start_unix=start_unix,end_unix=end_unix,request_seconds=seconds,cpu_seconds=cpu_seconds,stages=p.rows,feature_shapes=p.features,structure=str(structures[0]),memory=summarize(memory.path,unit.name),memory_trace=str(memory.path),allocator=allocator,geometry=check['geometry'],crystal=check['crystal'],scores=check['scores'],audit_seconds=time.perf_counter()-audit_start)
   save(unit/'measurement.json',row)
   check['files'].update({str(unit/'measurement.json'):sha(unit/'measurement.json'),str(unit/'input.json'):sha(unit/'input.json')})
   save(unit/'complete.json',dict(seed=seed,files=check['files']));outputs.append(str(unit/'measurement.json'))
   print('UNIT_DONE',block['id'],unit.name,round(seconds,3),flush=True)
  s.close();save(out/'completed.json',dict(outputs=outputs,session=str(session)))
 except BaseException as exc:
  text=traceback.format_exc();oom=any(x in text.lower() for x in ('out of memory','insufficient memory','insufficientmemory'))
  save(session/'failure.json',dict(error=repr(exc),traceback=text,status='oom' if oom else 'error',stage=profiler.failed_stage if profiler else 'initialization',unix=time.time()));raise
 finally:memory.close()
if __name__=='__main__':main()
