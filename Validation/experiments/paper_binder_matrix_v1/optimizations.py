"""Process-local experimental hooks. Never edits installed packages or defaults."""
import copy,functools,random,time,types,shutil,hashlib,json
from pathlib import Path
from common import save

class ExperimentHooks:
 def __init__(self,engine,variant,session,model,profiler,out):
  self.undo=[];self.model=model;self.out=out;self.profiler=profiler;self.cache={};self.hits=0;self.misses=0
  import torch
  self.torch=torch
  if engine in ('openfold3','boltz'):
   from pytorch_lightning.strategies.strategy import Strategy
   from pytorch_lightning.strategies.single_device import SingleDeviceStrategy
   # Diagnostic-only nested timings, normal request measurements remain comparable.
   profiler.wrap(SingleDeviceStrategy,'model_to_device','model_to_device')
   if 'keep' in variant:
    original=Strategy.teardown
    def teardown(strategy,_original=original):
     module=strategy.lightning_module
     if module is None:return _original(strategy)
     # Keep only this inference session's model resident; all other teardown remains.
     assert strategy.optimizers==[]
     had='cpu' in module.__dict__;prior=module.__dict__.get('cpu')
     module.cpu=lambda:module
     try:return _original(strategy)
     finally:
      if had:module.cpu=prior
      else:del module.cpu
    self.patch(Strategy,'teardown',teardown)
   profiler.wrap(Strategy,'teardown','trainer_teardown')
  if engine=='openfold3':
   workers=10 if variant=='baseline' else int(variant.split('_')[0][1:])
   session.data_module_args.num_workers=workers
   if workers==0:
    import numpy as np
    from openfold3.core.data.framework.single_datasets.inference import InferenceDataset
    from openfold3.core.data.framework.data_module import worker_init_function_with_data_seed
    original=InferenceDataset.__getitem__
    def getitem(dataset,index,_original=original):
     # Match the first item's worker0 RNG without changing inference RNG streams.
     pr=random.getstate();nr=np.random.get_state();tr=torch.get_rng_state()
     try:
      worker_init_function_with_data_seed(0,session.data_module_args.data_seed,rank=0)
      return _original(dataset,index)
     finally:random.setstate(pr);np.random.set_state(nr);torch.set_rng_state(tr)
    self.patch(InferenceDataset,'__getitem__',getitem)
    profiler.wrap(InferenceDataset,'__getitem__','featurization',True,False)
    if 'arrays' in variant:
     import ast,inspect,textwrap
     import openfold3.core.data.pipelines.featurization.conformer as conformer
     import openfold3.core.data.framework.single_datasets.inference as inference
     native=conformer.featurize_reference_conformers_of3
     tree=ast.parse(textwrap.dedent(inspect.getsource(native)));changes=[]
     class FastCoordinates(ast.NodeTransformer):
      def visit_Call(self,node):
       self.generic_visit(node)
       if isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='torch' and node.func.attr=='tensor' and len(node.args)==1 and isinstance(node.args[0],ast.Name) and node.args[0].id=='mol_ref_pos':
        changes.append(1)
        return ast.copy_location(ast.Call(func=ast.Name(id='_fast_position_tensor',ctx=ast.Load()),args=node.args,keywords=[]),node)
       return node
     tree=FastCoordinates().visit(tree);assert len(changes)==1
     ast.fix_missing_locations(tree)
     namespace=dict(inspect.unwrap(native).__globals__)
     namespace['_fast_position_tensor']=lambda coords:torch.from_numpy(np.asarray(coords,dtype=np.float32))
     exec(compile(tree,'<experiment-fast-reference-coordinates>','exec'),namespace)
     optimized=namespace['featurize_reference_conformers_of3']
     self.patch(conformer,'featurize_reference_conformers_of3',optimized)
     self.patch(inference,'featurize_reference_conformers_of3',optimized)
    if 'features' in variant:
     build=InferenceDataset.create_all_features
     def features(dataset,query):
      assert len(query.chains)==1 and query.chains[0].molecule_type.name=='PROTEIN'
      payload=query.model_dump(mode='json')
      # Query names identify output directories, not the scientific input.
      if 'keyed' in variant:payload.pop('query_name',None)
      for chain in payload['chains']:
       paths=chain.get('main_msa_file_paths') or []
       assert len(paths)==1 and Path(paths[0]).name=='colabfold_main.a3m'
       chain['main_msa_file_paths']=[hashlib.sha256(Path(paths[0]).read_bytes()).hexdigest()]
      key=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
      if key not in self.cache:self.cache[key]=copy.deepcopy(build(dataset,query));self.misses+=1
      else:self.hits+=1
      # Caller/model cannot mutate cached tensor or metadata storage.
      return copy.deepcopy(self.cache[key])
     self.patch(InferenceDataset,'create_all_features',features)
  if engine=='boltz' and 'prepared' in variant:
   original_process=session.boltz_main.process_inputs
   prepared={}
   def boltz_process(**kw):
    assert not kw['use_msa_server']
    texts=[Path(f).read_text() for f in kw['data']]
    assert all('ligand:' not in t and 'constraints:' not in t and 'templates:' not in t for t in texts)
    dependencies=[]
    for text in texts:
     for line in text.splitlines():
      if line.strip().startswith('msa:'):dependencies.append(hashlib.sha256(Path(line.split(':',1)[1].strip()).read_bytes()).hexdigest())
    key=hashlib.sha256(repr((texts,dependencies,str(kw['mol_dir']),kw['max_msa_seqs'],kw['boltz2'])).encode()).hexdigest()
    destination=Path(kw['out_dir'])/'processed'
    if key in prepared:shutil.copytree(prepared[key],destination,dirs_exist_ok=True);return
    result=original_process(**kw)
    cached=out/'prepared_cache'/key;shutil.copytree(destination,cached);prepared[key]=cached
    return result
   self.patch(session.boltz_main,'process_inputs',boltz_process)
  if engine.startswith('intellifold'):
   import intellifold.data.inference.data_tools as dt
   original=dt.pickle
   def load(file,*a,**k):
    name=Path(file.name);key=(str(name.resolve()),name.stat().st_size,name.stat().st_mtime_ns)
    t=time.perf_counter()
    if 'ccd' in variant and getattr(self,'cache_enabled',True) and key in self.cache:self.hits+=1;result=self.cache[key]
    else:
     self.misses+=1;result=original.load(file,*a,**k)
     if 'ccd' in variant:self.cache[key]=result
    r=profiler.rows.setdefault('ccd_load',dict(calls=0,seconds=0,cpu_seconds=0));r['calls']+=1;r['seconds']+=time.perf_counter()-t
    return result
   self.patch(dt,'pickle',types.SimpleNamespace(load=load))
   if 'prepared' in variant:
    original_process=session.upstream.process_inputs
    prepared={}
    def process(args,**kw):
     # This experiment is explicitly protein-only, no templates/constraints.
     assert not kw['use_msa_server'] and not kw['use_template']
     texts=[Path(f).read_text() for f in kw['data']]
     assert all('ligand:' not in t and 'constraints:' not in t for t in texts)
     dependencies=[]
     for text in texts:
      for line in text.splitlines():
       if line.strip().startswith('msa:'):
        path=Path(line.split(':',1)[1].strip());dependencies.append(hashlib.sha256(path.read_bytes()).hexdigest())
     key=hashlib.sha256(repr((texts,dependencies,str(kw['ccd_path']),kw['max_msa_seqs'],kw['use_pairing'])).encode()).hexdigest()
     destination=Path(kw['out_dir'])/'processed'
     if key in prepared:
      shutil.copytree(prepared[key],destination,dirs_exist_ok=True)
      return
     result=original_process(args,**kw)
     cached=out/'prepared_cache'/key;shutil.copytree(destination,cached);prepared[key]=cached
     return result
    self.patch(session.upstream,'process_inputs',process)

 def patch(self,obj,name,value):
  old=getattr(obj,name);self.undo.append((obj,name,old));setattr(obj,name,value)

 def close(self):
  save(self.out/'cache.json',dict(hits=self.hits,misses=self.misses))
  # Diagnostics wrap patched teardown, so restore patches before final release.
  for obj,name,old in reversed(self.undo):setattr(obj,name,old)
  if hasattr(self.model,'cpu'):self.model.cpu()
  self.cache.clear();self.torch.mps.synchronize();self.torch.mps.empty_cache()
  device=str(next(self.model.parameters()).device) if isinstance(self.model,self.torch.nn.Module) else 'mlx'
  save(self.out/'cleanup.json',dict(model_device=device,mps_bytes=self.torch.mps.driver_allocated_memory()))
