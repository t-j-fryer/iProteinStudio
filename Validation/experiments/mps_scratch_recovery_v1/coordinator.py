"""Bounded paired inference; launched only by the Studio execution broker."""
import json,os,signal,subprocess,sys,time
from pathlib import Path
cfg=json.loads(Path(sys.argv[1]).read_text());out=Path(cfg['output']);f=Path(__file__).parent;rows=[]
for req in cfg['blocks']:
 name=req['arm'];request=f/(name+'.json');request.write_text(json.dumps(req,indent=2))
 env=dict(os.environ,NANOHUNTER_ROOT=req['root'],PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',PYTHONNOUSERSITE='1',PYTORCH_ENABLE_MPS_FALLBACK='0',KMP_USE_SHM='0',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',VECLIB_MAXIMUM_THREADS='4',MKL_NUM_THREADS='4')
 env.pop('IPROTEINSTUDIO_RUNTIME_BINDINGS',None);env.pop('PYTHONPATH',None)
 start=time.monotonic();print('START|'+name,flush=True)
 with (out/(name+'.log')).open('w') as log:
  proc=subprocess.Popen([req['python'],'-B',str(f/'relocation_worker.py'),'--request',str(request)],env=env,stdout=log,stderr=subprocess.STDOUT)
  try:
   rc=proc.wait(timeout=cfg['timeout_seconds']);timed_out=False
  except subprocess.TimeoutExpired:
   timed_out=True
   subprocess.run(['/usr/bin/sample',str(proc.pid),'1','-file',str(out/(name+'-sample.txt'))],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
   proc.terminate()
   try:rc=proc.wait(timeout=10)
   except subprocess.TimeoutExpired:
    proc.kill()
    try:rc=proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
     row=dict(arm=name,timeout=True,termination_pending=True,pid=proc.pid,seconds=time.monotonic()-start);rows.append(row);(out/'progress.json').write_text(json.dumps(rows,indent=2));print(json.dumps(row),flush=True);raise SystemExit(3)
 row=dict(arm=name,returncode=rc,timeout=timed_out,seconds=time.monotonic()-start);rows.append(row)
 (out/'progress.json').write_text(json.dumps(rows,indent=2));print('DONE|'+json.dumps(row),flush=True)
raise SystemExit(0 if all(r['returncode']==0 for r in rows) else 2)
