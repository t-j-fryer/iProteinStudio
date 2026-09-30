import hashlib,json,time,functools
from pathlib import Path

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def save(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n');t.replace(p)
class Profiler:
 def __init__(self,sync):self.sync=sync;self.diagnostic=False;self.rows={};self.features=[]
 def reset(self):self.rows={};self.features=[]
 def wrap(self,obj,name,label,always=False,gpu=True,features=False,evaluate=None):
  old=getattr(obj,name)
  @functools.wraps(old)
  def call(*a,**k):
   if features:
    for x in list(a)+[k]+list(k.values()):
     if isinstance(x,dict):
      z=x.get('input_feature_dict',x)
      self.features.append({n:list(v.shape) for n,v in z.items() if 'msa' in n.lower() and hasattr(v,'shape')})
   if not (always or self.diagnostic):return old(*a,**k)
   if gpu:self.sync()
   t=time.perf_counter();c=time.process_time()
   result=old(*a,**k)
   if evaluate:evaluate(result)
   if gpu:self.sync()
   r=self.rows.setdefault(label,dict(calls=0,seconds=0,cpu_seconds=0));r['calls']+=1;r['seconds']+=time.perf_counter()-t;r['cpu_seconds']+=time.process_time()-c
   return result
  setattr(obj,name,call)
