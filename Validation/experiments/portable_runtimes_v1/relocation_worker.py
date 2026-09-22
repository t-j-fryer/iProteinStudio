import json,os,sys,time
from pathlib import Path
def main():
 req=json.loads(Path(sys.argv[2]).read_text());root=Path(req['root']);sys.path.insert(0,str(root/'scripts'))
 if req.get('manifest'):
  from runtime_package import verify
  verify(Path(req['manifest']).parent,engine=req['component'])
 if req['engine']=='boltz':
  import torch
  assert torch.backends.mps.is_available()
  torch.set_num_threads(req['threads']);torch.set_num_interop_threads(1)
  out=Path(req['output']);out.mkdir()
  from boltz_worker import run_boltz
  run_boltz(req,out,Path(sys.argv[2]),time.monotonic())
 else:
  from worker import main
  main()

if __name__=='__main__':main()
