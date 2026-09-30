"""Sequential engine processes under one immutable broker job/GPU lease."""
import json,os,subprocess,sys,time
from pathlib import Path
from common import save

def main():
 cfgpath=Path(sys.argv[1]);cfg=json.loads(cfgpath.read_text());out=Path(cfg['output'])
 results=[]
 for engine,variant in cfg['arms']:
  destination=out/(engine+'__'+variant)
  if destination.exists():raise RuntimeError(f'Refusing overwrite: {destination}')
  command=[cfg['engines'][engine]['python'],str(Path(__file__).with_name('worker.py')),str(cfgpath),engine,str(destination),variant]
  if variant.startswith('batch'):
   command=[cfg['engines'][engine]['python'],str(Path(__file__).with_name('batch_worker.py')),str(cfgpath),str(destination),variant[5:]]
  started=time.time()
  print('ARM_START',engine,variant,flush=True)
  with (out/(engine+'__'+variant+'.log')).open('x') as log:
   r=subprocess.run(command,env=os.environ.copy(),stdout=log,stderr=subprocess.STDOUT)
  results.append(dict(engine=engine,variant=variant,exit_code=r.returncode,elapsed_seconds=time.time()-started))
  save(out/'progress.json',dict(results=results))
  print('ARM_END',json.dumps(results[-1]),flush=True)
 save(out/'finished.json',dict(results=results))
 if any(r['exit_code'] for r in results):raise SystemExit(1)

if __name__=='__main__':main()
