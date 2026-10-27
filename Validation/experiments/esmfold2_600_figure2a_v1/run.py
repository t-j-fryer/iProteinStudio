"""Serial resident blocks under the immutable Studio broker lease."""
import json,os,subprocess,sys,time,threading
from pathlib import Path
from common import save,sha
from host_load import snapshot,acceptable,audit

def main():
 config=Path(sys.argv[1]);cfg=json.loads(config.read_text());out=Path(cfg['output'])
 for name,digest in cfg['source_hashes'].items():assert sha(Path(__file__).parent/name)==digest,name
 assert sha(Path(__file__).with_name('targets.json'))==cfg['targets_sha256']
 quiet=0
 with (out/('host_preflight_'+str(time.time_ns())+'.jsonl')).open('x') as f:
  for _ in range(120):
   row=snapshot();f.write(json.dumps(row)+'\n');f.flush();quiet=quiet+1 if acceptable(row) else 0
   if quiet==3:break
   print('WAITING_FOR_QUIET_HOST',quiet,round(row['external_cpu_percent'],1),flush=True);time.sleep(5)
  else:raise RuntimeError('Host did not become quiet in ten minutes; no models loaded')
 rows=[];errors=[];done=threading.Event();trace=out/('host_load_'+str(time.time_ns())+'.jsonl')
 def monitor():
  try:
   with trace.open('x') as f:
    while not done.is_set():
     row=snapshot();rows.append(row);f.write(json.dumps(row)+'\n');f.flush();done.wait(5)
  except BaseException as exc:errors.append(repr(exc))
 thread=threading.Thread(target=monitor,daemon=True);thread.start();results=[]
 try:
  for index,block in enumerate(cfg['blocks']):
   dest=out/'blocks'/block['id'];dest.mkdir(parents=True,exist_ok=True)
   if (dest/'completed.json').exists():
    for path in json.loads((dest/'completed.json').read_text())['outputs']:
     receipt=json.loads(Path(path).with_name('complete.json').read_text());assert all(sha(p)==h for p,h in receipt['files'].items())
    results.append(dict(id=block['id'],status='completed',reused=True));continue
   if (dest/'terminal_failure.json').exists():results.append(json.loads((dest/'terminal_failure.json').read_text()));continue
   env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1');env.pop('PYTHONPATH',None)
   env.pop('PYTORCH_MPS_FAST_MATH',None);env.pop('PYTORCH_MPS_PREFER_METAL',None)
   python=Path(env['NANOHUNTER_ROOT'])/'venvs/NanoHunter_esmfold2/bin/python'
   log=dest/('worker_'+str(time.time_ns())+'.log');started=time.time();print('BLOCK_START',block['id'],flush=True)
   with log.open('x') as handle:
    result=subprocess.run([str(python),str(Path(__file__).with_name('worker.py')),str(config),str(index)],env=env,stdout=handle,stderr=subprocess.STDOUT)
   failures=sorted((dest/'sessions').glob('*/failure.json'))
   status='completed' if result.returncode==0 and (dest/'completed.json').exists() else json.loads(failures[-1].read_text())['status'] if failures else 'killed_unknown' if result.returncode<0 else 'error'
   measured=len(list(dest.glob('seed_*/complete.json')))
   record=dict(id=block['id'],status=status,exit_code=result.returncode,seconds=time.time()-started,completed_seeds=measured,unattempted_or_incomplete_seeds=5-measured,log=str(log))
   if status!='completed':save(dest/'terminal_failure.json',record)
   results.append(record);save(out/'progress.json',dict(results=results,planned_blocks=len(cfg['blocks'])));print('BLOCK_END',json.dumps(record),flush=True)
 finally:
  done.set();thread.join();host=audit(rows);host['monitor_errors']=errors;host['trace']=str(trace)
  if errors:host['timing_qualified']=False
  save(out/'host_audit.json',host)
 save(out/'finished.json',dict(results=results,host_audit=host,finished_unix=time.time()))
 if any(r['status']!='completed' for r in results):raise SystemExit(1)
if __name__=='__main__':main()
