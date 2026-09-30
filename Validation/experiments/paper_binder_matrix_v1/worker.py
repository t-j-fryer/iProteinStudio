"""One pinned resident model; atomic audited units and stage timing."""
import os,sys,json,time,resource,subprocess,cProfile,contextlib
from pathlib import Path
from common import save,sha

def audit(structure,binder,target):
 import math,gzip
 import numpy as np
 from validate_prediction_geometry import inspect_geometry,cif_atom_rows,read_cif
 columns,rows=cif_atom_rows(structure);lookup={n.removeprefix('_atom_site.'):i for i,n in enumerate(columns)}
 def field(row,*names):
  return next((row[lookup[n]] for n in names if n in lookup and row[lookup[n]] not in ('.','?')),None)
 aa=dict(zip('ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split(),'ARNDCQEGHILKMFPSTWYV'))
 observed={}
 for row in rows:
  assert all(math.isfinite(float(row[lookup[k]])) for k in ('Cartn_x','Cartn_y','Cartn_z'))
  if field(row,'label_atom_id','auth_atom_id')=='CA':
   chain=field(row,'label_asym_id','auth_asym_id');observed.setdefault(chain,[]).append(aa[field(row,'label_comp_id','auth_comp_id')])
 assert {c:''.join(v) for c,v in observed.items()}=={'A':binder,'B':target},observed
 residues=read_cif(structure)
 assert all({'N','CA','C'}.issubset(v) for v in residues.values())
 files=[p for p in structure.parent.iterdir() if p.is_file() and any(k in p.name for k in ['confidence','full_data','pae','plddt'])]
 assert files,('Missing confidence',structure)
 keys={'ptm','iptm','plddt','avg_plddt','complex_plddt','pae','pde','token_pair_pae','token_pair_pde','atom_plddts','confidence_score','ipsae_min'};seen=set()
 for f in files:
  if f.name.endswith('.json') or f.name.endswith('.json.gz'):
   data=json.loads(gzip.decompress(f.read_bytes()) if f.suffix=='.gz' else f.read_text())
   for k,v in data.items():
    if k in keys and v is not None:assert np.isfinite(np.asarray(v,dtype=float)).all(),(f,k);seen.add(k)
  elif f.suffix=='.npz':
   with np.load(f,allow_pickle=False) as data:
    for k in data.files:assert np.isfinite(data[k]).all(),(f,k)
 assert 'ptm' in seen and any('plddt' in k for k in seen),(structure,seen)
 geometry=inspect_geometry(structure);assert not geometry['errors'],geometry
 return dict(geometry=geometry,files={str(p):sha(p) for p in [structure]+files})

def main():
 cfg=json.loads(Path(sys.argv[1]).read_text());engine=sys.argv[2];out=Path(sys.argv[3]);variant=sys.argv[4]
 out.mkdir(parents=True,exist_ok=True)
 verify_started=time.perf_counter()
 if 'asset_fingerprints' in cfg:
  from assets import verify
  print('ASSET_VERIFY '+engine,flush=True)
  verify(Path(os.environ['NANOHUNTER_ROOT']),cfg['asset_fingerprints'][engine])
 verify_seconds=time.perf_counter()-verify_started
 from engines import initialize
 env=initialize(cfg,engine,out);s=env['session'];model=env['model'];p=env['profiler'];sync=env['sync'];torch=env['torch'];spec=env['spec']
 from optimizations import ExperimentHooks
 session_out=out/'sessions'/str(os.getpid())
 cache_limit_prior=None
 if variant=='cache4g':
  assert engine.startswith('esm')
  import mlx.core as mx
  cache_limit_prior=mx.set_cache_limit(4<<30)
  save(session_out/'memory_policy.json',dict(free_cache_limit_bytes=4<<30,previous_limit_bytes=cache_limit_prior,active_before=mx.get_active_memory(),cache_before=mx.get_cache_memory(),scope='Process-local free allocator cache only; model arithmetic and active weights unchanged'))
 hookvariant=('baseline' if variant=='baseline' else 'w0_keep') if engine=='openfold3' else ('keep' if engine=='boltz' and variant!='baseline' else 'ccd' if engine.startswith('intellifold') and variant!='baseline' else 'baseline')
 hooks=ExperimentHooks(engine,hookvariant,s,model,p,session_out)
 from reuse import Reuse
 reuse=Reuse(engine,s,model,session_out,chain_cache=variant in ('chain','offset'),preserve_positions=variant=='offset') if variant in ('reuse','inference','metal','chain','offset') else None
 positions_undo=None
 template_undo=None
 precision_undo=None
 if variant=='trunk_bf16':
  assert engine=='protenix_v2'
  from precision import install as install_precision
  precision_undo=install_precision(model,session_out)
 if variant in ('templates','templates_diffcache'):
  assert engine=='protenix_v2'
  from template_duplicates import install as install_templates
  template_undo=install_templates(model,session_out)
 if variant in ('diffcache','templates_diffcache'):
  assert engine in ('protenix_v2','protenix_constraint')
  assert model.enable_diffusion_shared_vars_cache is False
  model.enable_diffusion_shared_vars_cache=True
  for c in (s.runner.configs,model.configs):c.enable_diffusion_shared_vars_cache=True
  save(session_out/'diffusion_cache.json',dict(enabled=True,scope='Native upstream invariant conditioning within each prediction; never shared between complexes'))
 if engine=='openfold3' and variant=='positions':
  from positions import install
  positions_undo=install()
 identity=id(model);load=dict(seconds=env['load_seconds'],initialization_seconds=env['initialization_seconds'],asset_verify_seconds=verify_seconds,pid=os.getpid(),engine=engine,variant=variant,model_identity=identity,torch_version=torch.__version__,torch_threads=torch.get_num_threads(),torch_interop_threads=torch.get_num_interop_threads())
 save(session_out/'load.json',load)
 if not (out/'load.json').exists():save(out/'load.json',load)
 selected=cfg['selected_rows'];schedule=[]
 schedule.append((selected[0],42,True,False))
 for i,row in enumerate(selected):
  for seed in (cfg['seeds'] if cfg['phase']=='campaign' else [42+i]):schedule.append((row,seed,False,False))
 if cfg['phase'] not in ('campaign','precision_probe','esm_memory'):schedule.append((selected[-1],46,False,True))
 outputs=[]
 try:
  for number,(row,seed,warmup,diagnostic) in enumerate(schedule):
   tag=f"{row['design_name']}__s{seed}"+('_warmup' if warmup else '_profile' if diagnostic else '')
   unit=out/tag
   if not (unit/'complete.json').exists():
    recovered=sorted(p for p in out.glob(tag+'_retry*') if (p/'complete.json').exists())
    if recovered:unit=recovered[0]
   if (unit/'complete.json').exists():
    receipt=json.loads((unit/'complete.json').read_text())
    assert receipt['seed']==seed and receipt['design_name']==row['design_name']
    assert all(Path(f).is_file() and sha(f)==h for f,h in receipt['files'].items())
    if not warmup:outputs.append(str(unit/'measurement.json'));continue
    # A resumed process must warm its fresh model; never overwrite old warmup.
    unit=out/(tag+f'_restart{os.getpid()}_{time.time_ns()}')
   elif unit.exists():
    # Partial outputs are preserved as an explicit retry, never used as success.
    unit=out/(tag+f'_retry{os.getpid()}_{time.time_ns()}')
   unit_started=time.perf_counter()
   unit.mkdir();target=cfg['targets'][row['target_key']];binder=row['binder_sequence'];sequence=target['sequence'];steps=spec['full'] if engine=='esmfold2_fast' else spec['reduced']
   active=dict(engine=engine,variant=variant,design_name=row['design_name'],seed=seed,unit=str(unit),index=number+1,planned=len(schedule),warmup=warmup,diagnostic=diagnostic,status='running',started_unix=time.time(),pid=os.getpid())
   save(out/'active.json',active);print('UNIT_START '+json.dumps(active),flush=True)
   msa='empty' if engine=='esmfold2_fast' else target['msa']
   if msa!='empty':assert sha(msa)==target['msa_sha256']
   source=unit/'input';source.mkdir();inp=source/'complex.yaml'
   inp.write_text(f'version: 1\nsequences:\n  - protein:\n      id: A\n      sequence: {binder}\n      msa: empty\n  - protein:\n      id: B\n      sequence: {sequence}\n      msa: {msa}\n')
   p.reset();p.diagnostic=True;torch.manual_seed(seed)
   if engine=='boltz':s.request_seed=seed;s.model.predict_args['sampling_steps']=steps
   elif engine.startswith('intellifold'):s.seeds=[seed];s.args.seed=str(seed);s.args.sampling_steps=steps;model.sample_config.no_sample_steps_T=steps
   elif engine.startswith('protenix'):
    s.config['use_msa']=True;s.seeds=[seed]
    for c in (s.runner.configs,model.configs):c.seeds=[seed];c.use_msa=True;c.sample_diffusion.N_step=steps
   elif engine.startswith('esm'):
    import mlx.core as mx,esmfold2_predict as ep
    ep.PROFILES[s.profile]=(spec['recycles'],steps);mx.random.seed(seed)
   elif engine=='openfold3':
    from openfold3.projects.of3_all_atom.config.inference_query_format import InferenceQuerySet
    model.shared.diffusion.no_full_rollout_steps=steps
    for k in ('lightning_data_module','data_module_config'):s.__dict__.pop(k,None)
    s.seeds=[seed];query=unit/'query.json';qname=unit.name.replace('_','-')
    subprocess.run([sys.executable,str(Path(__file__).with_name('openfold_query_json.py')),str(inp),binder,qname,str(query),'','',str(seed)],check=True)
   sync();input_setup_seconds=time.perf_counter()-unit_started;cpu=time.process_time();trace=cProfile.Profile() if diagnostic else None
   if trace:trace.enable()
   start=time.perf_counter()
   with torch.inference_mode() if variant=='inference' else contextlib.nullcontext():
    if engine.startswith('esm'):
     dest=unit/'prediction';dest.mkdir();s.predict([dict(id='A',kind='protein',sequence=binder,msa='empty'),dict(id='B',kind='protein',sequence=sequence,msa=msa)],seed,1,dest,'complex')
    elif engine=='openfold3':s.run(InferenceQuerySet.from_json(query))
    else:s.predict(source,unit/'prediction',1)
   sync();seconds=time.perf_counter()-start;cpu_seconds=time.process_time()-cpu
   if trace:trace.disable();trace.dump_stats(str(unit/'cpu_profile.prof'))
   assert id(model)==identity
   msa_shapes=[x['msa'] for x in p.features if 'msa' in x]
   for shape in msa_shapes:
    token_axis=-2 if shape[-1] in (32,33) else -1
    assert shape[token_axis]==len(binder)+len(sequence),(engine,shape,len(binder),len(sequence))
    if not target['query_only'] and engine!='esmfold2_fast':assert shape[token_axis-1]>1,(engine,shape)
   structroot=out/'predictions'/qname if engine=='openfold3' else unit/'prediction'
   structures={f.resolve() for f in structroot.rglob('*.cif') if 'processed' not in f.parts};assert len(structures)==1,structures
   structure=next(iter(structures));audit_start=time.perf_counter();check=audit(structure,binder,sequence)
   measurement=dict(engine=engine,variant=variant,design_name=row['design_name'],target_key=row['target_key'],seed=seed,steps=steps,recycles=spec['recycles'],warmup=warmup,diagnostic=diagnostic,request_seconds=seconds,input_setup_seconds=input_setup_seconds,unit_seconds_before_checkpoint=time.perf_counter()-unit_started,cpu_seconds=cpu_seconds,stages=p.rows,feature_shapes=p.features,structure=str(structure),geometry=check['geometry'],audit_seconds=time.perf_counter()-audit_start,pid=os.getpid(),model_load_count=1,rss_peak_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,mps_bytes=torch.mps.driver_allocated_memory())
   if engine.startswith('esm'):
    measurement.update(mlx_active_bytes=mx.get_active_memory(),mlx_cache_bytes=mx.get_cache_memory(),mlx_peak_bytes=mx.get_peak_memory())
   save(unit/'measurement.json',measurement);check['files'][str(unit/'measurement.json')]=sha(unit/'measurement.json')
   save(unit/'complete.json',dict(design_name=row['design_name'],seed=seed,files=check['files']))
   save(out/'active.json',{**active,'status':'completed','finished_unix':time.time()})
   outputs.append(str(unit/'measurement.json'));save(out/'progress.json',dict(completed=len(outputs),planned=len(schedule),last=tag))
   print('UNIT '+json.dumps({k:measurement[k] for k in ('engine','variant','design_name','seed','warmup','diagnostic','request_seconds')}),flush=True)
 finally:
  if precision_undo:precision_undo()
  if template_undo:template_undo()
  if positions_undo:positions_undo()
  if reuse:reuse.close()
  hooks.close()
  if cache_limit_prior is not None:
   save(session_out/'memory_final.json',dict(active=mx.get_active_memory(),cache=mx.get_cache_memory(),peak=mx.get_peak_memory()))
   mx.set_cache_limit(cache_limit_prior)
 save(out/'completed.json',dict(outputs=outputs,model_load_count=1,pid=os.getpid()))

if __name__=='__main__':main()
