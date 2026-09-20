"""Small GPU kernel experiment; called only under the Studio shared GPU lease."""
import math,time
import numpy as np
import mlx.core as mx
from worker import atomic

def run(R,out):
 from metal_sparse_attention import fused as metal
 from rfd3_attention import fused as sdpa
 compiled=mx.compile(R._sparse_attn_single)
 functions={'eager':R._sparse_attn_single,'compiled':compiled,'sdpa':sdpa,'metal':metal}
 rng=np.random.default_rng(91019);rows=[]
 for L,kk,H,d in [(65,33,4,32),(128,128,4,32),(512,128,4,32),(1064,128,4,32)]:
  for dtype in (mx.float32,mx.bfloat16):
   args=[mx.array(rng.normal(size=(L,H*d)).astype('float32'),dtype=dtype) for _ in range(4)]
   B=rng.normal(size=(L,L,H)).astype('float32');B[:,0,:]=-np.inf
   idx=rng.integers(1,L,size=(L,kk),dtype=np.int32);idx[:,0]=0
   args += [mx.array(B),mx.array(idx),H];mx.eval(args[:-1]);mx.synchronize()
   Q,K,V,G=[np.asarray(x.astype(mx.float32)).astype('float64') for x in args[:4]]
   s=np.sum(Q.reshape(L,H,d)[:,:,None,:]*K[idx].reshape(L,kk,H,d).transpose(0,2,1,3),axis=-1)/math.sqrt(d)+np.take_along_axis(B,np.broadcast_to(idx[:,:,None],(L,kk,H)),axis=1).transpose(0,2,1)
   p=np.exp(s-s.max(-1,keepdims=True));p/=p.sum(-1,keepdims=True)
   reference=(np.sum(p[:,:,:,None]*V[idx].reshape(L,kk,H,d).transpose(0,2,1,3),axis=2)*G.reshape(L,H,d)).reshape(L,H*d)
   errors={};passes={};compile_times={};samples={k:[] for k in functions};limit=1e-5 if dtype==mx.float32 else .01
   for name,fn in functions.items():
    t=time.monotonic();y=fn(*args);mx.eval(y);mx.synchronize();compile_times[name]=time.monotonic()-t
    a=np.asarray(y.astype(mx.float32));err=float(np.linalg.norm(a-reference)/np.linalg.norm(reference));errors[name]=err
    if not np.isfinite(a).all():raise RuntimeError(f'{name} produced nonfinite output')
    # Keep the same threshold and expose failures. A baseline threshold failure
    # must not prevent measuring the candidate against the independent oracle.
    passes[name]=err<=limit
    for _ in range(10):mx.eval(fn(*args))
    mx.synchronize()
   # Alternating blocks; every reported call includes host dispatch and GPU completion.
   for block in range(4):
    order=list(functions) if block%2==0 else list(reversed(functions))
    for name in order:
     fn=functions[name]
     for _ in range(20):
      mx.synchronize();t=time.perf_counter();mx.eval(fn(*args));mx.synchronize();samples[name].append(time.perf_counter()-t)
   rows.append(dict(shape=[L,kk,H,d],dtype=str(dtype),oracle_relative_l2=errors,oracle_limit=limit,oracle_passed=passes,first_call_seconds=compile_times,median_seconds={k:float(np.median(v)) for k,v in samples.items()},samples_seconds=samples))
   atomic(out/'kernel_benchmark.json',dict(scope='Synthetic sparse-attention operator only; no model speed claim. Identical inputs including irregular/repeated neighbors and a -inf mask; NumPy FP64 oracle. Four alternating-order blocks, 20 synchronized calls per implementation per block, after 10 warmups. Includes dispatch/layout costs; existing FP32/BF16 input/output types.',rows=rows))
