import os,sys,json,time
from pathlib import Path
from common import Profiler

def initialize(cfg,engine,out):
 START=time.perf_counter()
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
  from boltz.data.module.inferencev2 import PredictionDataset
  p.wrap(PredictionDataset,'__getitem__','featurization',True,False)
  for n in ('input_embedder','msa_module','pairformer_module','confidence_module'):
   if hasattr(model,n):p.wrap(getattr(model,n),'forward',n)
  p.wrap(model.structure_module,'sample','diffusion')
  from boltz.data.write.writer import BoltzWriter
  p.wrap(BoltzWriter,'write_on_batch_end','output_write',True,False)
 elif engine.startswith('intellifold'):
  config.update(model='v2-flash' if engine.endswith('flash') else 'v2',engine_args=['--seed','42','--num_workers','0','--recycling_iters','10','--sampling_steps','200','--num_diffusion_samples','1','--precision','no'])
  s=rp.IntelliFoldSession(config);model=s.model
  p.wrap(model,'forward','model_total',True,features=True)
  p.wrap(s.upstream,'process_inputs','preprocessing',True,False)
  import types
  p.wrap(s.upstream,'write_cif','structure_write',True,False)
  json_proxy=types.SimpleNamespace(**vars(s.upstream.json));p.wrap(json_proxy,'dump','confidence_write',True,False);s.upstream.json=json_proxy
  p.wrap(model,'sample_diffusion','diffusion');p.wrap(model.backbone_trunk,'forward','trunk');p.wrap(model.confidence_head,'forward','confidence')
  # Dataset features include CPU alignment/token preparation.
  from intellifold.data.module.inference import PredictionDataset
  p.wrap(PredictionDataset,'__getitem__','featurization',True,False)
 elif engine.startswith('protenix'):
  config['model']={'protenix_v2':'v2','protenix_mini':'mini','protenix_constraint':'constraint'}[engine]
  s=rp.ProtenixSession(config);model=s.runner.model
  p.wrap(s.runner,'predict','model_total',True,features=True)
  p.wrap(s.runner.dumper,'dump','output_write',True,False)
  p.wrap(model,'get_pairformer_output','trunk');p.wrap(model,'sample_diffusion','diffusion');p.wrap(model,'run_confidence_head','confidence')
  # Count repeated invariant work without adding GPU fences inside every denoising step.
  # These are CPU dispatch times; synchronized diffusion/model timers measure GPU work.
  p.wrap(model.diffusion_module.diffusion_conditioning,'prepare_cache','diffusion_pair_conditioning_dispatch',gpu=False)
  p.wrap(model.diffusion_module.atom_attention_encoder,'prepare_cache','diffusion_atom_conditioning_dispatch',gpu=False)
  import runner.inference as ri
  p.wrap(ri,'get_inference_dataloader','preprocessing',True,False)
  from protenix.data.inference.infer_dataloader import InferenceDataset
  p.wrap(InferenceDataset,'__getitem__','featurization',True,False)
 elif engine.startswith('esm'):
  import esmfold2_predict as ep
  profile='fast' if engine.endswith('fast') else 'full';s=ep.Session(root,profile);model=s.model
  # Native __call__ materializes MLX results into Torch outputs before returning.
  p.wrap(type(model),'__call__','model_total',True,features=True)
  p.wrap(s.builder,'prepare_input','preprocessing',True,False)
  p.wrap(s.builder,'decode','decode',True,False)
  p.wrap(ep,'atomic','confidence_write',True,False)
  from esm.utils.structure.molecular_complex import MolecularComplex
  p.wrap(MolecularComplex,'to_mmcif','structure_serialization',True,False)
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
  from openfold3.core.runners.writer import OF3OutputWriter
  p.wrap(OF3OutputWriter,'write_all_outputs','output_write',True,False)
  p.wrap(model,'forward','model_total',True,features=True);p.wrap(model,'run_trunk','trunk');p.wrap(model,'_rollout','diffusion')
  for n in ('msa_module','pairformer','aux_heads'):
   if hasattr(model,n):p.wrap(getattr(model,n),'forward',n)
 else:raise ValueError(engine)

 sync()
 return dict(session=s,model=model,profiler=p,sync=sync,load_seconds=time.perf_counter()-loadstart,initialization_seconds=time.perf_counter()-START,torch=torch,spec=spec,root=root)
