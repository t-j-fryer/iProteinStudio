"""Bounded native-cache diagnostic; no model weights or biological inputs."""
import json,os,subprocess,sys,time
from pathlib import Path
cfg=json.loads(Path(sys.argv[1]).read_text());out=Path(cfg['output']);out.mkdir(exist_ok=True)
code="import torch; print('imported',flush=True); torch.set_num_threads(4); x=torch.randn((8,64,1280),device='mps'); w=torch.randn((1280,1280),device='mps'); b=torch.randn(1280,device='mps'); print('allocated',flush=True); y=torch.nn.functional.linear(x,w,b); torch.mps.synchronize(); print('linear',float(y.cpu().sum()),flush=True); a=torch.randn((64,76,128),device='mps'); z=torch.randn((64,128,76),device='mps'); y=torch.einsum('bij,bjk->bik',a,z); torch.mps.synchronize(); print('einsum',float(y.cpu().sum()),flush=True)"
rows=[]
for variant in ('inherited','no_pycache_prefix','private_pycache','private_tmp'):
 env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
 if variant=='no_pycache_prefix':env.pop('PYTHONPYCACHEPREFIX',None)
 if variant=='private_pycache':
  cache=out/'bytecode';cache.mkdir(exist_ok=True);env['PYTHONPYCACHEPREFIX']=str(cache)
 if variant=='private_tmp':
  cache=out/'tmp';cache.mkdir(exist_ok=True);env['TMPDIR']=str(cache)+'/'
 start=time.monotonic()
 try:
  r=subprocess.run([cfg['python'],'-B','-c',code],env=env,capture_output=True,text=True,timeout=25);row=dict(variant=variant,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
 except subprocess.TimeoutExpired as e:row=dict(variant=variant,timeout=True,stdout=str(e.stdout),stderr=str(e.stderr))
 row['seconds']=time.monotonic()-start;rows.append(row);(out/'probe.json').write_text(json.dumps(rows,indent=2));print(json.dumps(row),flush=True)
