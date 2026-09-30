"""Bounded, process-local candidates for varying binders; no runtime edits."""
import copy,functools,hashlib,sys
from collections import OrderedDict
from pathlib import Path
from common import save

class Reuse:
 def __init__(self,engine,session,model,out,chain_cache=False,preserve_positions=False):
  self.undo=[];self.mapping_undo=[];self.cache=OrderedDict();self.hits=0;self.misses=0;self.out=out
  def identity(x):
   if isinstance(x,Path):return ('file',hashlib.sha256(x.read_bytes()).hexdigest())
   if isinstance(x,str):return ('text',hashlib.sha256(x.encode()).hexdigest())
   if isinstance(x,(int,float,bool,type(None))):return x
   if isinstance(x,(tuple,list)):return tuple(identity(v) for v in x)
   if isinstance(x,dict):return tuple(sorted((k,identity(v)) for k,v in x.items()))
   raise TypeError(f'Unkeyed parser argument {type(x)}')
  def cached(fn):
   @functools.wraps(fn)
   def call(*a,**kw):
    key=(identity(a),identity(kw))
    if key not in self.cache:
     self.cache[key]=copy.deepcopy(fn(*a,**kw));self.misses+=1
     while len(self.cache)>8:self.cache.popitem(last=False)
    else:self.hits+=1;self.cache.move_to_end(key)
    return copy.deepcopy(self.cache[key])
   return call
  if engine=='boltz':self.patch(session.boltz_main,'parse_a3m',cached(session.boltz_main.parse_a3m))
  elif engine.startswith('intellifold'):
   import intellifold.data.inference.data_tools as dt
   self.patch(dt,'parse_a3m',cached(dt.parse_a3m))
  elif engine=='openfold3':
   from openfold3.core.data.io.sequence import msa as msa_io
   original=msa_io.parse_a3m;wrapped=cached(original)
   self.patch(msa_io,'parse_a3m',wrapped)
   self.mapping_undo.append((msa_io.MSA_PARSER_REGISTRY,'.a3m',msa_io.MSA_PARSER_REGISTRY['.a3m']))
   msa_io.MSA_PARSER_REGISTRY['.a3m']=wrapped
  elif engine.startswith('protenix'):
   try:
    from protenix.data.msa.msa_utils import RawMsa
    original=RawMsa.from_a3m;wrapped=cached(original)
    self.patch(RawMsa,'from_a3m',classmethod(lambda cls,*a,**k:wrapped(*a,**k)))
   except ImportError:
    # Constraint has an older upstream parser, discovered separately; no silent hit claim.
    self.unsupported_parser=True
  elif engine.startswith('esm') and chain_cache:
   import numpy as np
   import mlx.core as mx
   original=model.compute_lm_hidden_states
   positional_offset=[0]
   if preserve_positions:
    import mlx.nn as nn
    ropes={id(block.attn.rope) for block in model._esmc.esmc.transformer.blocks}
    native_rope=nn.RoPE.__call__
    def rope_call(rope,x,offset=0):
     if id(rope) in ropes:
      assert offset==0
      offset=positional_offset[0]
     return native_rope(rope,x,offset=offset)
    self.patch(nn.RoPE,'__call__',rope_call)
   def chainwise(input_ids,asym_id=None,residue_index=None,mol_type=None,token_mask=None):
    assert input_ids.shape[0]==1 and asym_id is not None and residue_index is not None
    assert np.all(np.asarray(mol_type)==0)
    if token_mask is not None:assert np.all(np.asarray(token_mask))
    chains=np.asarray(asym_id)[0];parts=[]
    for chain_number,cid in enumerate(dict.fromkeys(chains.tolist())):
     indices=np.flatnonzero(chains==cid);assert np.all(np.diff(indices)==1)
     lo,hi=int(indices[0]),int(indices[-1])+1
     offset=lo+2*chain_number if preserve_positions else 0
     ids=input_ids[:,lo:hi];key=(hashlib.sha256(np.asarray(ids).tobytes()).hexdigest(),offset)
     target=cid==chains[-1]
     if target and key in self.cache:
      self.hits+=1;hidden=self.cache[key];self.cache.move_to_end(key)
     else:
      positional_offset[0]=offset
      try:
       hidden=original(ids,asym_id[:,lo:hi],residue_index[:,lo:hi],mol_type[:,lo:hi],None if token_mask is None else token_mask[:,lo:hi]);mx.eval(hidden)
      finally:positional_offset[0]=0
      if target:
       self.misses+=1;self.cache[key]=hidden
       while sum(v.nbytes for v in self.cache.values())>512*1024**2 and len(self.cache)>1:self.cache.popitem(last=False)
     parts.append(hidden)
    result=mx.concatenate(parts,axis=1);mx.eval(result);return result
   self.patch(model,'compute_lm_hidden_states',chainwise)
 def patch(self,obj,name,value):
  old=obj.__dict__.get(name,getattr(obj,name));self.undo.append((obj,name,old));setattr(obj,name,value)
 def close(self):
  save(self.out/'reuse.json',dict(hits=self.hits,misses=self.misses,entries=len(self.cache),unsupported_parser=getattr(self,'unsupported_parser',False)))
  for mapping,key,old in self.mapping_undo:mapping[key]=old
  for obj,name,old in reversed(self.undo):setattr(obj,name,old)
  self.cache.clear()
