"""Experimental SDPA sparse attention: same gathered neighbors, bias and gates."""
import math,time
import numpy as np
import mlx.core as mx

def fused(q,k,v,g,B,idx,H):
 L,c=q.shape;kk=idx.shape[-1];d=c//H
 keys=mx.take(k,idx,axis=0).reshape(L,kk,H,d).transpose(0,2,1,3)
 values=mx.take(v,idx,axis=0).reshape(L,kk,H,d).transpose(0,2,1,3)
 bias=mx.take_along_axis(B,mx.broadcast_to(idx[:,:,None],(L,kk,H)),axis=1).transpose(0,2,1)[:,:,None,:]
 # Keep the native FP32 bias and stable softmax. Fused attention accumulates
 # FP32; round its result to the existing activation dtype before the gate.
 result=mx.fast.scaled_dot_product_attention(q.reshape(L,H,1,d).astype(mx.float32),keys.astype(mx.float32),values.astype(mx.float32),scale=1/math.sqrt(d),mask=bias.astype(mx.float32)).astype(q.dtype)
 return (result.reshape(L,H,d)*g.reshape(L,H,d)).reshape(L,c)

def oracle(original,candidate=fused):
 rng=np.random.default_rng(1973);rows=[]
 for L,kk,H,d in [(65,33,4,32),(128,128,4,32)]:
  for dtype in (mx.float32,mx.bfloat16):
   q,k,v,g=[mx.array(rng.normal(size=(L,H*d)).astype('float32'),dtype=dtype) for _ in range(4)]
   B=mx.array(rng.normal(size=(L,L,H)).astype('float32'));idx=mx.array(rng.integers(0,L,size=(L,kk),dtype=np.int32))
   old=original(q,k,v,g,B,idx,H);new=candidate(q,k,v,g,B,idx,H);mx.eval(old,new)
   Q,K,V,G=[np.asarray(x.astype(mx.float32)).astype('float64') for x in (q,k,v,g)];bias=np.asarray(B).astype('float64');ii=np.asarray(idx)
   scores=np.sum(Q.reshape(L,H,d)[:,:,None,:]*K[ii].reshape(L,kk,H,d).transpose(0,2,1,3),axis=-1)/math.sqrt(d)+np.take_along_axis(bias,np.broadcast_to(ii[:,:,None],(L,kk,H)),axis=1).transpose(0,2,1)
   probs=np.exp(scores-scores.max(-1,keepdims=True));probs/=probs.sum(-1,keepdims=True)
   ref=(np.sum(probs[:,:,:,None]*V[ii].reshape(L,kk,H,d).transpose(0,2,1,3),axis=2)*G.reshape(L,H,d)).reshape(L,H*d)
   x,y=np.asarray(old.astype(mx.float32)),np.asarray(new.astype(mx.float32));error=float(np.linalg.norm(y-ref)/np.linalg.norm(ref));limit=1e-5 if dtype==mx.float32 else .01
   assert np.isfinite(y).all() and error<limit,('SDPA independent oracle failed',error,limit)
   durations={}
   for name,fn in [('baseline',original),('candidate',candidate)]:
    t=time.monotonic()
    for _ in range(10):mx.eval(fn(q,k,v,g,B,idx,H))
    mx.synchronize();durations[name]=(time.monotonic()-t)/10
   rows.append(dict(shape=[L,kk,H,d],dtype=str(dtype),reference_relative_l2=error,baseline_reference_relative_l2=float(np.linalg.norm(x-ref)/np.linalg.norm(ref)),max_change=float(np.max(np.abs(y-x))),seconds=durations,passed=True))
 return rows

def install(R):
 evidence=oracle(R._sparse_attn_single);counts={'calls':0,'shapes':{}}
 def call(q,k,v,g,B,idx,H):
  counts['calls']+=1;shape=f'{q.shape}/{idx.shape}/{q.dtype}';counts['shapes'][shape]=counts['shapes'].get(shape,0)+1
  return fused(q,k,v,g,B,idx,H)
 R._sparse_attn_single=call
 return dict(oracle=evidence,execution=counts)
