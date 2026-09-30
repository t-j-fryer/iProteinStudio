import json,os,sys,shutil,subprocess,time
from pathlib import Path
from common import save,sha
HERE=Path(__file__).resolve().parent
ENGINES={
 'boltz':dict(component='boltz',full=200,reduced=25,recycles=3),
 'intellifold_flash':dict(component='intellifold',full=200,reduced=25,recycles=10),
 'intellifold_full':dict(component='intellifold',full=200,reduced=25,recycles=10),
 'protenix_v2':dict(component='protenix',full=200,reduced=25,recycles=10),
 'protenix_mini':dict(component='protenix',full=5,reduced=1,recycles=4),
 'protenix_constraint':dict(component='protenix_constraint',full=200,reduced=25,recycles=10),
 'openfold3':dict(component='openfold3',full=200,reduced=25,recycles=3),
 'esmfold2_full':dict(component='esmfold2',full=100,reduced=13,recycles=20),
 'esmfold2_fast':dict(component='esmfold2',full=50,reduced=6,recycles=3)}
def prepare():
 repo=HERE.parents[2];out=repo/'Validation/output/sumo_model_matrix_exact_v1';out.mkdir(exist_ok=False)
 root=Path(os.environ.get('NANOHUNTER_ROOT',Path.home()/'.iproteinstudio'));os.environ['NANOHUNTER_ROOT']=str(root);sys.path.insert(0,str(root/'mcp'))
 from server import MCPServer
 from iprotein_mcp.plans import _persist,_script_provenance
 server=MCPServer('run');save(out/'workflow_guide.json',server.tool_call('workflow_guide',{'workflow':'prediction'}))
 (out/'inputs').mkdir();(out/'frozen').mkdir()
 sequence=json.loads((repo/'Validation/experiments/sumo_binder_four_engine_v1/manifest.json').read_text())['chains']['B']
 for tag,source in [('full',root/'msa_cache/00e99841616c44295043375bc0ba6286.a3m'),('128',repo/'Validation/output/boltz_sumo_msa128_v1/inputs/sumo128.a3m')]:shutil.copy2(source,out/'inputs'/f'{tag}.a3m')
 refdir=repo/'Validation/output/esmfold2_pytorch_compare_v1/paired_20260928T213248054506Z/04_pytorch_resident/inputs'
 for name in ('3QHT.cif','reference.json'):shutil.copy2(refdir/name,out/'inputs'/name)
 ref=json.loads((out/'inputs/reference.json').read_text());assert sha(out/'inputs/3QHT.cif')==ref['sha256'];assert ref['core_indices']==list(range(20,96))
 for p in HERE.iterdir():
  if p.suffix in ('.py','.json'):shutil.copy2(p,out/'frozen'/p.name)
 engines={k:{**v,'python':str((root/'components'/v['component']/'current/python/bin/python3').resolve()),'runtime_manifest_sha256':sha(root/'components'/v['component']/'current/runtime.json')} for k,v in ENGINES.items()}
 cfg=dict(output=str(out),sequence=sequence,engines=engines,msas={k:str(out/'inputs'/f'{k}.a3m') for k in ('128','full')},msa_hashes={k:sha(out/'inputs'/f'{k}.a3m') for k in ('128','full')},seeds=[42,43,44,45,46],normal_predictions=250,diagnostic_replays=50,analysis_python=str(repo/'Validation/output/esmfold2_mlx_update_v1/venv/bin/python'),host={k:subprocess.check_output(c,text=True).strip() for k,c in {'chip':['sysctl','-n','machdep.cpu.brand_string'],'memory':['sysctl','-n','hw.memsize'],'os':['sw_vers'],'commit':['git','-C',str(repo),'rev-parse','HEAD']}.items()})
 cfg['reuse_engine_outputs']={e:str(repo/'Validation/output/sumo_model_matrix_v1'/e) for e in ('boltz','esmfold2_full','esmfold2_fast')}
 cfg['run_order']=['intellifold_full','intellifold_flash','openfold3','protenix_constraint','protenix_mini','protenix_v2']
 cfg['token_sizing']='exact input token count; native internal atom blocks retained'
 save(out/'frozen/config.json',cfg)
 py=str((root/'components/control/current/python/bin/python3').resolve());command=['/usr/bin/caffeinate','-dimsu',py,str(out/'frozen/campaign.py'),'run',str(out/'frozen/config.json')]
 normalized=dict(workflow='runtime_benchmark',engines=list(engines),runtime_python_paths=[v['python'] for v in engines.values()],output=str(out),msa_policy='Exact cached natural SUMO MSAs; none/query-only, frozen128, full8060. Native engine caps retained. Fast sequence-only.',scheduler='One resident process per model; sequential requests; shared exclusive GPU lease.',steps=[dict(stage='sumo-matrix',command=command,cwd=str(out))])
 files=list((out/'frozen').iterdir())+list((out/'inputs').iterdir())+[Path(v['python']) for v in engines.values()]
 plan=_persist('desktop_runtime_benchmark','sumo-model-matrix',normalized,command,'apple_gpu_exclusive',_script_provenance(files));save(out/'plan.json',plan)
 print(json.dumps({k:plan[k] for k in ('id','sha256','normalized_request','command_preview')}),flush=True)
def run(path):
 cfg=json.loads(Path(path).read_text());out=Path(cfg['output']);env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',PYTORCH_ENABLE_MPS_FALLBACK='0',OMP_NUM_THREADS='4',VECLIB_MAXIMUM_THREADS='4',MKL_NUM_THREADS='4',KMP_USE_SHM='0',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
 completed=[];failed=[]
 for engine in cfg['run_order']:
  spec=cfg['engines'][engine]
  dest=out/engine
  if (dest/'completed.json').exists():completed.append(engine);continue
  if dest.exists():raise RuntimeError('Existing incomplete block requires a separately frozen retry: '+str(dest))
  e=env.copy()
  if engine.startswith('intellifold'):e.update(OMP_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
  t=time.perf_counter()
  with (out/(engine+'.log')).open('w') as f:r=subprocess.run([spec['python'],str(Path(__file__).with_name('worker.py')),path,engine,str(dest)],env=e,stdout=f,stderr=subprocess.STDOUT)
  save(out/(engine+'_process.json'),dict(returncode=r.returncode,wall_seconds=time.perf_counter()-t))
  (failed if r.returncode else completed).append(engine)
  save(out/'progress.json',dict(completed=completed,failed=failed))
  print('MATRIX_ENGINE '+engine+' exit='+str(r.returncode),flush=True)
 if failed:raise RuntimeError('Inspect failed engine logs: '+','.join(failed))
 save(out/'completed.json',dict(engines=completed,config_sha256=sha(path)))
if __name__=='__main__':
 if sys.argv[1]=='prepare':prepare()
 else:run(sys.argv[2])
