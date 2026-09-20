"""Metal prototype preserving the existing BF16 rounding boundaries.

Distinct from FP32-accumulation fast attention. Independent reference explicitly
models the existing reduced-precision products, sums and probability rounding.
"""
import math
import numpy as np
import mlx.core as mx
from metal_sparse_attention import fused
from rounding_reference import bf16

def rounded(q,k,v,g,B,idx,H):return fused(q,k,v,g,B,idx,H,preserve=True)

def oracle(original):
 rng=np.random.default_rng(1973);rows=[]
 for L,kk,H,d in ((65,33,4,32),(128,128,4,32),(1064,128,4,32)):
  q,k,v,g=[mx.array(rng.normal(size=(L,H*d)).astype('float32'),dtype=mx.bfloat16) for _ in range(4)]
  bias=rng.normal(size=(L,L,H)).astype('float32');bias[:,0,:]=-np.inf
  ii=rng.integers(1,L,size=(L,kk),dtype=np.int32);ii[:,0]=0
  B,idx=mx.array(bias),mx.array(ii)
  old,new=original(q,k,v,g,B,idx,H),rounded(q,k,v,g,B,idx,H);mx.eval(old,new)
  Q,K,V,G=[np.asarray(x.astype(mx.float32)).astype('float64') for x in (q,k,v,g)]
  products=bf16(Q.reshape(L,H,d)[:,:,None,:]*K[ii].reshape(L,kk,H,d).transpose(0,2,1,3))
  scores=(bf16(products.sum(-1)).astype(np.float32)/np.sqrt(np.float32(d))+np.take_along_axis(bias,np.broadcast_to(ii[:,:,None],(L,kk,H)),axis=1).transpose(0,2,1)).astype(np.float64)
  probs=np.exp(scores-scores.max(-1,keepdims=True));probs/=probs.sum(-1,keepdims=True);probs=bf16(probs)
  weighted=bf16(probs[:,:,:,None]*V[ii].reshape(L,kk,H,d).transpose(0,2,1,3))
  ref=bf16(bf16(weighted.sum(2))*G.reshape(L,H,d)).reshape(L,H*d)
  x,y=np.asarray(old.astype(mx.float32)),np.asarray(new.astype(mx.float32))
  relative=float(np.linalg.norm(y-ref)/np.linalg.norm(ref));baseline_relative=float(np.linalg.norm(y-x)/np.linalg.norm(x))
  if not np.isfinite(y).all() or max(relative,baseline_relative)>.001:raise RuntimeError(f'Rounding-preserving attention oracle failed: {relative}, baseline delta {baseline_relative}')
  rows.append(dict(shape=[L,kk,H,d],rounded_oracle_relative_l2=relative,baseline_relative_l2=baseline_relative,passed=True))
 return rows

def install(R):
 evidence=oracle(R._sparse_attn_single);counts={'calls':0,'shapes':{}}
 def call(q,k,v,g,B,idx,H):
  counts['calls']+=1;key=f'{q.shape}/{idx.shape}/{q.dtype}';counts['shapes'][key]=counts['shapes'].get(key,0)+1
  return rounded(q,k,v,g,B,idx,H)
 R._sparse_attn_single=call
 return dict(oracle=evidence,execution=counts,implementation='Direct-load Metal preserving BF16 product, sum and probability rounding boundaries')
