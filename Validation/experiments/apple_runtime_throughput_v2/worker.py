"""Bounded fixed-input replay in one isolated engine process, broker owned."""
import argparse, functools, hashlib, importlib.metadata, json, os, resource, sys, time
from pathlib import Path

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def atomic(p,x):
 p=Path(p);t=p.with_suffix('.part');t.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n');t.replace(p)
class Profile:
 def __init__(self,sync):self.sync=sync;self.rows={};self.enabled=False
 def wrap(self,obj,name,label):
  old=getattr(obj,name)
  @functools.wraps(old)
  def call(*a,**k):
   if not self.enabled:return old(*a,**k)
   self.sync();t=time.monotonic();c=time.process_time()
   result=old(*a,**k)
   if hasattr(self,'evaluate'):self.evaluate(result)
   self.sync()
   r=self.rows.setdefault(label,dict(calls=0,seconds=0,cpu_seconds=0));r['calls']+=1;r['seconds']+=time.monotonic()-t;r['cpu_seconds']+=time.process_time()-c
   return result
  setattr(obj,name,call)
 def reset(self):self.rows={}

def main():
 start=time.monotonic();ap=argparse.ArgumentParser();ap.add_argument('--request',type=Path,required=True);a=ap.parse_args();req=json.loads(a.request.read_text())
 out=Path(req['output']);out.mkdir(parents=True,exist_ok=False);root=Path(req['root']);engine=req['engine']
 os.environ['NANOHUNTER_ROOT']=str(root)
 os.environ['MPLCONFIGDIR']=str(out/'matplotlib');os.environ['NUMBA_CACHE_DIR']=str(out/'numba');os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
 sys.path.insert(0,str(root/'scripts'))
 import numpy as np
 import torch
 assert torch.__version__.split('+')[0]==req['torch_version'],torch.__version__
 assert torch.backends.mps.is_available(),'MPS unavailable'
 assert os.environ['PYTORCH_ENABLE_MPS_FALLBACK']=='0'
 torch.set_num_threads(req['threads']);torch.set_num_interop_threads(1)
 torch.set_float32_matmul_precision('highest')
 sync=torch.mps.synchronize;prof=Profile(sync);load=time.monotonic()
 if req.get('diagnostic')=='rng':
  gen=torch.Generator(device='mps').manual_seed(req['seed']);arrays={}
  for j in range(3):
   arrays[f'normal{j}']=torch.empty((1,601,3),device='mps').normal_(generator=gen).cpu().numpy()
   arrays[f'uniform{j}']=torch.rand((1,3),device='mps',generator=gen).cpu().numpy()
   arrays[f'translation{j}']=torch.randn((1,3),device='mps',generator=gen).cpu().numpy()
  np.savez(out/'random_draws.npz',**arrays)
  atomic(out/'result.json',dict(rows=[],torch=torch.__version__,diagnostic='Independent MPS generator draw sequence, same seed and call shapes'))
  atomic(out/'completed.json',dict(request_sha256=sha(a.request),files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}));return
 if engine.startswith('intellifold') or engine in ('protenix','constraint'):
  import resident_predictor as rp
  config=dict(root=str(root),seed=req['seed'],samples=1,use_msa=False)
  if engine.startswith('intellifold'):
   config.update(model='v2-flash' if engine.endswith('flash') else 'v2',engine_args=['--seed',str(req['seed']),'--num_workers','0','--recycling_iters','10','--sampling_steps','200','--num_diffusion_samples','1','--precision','no'])
   if req.get('variant')=='buckets128':config['engine_args']+=['--buckets','128,256,512,768,1024,2048,4096,5120']
   session=rp.IntelliFoldSession(config)
   feature_shapes=[]
   def record_shapes(module,args):
    features=args[0]
    feature_shapes.append({k:list(features[k].shape) for k in ('seq_mask','ref_pos','token_bonds')})
   session.model.register_forward_pre_hook(record_shapes)
   prof.wrap(session.upstream,'process_inputs','preprocess')
   prof.wrap(session.model,'forward','model_total')
   prof.wrap(session.model,'sample_diffusion','diffusion')
   prof.wrap(session.model.backbone_trunk,'forward','trunk')
   prof.wrap(session.model.confidence_head,'forward','confidence')
  else:
   config['model']='constraint' if engine=='constraint' else 'v2'
   session=rp.ProtenixSession(config)
   if req.get('variant')=='diffusion_cache':
    session.runner.configs.enable_diffusion_shared_vars_cache=True
    session.runner.model.configs.enable_diffusion_shared_vars_cache=True
    session.runner.model.enable_diffusion_shared_vars_cache=True
   cfg=session.runner.configs
   assert cfg.model.N_cycle==10 and cfg.sample_diffusion.N_step==200 and cfg.sample_diffusion.N_sample==1
   assert cfg.dtype=='fp32' and not cfg.enable_efficient_fusion and not cfg.enable_tf32 and not cfg.use_template and not cfg.use_msa
   atomic(out/'effective_protenix.json',dict(model_name=session.model_name,recycles=cfg.model.N_cycle,steps=cfg.sample_diffusion.N_step,samples=cfg.sample_diffusion.N_sample,dtype=cfg.dtype,cache=session.runner.model.enable_diffusion_shared_vars_cache,fusion=cfg.enable_efficient_fusion,tf32=cfg.enable_tf32,use_msa=cfg.use_msa,use_template=cfg.use_template,parameter_dtypes=sorted({str(p.dtype) for p in session.runner.model.parameters()})))
   prof.wrap(session.runner,'predict','model_total')
   prof.wrap(session.runner.model,'sample_diffusion','diffusion')
   prof.wrap(session.runner.model,'run_confidence_head','confidence')
  atomic(out/'effective.json',dict(config=config,resume_identity=getattr(session,'resume_identity',None),model_load_count=session.model_load_count,variant=req.get('variant'),diffusion_cache=getattr(getattr(getattr(session,'runner',None),'model',None),'enable_diffusion_shared_vars_cache',None)))
 elif engine=='nesso':
  sys.path.insert(0,str(root/'scripts/nise'))
  import nesso_worker
  session=nesso_worker.Engine(Path(req['managed_root']))
  # Same pretrained backbone and tokenizer; omit only outputs the scorer never consumes.
  if req.get('variant')=='esm_backbone':
   import types
   def forward(**kw):
    kw.pop('output_hidden_states',None)
    return types.SimpleNamespace(hidden_states=(session.esm.esm(**kw,output_hidden_states=False,return_dict=True).last_hidden_state,))
   session.esm.forward=forward
  if req.get('variant')=='ccd_cache':
   from nesso_cache import install
   cache_counts=install()
  import nesso.main as nm
  import nesso.data.inference as ni
  prof.wrap(nm,'preprocess_yamls','preprocess')
  prof.wrap(ni,'load_standard_aa_mols','ccd_load')
  prof.wrap(ni.InferenceDataset,'__getitem__','featurize')
  prof.wrap(session.model,'predict_step','model_total')
  prof.wrap(session.esm,'forward','esm')
 else:
  from extra_engines import run_extra
  return run_extra(req,out,a.request,start)
 sync();load=time.monotonic()-load;rows=[]
 for i,case in enumerate(req['cases']):
  unit=out/f'unit_{i:02d}';unit.mkdir();prof.enabled=bool(case.get('profile'));prof.reset()
  sync();t=time.monotonic();c=time.process_time()
  if engine=='nesso':
   details=session.score(case['sequence'],'CC(=O)O',unit/'prediction',req['seed'])
  else:
   import yaml
   source=unit/'input';source.mkdir()
   (source/(case['name']+'.yaml')).write_text(yaml.safe_dump(dict(version=1,sequences=[dict(protein=dict(id='A',sequence=case['sequence'],msa='empty'))]),sort_keys=False))
   if req.get('random_tape'):
    from random_tape import RandomTape
    reference=Path(req['random_reference'])/f'unit_{i:02d}'/'random_tape.npz' if req['random_tape']=='replay' else None
    generator=session.model.generator if engine.startswith('intellifold') else None
    with RandomTape(torch,generator,unit/'random_tape.npz',reference=reference) as tape:
     session.predict(source,unit/'prediction',1)
    minimum=500 if engine.startswith('intellifold') else 399
    if len(tape.events)<minimum:raise RuntimeError('Random tape did not capture the complete diffusion trajectory')
    details=dict(random_tape=req['random_tape'],draw_count=len(tape.events),timing='diagnostic only; includes RNG recording/replay transfers')
   else:
    session.predict(source,unit/'prediction',1);details={}
  sync();seconds=time.monotonic()-t
  if engine=='nesso' and req.get('variant')=='ccd_cache':details['ccd_cache']=dict(cache_counts)
  if engine.startswith('intellifold'):details['model_input_shapes']=feature_shapes[-1:]
  row=dict(name=case['name'],sequence=case['sequence'],seed=req['seed'],warmup=case.get('warmup',False),profiled=prof.enabled,seconds=seconds,cpu_seconds=time.process_time()-c,stages=prof.rows,details=details,torch=torch.__version__,threads=torch.get_num_threads(),mps_bytes=torch.mps.driver_allocated_memory(),rss_peak_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
  atomic(unit/'measurement.json',row);rows.append(str(unit/'measurement.json'))
  print('BENCH_UNIT|'+json.dumps({k:row[k] for k in ('name','warmup','profiled','seconds','cpu_seconds','stages')}),flush=True)
 atomic(out/'result.json',dict(rows=rows,model_load_seconds=load,process_seconds=time.monotonic()-start,packages={n:importlib.metadata.version(n) for n in ('torch','numpy')}))
 atomic(out/'completed.json',dict(request_sha256=sha(a.request),files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}))
if __name__=='__main__':main()
