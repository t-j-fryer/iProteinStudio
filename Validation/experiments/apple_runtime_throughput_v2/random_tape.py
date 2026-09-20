"""Diagnostic RNG replay: separate framework arithmetic from changed RNG streams.
Not a production RNG policy and not used for throughput claims.
"""
import json
from pathlib import Path
import numpy as np

class RandomTape:
 def __init__(self,torch,generator,path,reference=None):
  self.torch=torch;self.generator=generator;self.path=Path(path);self.originals={};self.events=[];self.arrays={};self.reference=Path(reference) if reference else None
  self.expected=json.loads(self.reference.with_suffix('.json').read_text()) if self.reference else None
  self.saved=np.load(self.reference) if self.reference else None
 def __enter__(self):
  self.patch(self.torch.Tensor,'normal_');self.patch(self.torch,'rand');self.patch(self.torch,'randn');return self
 def patch(self,obj,name):
  old=getattr(obj,name);self.originals[obj,name]=old
  def call(*args,**kwargs):
   result=old(*args,**kwargs)
   if kwargs.get('generator') is not self.generator:return result
   event=dict(operation=name,shape=list(result.shape),dtype=str(result.dtype));index=len(self.events);key=f'draw_{index:04d}'
   if self.reference:
    if index>=len(self.expected) or event!=self.expected[index]:raise RuntimeError('Random tape call/shape mismatch')
    replacement=self.torch.from_numpy(self.saved[key].copy()).to(device=result.device,dtype=result.dtype)
    if name=='normal_':result.copy_(replacement)
    else:result=replacement
   self.events.append(event);self.arrays[key]=result.detach().cpu().numpy().copy()
   return result
  setattr(obj,name,call)
 def __exit__(self,kind,value,traceback):
  for (obj,name),old in self.originals.items():setattr(obj,name,old)
  if kind is None:
   if self.expected is not None and len(self.events)!=len(self.expected):raise RuntimeError('Random tape not fully consumed')
   np.savez(self.path,**self.arrays);self.path.with_suffix('.json').write_text(json.dumps(self.events,indent=2)+'\n')
  if self.saved is not None:self.saved.close()
