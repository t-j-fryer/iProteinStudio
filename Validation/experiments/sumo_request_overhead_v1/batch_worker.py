"""OpenFold directory-style five-seed throughput, with bounded CPU prefetch."""
import json,os,sys,time,random
from pathlib import Path
from common import save,sha,Profiler

class SeededDataset:
 """Isolate CPU feature RNG exactly as worker0 in each single-request control."""
 def __init__(self,dataset,data_seed):self.dataset=dataset;self.data_seed=data_seed
 def __len__(self):return len(self.dataset)
 def __getitem__(self,index):
  import torch,numpy as np
  from openfold3.core.data.framework.data_module import worker_init_function_with_data_seed
  pr=random.getstate();nr=np.random.get_state();tr=torch.get_rng_state()
  try:
   worker_init_function_with_data_seed(0,self.data_seed,rank=0)
   return self.dataset[index]
  finally:random.setstate(pr);np.random.set_state(nr);torch.set_rng_state(tr)

def main():
 cfg=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);workers=int(sys.argv[3]);out.mkdir(parents=True,exist_ok=False)
 root=Path(os.environ['NANOHUNTER_ROOT']);sys.path.insert(0,str(root/'scripts'))
 import torch,mlx.core as mx,yaml
 assert torch.backends.mps.is_available() and os.environ['PYTORCH_ENABLE_MPS_FALLBACK']=='0'
 torch.set_num_threads(4);torch.set_num_interop_threads(1)
 def sync():torch.mps.synchronize();mx.synchronize()
 from openfold3.run_openfold import _torch_gpu_setup
 _torch_gpu_setup()
 from openfold3.entry_points.experiment_runner import InferenceExperimentRunner
 from openfold3.entry_points.validator import InferenceExperimentConfig
 from openfold3.projects.of3_all_atom.config.inference_query_format import InferenceQuerySet
 from openfold3.core.data.framework.data_module import DataModule
 from openfold_runner_yaml import GPU
 start=time.perf_counter();ec=InferenceExperimentConfig(inference_ckpt_path=root/'models/openfold3/of3_ft3_v1.pt',**yaml.safe_load(GPU))
 s=InferenceExperimentRunner(ec,1,1,False,False,out/'predictions');s.setup();model=s.lightning_module.model
 model.shared.diffusion.no_full_rollout_steps=25
 p=Profiler(sync);p.wrap(model,'forward','model_total',True,features=True)
 from optimizations import ExperimentHooks
 hooks=ExperimentHooks('openfold3',f'w{workers}_keep',s,model,p,out)
 original=DataModule.generate_dataloader
 def loader(dm,mode):
  native=original(dm,mode)
  kwargs=dict(dataset=SeededDataset(native.dataset,dm.data_seed),batch_size=native.batch_size,num_workers=workers,collate_fn=native.collate_fn,generator=native.generator,worker_init_fn=native.worker_init_fn,persistent_workers=workers>0)
  if workers:kwargs['prefetch_factor']=1
  return torch.utils.data.DataLoader(**kwargs)
 DataModule.generate_dataloader=loader
 sync();save(out/'load.json',dict(seconds=time.perf_counter()-start))
 msa=out/'colabfold_main.a3m';msa.write_bytes(Path(cfg['msas']['128']).read_bytes());assert sha(msa)==cfg['msa_hashes']['128']
 for name,seeds in [('warmup',[42]),('batch',[42,43,44,45,46])]:
  s.seeds=seeds
  for k in ('lightning_data_module','data_module_config'):s.__dict__.pop(k,None)
  query=out/(name+'.json');save(query,dict(seeds=seeds,queries={name:dict(use_msas=True,use_main_msas=True,use_paired_msas=False,chains=[dict(molecule_type='protein',chain_ids=['A'],sequence=cfg['sequence'],main_msa_file_paths=[str(msa)])])}))
  p.reset();sync();start=time.perf_counter();s.run(InferenceQuerySet.from_json(query));sync();seconds=time.perf_counter()-start
  structures=list((out/'predictions'/name).rglob('*model.cif'));assert len(structures)==len(seeds)
  save(out/(name+'_measurement.json'),dict(seeds=seeds,workers=workers,prefetch_factor=1 if workers else None,request_seconds=seconds,amortized_seconds=seconds/len(seeds),stages=p.rows,feature_shapes=p.features,structures=[str(f) for f in structures],mps_bytes=torch.mps.driver_allocated_memory(),model_device_after=str(next(model.parameters()).device)))
 DataModule.generate_dataloader=original;hooks.close();save(out/'completed.json',dict(seeds=[42,43,44,45,46],workers=workers))

if __name__=='__main__':main()
