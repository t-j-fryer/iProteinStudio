"""Explicit OpenFold, MLX RFD3 and AntiFold fixed-input benchmark adapters."""
import functools,importlib.metadata,json,os,resource,sys,time
from pathlib import Path
from worker import Profile,atomic,sha

def run_extra(req,out,request,start):
 import numpy as np
 import torch
 root=Path(req['root']);engine=req['engine'];load=time.monotonic();rows=[]
 sync=torch.mps.synchronize;profile=Profile(sync)
 if engine=='rfd3':
  import mlx.core as mx
  mx.set_default_device(mx.gpu)
  expected='0.32.2' if req['runtime']=='candidate' else '0.32.0'
  assert importlib.metadata.version('mlx')==expected
  sync=mx.synchronize;profile=Profile(sync);profile.evaluate=mx.eval
  sys.path[:0]=[str(root/'rfd3/mlx_port'),str(root/'rfd3')]
  import sampler,rfd3_mlx as R
  if req.get('diagnostic')=='kernel':
   from kernel_benchmark import run
   run(R,out)
   atomic(out/'result.json',dict(rows=[],diagnostic='Synthetic sparse-attention kernel benchmark',process_seconds=time.monotonic()-start))
   atomic(out/'completed.json',dict(request_sha256=sha(request),files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}));return
  from featurizer import featurize_binder
  from rfd3_weight_set import assert_ema_artifact
  weights=root/'rfd3/weights/rfd3_core.safetensors';metadata=assert_ema_artifact(weights)
  w=R.to_bf16(mx.load(str(weights)));mx.eval(w);sync()
  if req.get('variant') in ('sparse_sdpa','sparse_metal','sparse_metal_round'):
   if req['variant']=='sparse_metal_round':from rounded_attention import install
   elif req['variant']=='sparse_metal':from metal_sparse_attention import install
   else:from rfd3_attention import install
   variant_evidence=install(R)
   atomic(out/'variant.json',variant_evidence)
  atomic(out/'effective.json',dict(weight_metadata=metadata,steps=200,recycles=2,samples=1,precision='existing selective BF16',mlx=expected,fixture='unconditional protein, existing NumPy featurizer; no target or conditioning'))
  profile.wrap(sampler,'create_attention_indices_mlx','neighbor_indices')
  profile.wrap(R.DiffusionModule,'__call__','denoiser')
  profile.wrap(sampler.TokenInitializer,'__call__','token_initializer')
 elif engine=='openfold':
  os.environ['OPENFOLD_CACHE']=str(Path(req['managed_root'])/'models/openfold3')
  import mlx.core as mx
  def sync():torch.mps.synchronize();mx.synchronize()
  profile=Profile(sync)
  from openfold3.core.model.primitives import attention_mlx
  if req.get('variant')=='checkpoint_init':
   from openfold_initialization import install
   init_evidence=install(torch)
  if req.get('variant')=='sparse_sdpa':
   from openfold_attention import install
   variant_evidence=install(torch)
   atomic(out/'variant.json',variant_evidence)
  transfer={'torch_to_mlx_calls':0,'torch_to_mlx_elements':0,'mlx_to_torch_calls':0,'attention_calls':0}
  for name,key in [('_torch_to_mlx','torch_to_mlx_calls'),('_mlx_to_torch','mlx_to_torch_calls'),('mlx_evo_attention','attention_calls')]:
   old=getattr(attention_mlx,name)
   def wrap(old=old,key=key):
    @functools.wraps(old)
    def counted(*a,**k):
     transfer[key]+=1
     if key=='torch_to_mlx_calls':transfer['torch_to_mlx_elements']+=a[0].numel()
     return old(*a,**k)
    return counted
   setattr(attention_mlx,name,wrap())
  from openfold3.run_openfold import predict
  from openfold3.entry_points.experiment_runner import InferenceExperimentRunner
  from openfold3.projects.of3_all_atom.model import OpenFold3
  msa_features=[]
  old_forward=OpenFold3.forward
  def capture_msa(self,batch):
   shapes={k:list(v.shape) for k,v in batch.items() if 'msa' in k and hasattr(v,'shape')}
   msa_features.append(shapes)
   if req.get('use_msa'):assert batch['msa'].shape[-3]>1,shapes
   return old_forward(self,batch)
  OpenFold3.forward=capture_msa
  profile.wrap(OpenFold3,'forward','model_total')
  profile.wrap(OpenFold3,'run_trunk','trunk')
  profile.wrap(OpenFold3,'_rollout','diffusion')
  profile.wrap(InferenceExperimentRunner,'setup','load_setup')
  profile.wrap(InferenceExperimentRunner,'run','run')
  from openfold_runner_yaml import GPU
  runner=out/'runner.yaml';runner.write_text(GPU)
  atomic(out/'effective.json',dict(torch=req['torch_version'],mlx=importlib.metadata.version('mlx'),num_diffusion_samples=1,num_model_seeds=1,runner_yaml=GPU,mode='existing CLI callback; model reload per input; no residency claim',use_msa_server=False,use_templates=False))
 elif engine=='antifold':
  from antifold import antiscripts as anti
  import pandas as pd
  model=anti.load_model();assert next(model.parameters()).device.type=='mps'
  profile.wrap(model,'forward','model_total')
  profile.wrap(anti,'get_dataset_dataloader','preprocess')
  atomic(out/'effective.json',dict(torch=req['torch_version'],checkpoint_sha256=sha(root/'src/AntiFold/models/model.pt'),device='mps',mode='teacher-forced logits on fixed benign monomer backbones, custom_chain_mode; no sequence design',data_workers=0))
 else:raise RuntimeError('Unknown engine')
 sync();load=time.monotonic()-load
 for i,case in enumerate(req['cases']):
  unit=out/f'unit_{i:02d}';unit.mkdir();profile.enabled=bool(case.get('profile'));profile.reset();details={}
  sync();t=time.monotonic();cpu=time.process_time()
  if engine=='rfd3':
   feats,coords=featurize_binder([],[],len(case['sequence']))
   np.savez(unit/'features.npz',**feats,coord_to_be_noised=coords)
   model=sampler.Sampler(w,num_timesteps=200,n_recycle=2,seed=req['seed'])
   pred=model.generate(feats,D=1,coord_to_be_noised=coords);mx.eval(pred);sync()
   xyz=np.asarray(pred['X_L'])[0];idx=np.asarray(pred['sequence_indices_I'])[0]
   assert xyz.shape==(14*len(case['sequence']),3) and np.isfinite(xyz).all()
   np.savez(unit/'prediction.npz',coordinates=xyz,ca=xyz[np.asarray(feats['is_ca'],bool)],sequence_indices=idx)
   details=dict(tokens=len(case['sequence']),mlx=importlib.metadata.version('mlx'),peak_memory_bytes=mx.get_peak_memory())
  elif engine=='openfold':
   query=unit/'query.json'
   chain=dict(molecule_type='protein',chain_ids=['A'],sequence=case['sequence'])
   if case.get('msa'):
    assert sha(case['msa'])==case['msa_sha256'],'Alignment changed'
    chain['main_msa_file_paths']=[case['msa']]
   atomic(query,dict(seeds=[req['seed']],queries={case['name']:dict(use_msas=bool(case.get('msa')),use_paired_msas=False,use_main_msas=bool(case.get('msa')),chains=[chain])}))
   for k in transfer:transfer[k]=0
   predict.callback(query_json=query,inference_ckpt_path=Path(req['managed_root'])/'models/openfold3/of3_ft3_v1.pt',num_diffusion_samples=1,num_model_seeds=1,runner_yaml=runner,use_msa_server=False,use_templates=False,output_dir=unit/'prediction')
   assert len(list((unit/'prediction').rglob('*.cif')))==1,'OpenFold returned without its requested structure; inspect summary.txt'
   details=dict(transfer);details['msa_feature_shapes']=msa_features[-1:];details['msa_sha256']=case.get('msa_sha256');details['float32_matmul_precision']=torch.get_float32_matmul_precision();details['measurement_scope']='includes a new model load for each input'
  elif engine=='antifold':
   fixture=Path(req['fixtures'])/(case['name']+'.pdb')
   df=pd.DataFrame([dict(pdb=case['name'],Hchain='A',Lchain=float('nan'))])
   logits=anti.get_pdbs_logits(model,df,pdb_dir=str(fixture.parent),custom_chain_mode=True,nanobody_mode=True,num_threads=0,seed=req['seed'],save_flag=False)
   assert len(logits)==1
   values=logits[0][list('ACDEFGHIKLMNPQRSTVWY')].to_numpy(dtype=float)
   assert values.shape==(len(case['sequence']),20) and np.isfinite(values).all()
   np.save(unit/'logits.npy',values);logits[0].to_csv(unit/'residues.csv',index=False)
  sync();seconds=time.monotonic()-t
  row=dict(name=case['name'],sequence=case['sequence'],seed=req['seed'],warmup=case.get('warmup',False),profiled=profile.enabled,seconds=seconds,cpu_seconds=time.process_time()-cpu,stages=profile.rows,details=details,torch=torch.__version__,threads=torch.get_num_threads(),rss_peak_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
  atomic(unit/'measurement.json',row);rows.append(str(unit/'measurement.json'));print('BENCH_UNIT|'+json.dumps(row),flush=True)
 if engine in ('rfd3','openfold') and req.get('variant') in ('sparse_sdpa','sparse_metal','sparse_metal_round'):
  counts=variant_evidence['execution'] if engine=='rfd3' else variant_evidence
  if counts['calls']==0:raise RuntimeError('Requested attention implementation was never called')
  atomic(out/'variant.json',variant_evidence)
 if engine=='openfold' and req.get('variant')=='checkpoint_init':
  atomic(out/'initialization.json',init_evidence)
  assert init_evidence['skipped_initializers']==init_evidence['verified_initializers']+init_evidence['discarded_modules'] and init_evidence['strict_loads']==len(req['cases'])
 atomic(out/'result.json',dict(rows=rows,model_load_seconds=load,process_seconds=time.monotonic()-start))
 atomic(out/'completed.json',dict(request_sha256=sha(request),files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}))
