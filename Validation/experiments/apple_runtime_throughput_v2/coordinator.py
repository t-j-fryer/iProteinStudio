"""Sequential isolated workers under the real Studio GPU execution lease."""
import argparse,json,os,subprocess,sys
from pathlib import Path
from worker import atomic,sha

def verify_seal(path,inventory=True):
 s=json.loads(Path(path).read_text());root=Path(s['root'])
 if inventory:
  actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
  if actual!=set(s['files']):raise RuntimeError('Runtime inventory changed')
 for name,h in s['files'].items():
  if sha(root/name)!=h:raise RuntimeError('Sealed file changed: '+name)
 return root

def verify_complete(out,request):
 data=json.loads((out/'completed.json').read_text())
 if data['request_sha256']!=sha(request):raise RuntimeError('Changed completed request')
 actual={str(p.relative_to(out)) for p in out.rglob('*') if p.is_file() and p.name!='completed.json'}
 if actual!=set(data['files']):raise RuntimeError('Changed completed output inventory')
 for n,h in data['files'].items():
  if sha(out/n)!=h:raise RuntimeError('Changed completed output: '+n)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--manifest',type=Path,required=True);a=ap.parse_args();cfg=json.loads(a.manifest.read_text());out=Path(cfg['output'])
 marker=json.loads((out/'studio_job.json').read_text());assert marker.get('plan_id')
 verify_seal(cfg['source_seal'],False)
 runtimes={k:verify_seal(v)/'bin/python' for k,v in cfg['seals'].items()};progress={};failures=[]
 if cfg.get('reused_reference'):
  ref=cfg['reused_reference'];p=Path(ref['output'])
  if sha(p/'completed.json')!=ref['completed_sha256']:raise RuntimeError('Reference receipt changed')
  verify_complete(p,Path(ref['request']));progress[ref['id']]=str(p);atomic(out/'progress.json',progress)
 for b in cfg['blocks']:
  base=out/b['id'];base.mkdir(exist_ok=True);complete=sorted(base.glob('attempt_*/completed.json'))
  if complete:
   attempt=complete[-1].parent;verify_complete(attempt,base/(attempt.name+'.request.json'))
  else:
   n=1
   while (base/f'attempt_{n:03d}').exists():n+=1
   attempt=base/f'attempt_{n:03d}';req=base/(attempt.name+'.request.json')
   request=dict(**b,root=cfg['root'],managed_root=cfg['managed_root'],output=str(attempt))
   if b.get('random_tape')=='replay':
    reference=Path(progress['baseline']);request['random_reference']=str(reference);request['random_reference_receipt_sha256']=sha(reference/'completed.json')
   atomic(req,request)
   env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',PYTHONNOUSERSITE='1',PYTORCH_ENABLE_MPS_FALLBACK='0',KMP_USE_SHM='0')
   for key in ('PYTHONPATH','PYTORCH_MPS_FAST_MATH','PYTORCH_MPS_PREFER_METAL'):env.pop(key,None)
   for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):env[key]=str(b['threads'])
   print('BENCH_START|'+b['id'],flush=True)
   with (base/(attempt.name+'.log')).open('w') as log:
    p=subprocess.Popen([str(runtimes[b['runtime']]),str(Path(__file__).with_name('worker.py')),'--request',str(req)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=env)
    fallback=[]
    for line in p.stdout:
     log.write(line);log.flush();print(line,end='',flush=True)
     if 'cpu' in line.lower() and any(x in line.lower() for x in ('fallback','fall back','falling back')):fallback.append(line.strip())
    code=p.wait()
   atomic(base/(attempt.name+'.execution.json'),dict(exit_code=code,cpu_fallback_lines=fallback))
   if code or fallback:
    failures.append(dict(block=b['id'],exit_code=code,fallback=fallback));atomic(out/'failures.json',failures)
    # A failed baseline makes its candidate uninterpretable; hold this engine, retain diagnostics.
    raise RuntimeError('Worker failed or forbidden fallback; see retained attempt log')
   verify_complete(attempt,req)
  progress[b['id']]=str(attempt);atomic(out/'progress.json',progress)
 atomic(out/'completed.json',dict(blocks=progress,plan=marker))
if __name__=='__main__':main()
