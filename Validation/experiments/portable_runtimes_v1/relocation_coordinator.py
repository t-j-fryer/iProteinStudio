import json,os,subprocess,sys
from pathlib import Path
cfg=json.loads(Path(sys.argv[1]).read_text());out=Path(cfg['output']);f=Path(__file__).resolve().parent;results=[]
for req in cfg['blocks']:
 name=req.get('model',req['engine'])+'-'+req['arm'];path=f/(name+'.json');path.write_text(json.dumps(req,indent=2)+'\n')
 env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',PYTHONNOUSERSITE='1',PYTORCH_ENABLE_MPS_FALLBACK='0',KMP_USE_SHM='0',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',VECLIB_MAXIMUM_THREADS='4',MKL_NUM_THREADS='4',NUMEXPR_NUM_THREADS='4')
 env.pop('IPROTEINSTUDIO_RUNTIME_BINDINGS',None);env.pop('PYTHONPATH',None);env['NANOHUNTER_ROOT']=req['root']
 print('RELOCATION_START|'+name,flush=True)
 with (out/(name+'.log')).open('w') as log:
  r=subprocess.run(([req['python'],str(f/'sequence_smoke.py'),str(path)] if req.get('sequence_test') else [req['python'],str(f/'relocation_worker.py'),'--request',str(path)]),stdout=log,stderr=subprocess.STDOUT,env=env)
 result=dict(engine=req['engine'],arm=req['arm'],returncode=r.returncode);results.append(result)
 (out/'progress.json').write_text(json.dumps(results,indent=2));print('RELOCATION_DONE|'+json.dumps(result),flush=True)
if cfg.get('skip_audit'):raise SystemExit(0 if all(r['returncode']==0 for r in results) else 2)
# Audit runs with a scientific environment, not the minimal control interpreter.
code="""import json,sys;from pathlib import Path;cfg=json.loads(Path(sys.argv[1]).read_text());sys.path.insert(0,str(Path(cfg["blocks"][0]["root"])/"scripts"));from analyse import extract,compare;out=Path(cfg['output']);rows=[]
for engine in dict.fromkeys(r['engine'] for r in cfg['blocks'] if not r.get('sequence_test')):
 try:
  a=extract(out/(engine+'-baseline')/'unit_00',engine);b=extract(out/(engine+'-portable')/'unit_00',engine);r=compare(a,b,engine,cfg['limits']);r['engine']=engine
 except Exception as e:r=dict(engine=engine,passed=False,error=str(e))
 rows.append(r)
for model in dict.fromkeys(r['model'] for r in cfg['blocks'] if r.get('sequence_test')):
 try:
  a=json.loads((out/(model+'-baseline')/'audit.json').read_text());b=json.loads((out/(model+'-portable')/'audit.json').read_text());r=dict(engine=model,passed=a==b,exact=a==b)
 except Exception as e:r=dict(engine=model,passed=False,error=str(e))
 rows.append(r)
(out/'audit.json').write_text(json.dumps(rows,indent=2)+'\\n');print(json.dumps(rows));sys.exit(0 if all(r['passed'] for r in rows) else 2)
"""
python=next(r['python'] for r in cfg['blocks'] if r['engine']=='intellifold-flash' and r['arm']=='portable')
raise SystemExit(subprocess.run([python,'-c',code,sys.argv[1]],cwd=f).returncode)
