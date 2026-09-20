"""CPU-only replay of the exact saved IntelliFold feature-loader arguments."""
import argparse,json,os
from pathlib import Path
from types import SimpleNamespace

def main():
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args()
 import torch
 from accelerate.utils import set_seed
 from intellifold.data.module.inference import get_inference_dataloader
 from intellifold.data.types import Manifest
 torch.set_num_threads(1)
 rows=[]
 for block,value in json.loads((a.run/'progress.json').read_text()).items():
  out=Path(value);effective=json.loads((out/'effective.json').read_text())
  settings=effective['resume_identity']['settings'];args=SimpleNamespace(**settings)
  for unit in sorted(out.glob('unit_*')):
   processed=unit/'prediction/input/processed'
   set_seed(42)
   loader=get_inference_dataloader(args,Manifest.load(processed/'manifest.json'),processed/'structures',processed/'msa',None,None)
   f=next(iter(loader));mask=f['seq_mask']
   assert mask.device.type=='cpu'
   rows.append(dict(block=block,unit=unit.name,buckets=settings['buckets'],seq_mask_shape=list(mask.shape),real_tokens=int(mask.sum()),ref_pos_shape=list(f['ref_pos'].shape),token_bonds_shape=list(f['token_bonds'].shape)))
 target=a.run/'padding_loader_audit.json'
 target.write_text(json.dumps(dict(scope='CPU reconstruction of saved upstream loader; not an inference timing',rows=rows),indent=2)+'\n')
 print(target);print(json.dumps(rows))
if __name__=='__main__':main()
