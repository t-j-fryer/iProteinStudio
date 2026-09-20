"""One SIMD group per FP32 row: non-affine LayerNorm + adaptive gate/bias."""
import time
import numpy as np

SOURCE=r'''
#include <metal_stdlib>
using namespace metal;
#pragma clang fp contract(off)
kernel void adaptive_norm(device const float* x, device const float* g,
                          device const float* b, device float* o,
                          constant uint& C, constant float& eps,
                          uint index [[thread_position_in_grid]],
                          uint lane [[thread_index_in_simdgroup]]) {
 uint row=index/32;uint offset=row*C;
 float partial=0.0f;
 for(uint c=lane;c<C;c+=32)partial+=x[offset+c];
 float mean=simd_sum(partial)/float(C);
 float squares=0.0f;
 for(uint c=lane;c<C;c+=32){float d=x[offset+c]-mean;squares+=d*d;}
 float variance=simd_sum(squares)/float(C);
 float inverse=1.0f/precise::sqrt(variance+eps);
 for(uint c=lane;c<C;c+=32){
   uint i=offset+c;float norm=(x[i]-mean)*inverse;
   float scale=1.0f/(1.0f+precise::exp(-g[i]));
   float product=scale*norm;o[i]=product+b[i];
 }
}
'''

class AdaptiveNorm:
    def __init__(self,torch):
        self.torch=torch;self.library=torch.mps.compile_shader(SOURCE);self.constants={};self.counts={}
    def __call__(self,x,g,b,eps=1e-5):
        t=self.torch
        if any(a.dtype!=t.float32 or a.device.type!='mps' for a in (x,g,b)):
            raise RuntimeError('Adaptive Metal norm requires FP32 MPS')
        if t.is_grad_enabled() and any(a.requires_grad for a in (x,g,b)):
            raise RuntimeError('Adaptive Metal norm is inference-only')
        x,g,b=[a.contiguous() for a in t.broadcast_tensors(x,g,b)]
        channels=x.shape[-1]
        if channels<1 or channels>4096 or x.numel()>=2**31:raise RuntimeError('Unsupported adaptive norm shape')
        key=(channels,float(eps))
        if key not in self.constants:
            self.constants[key]=(t.tensor([channels],dtype=t.int32,device='mps'),t.tensor([eps],device='mps'))
        out=t.empty_like(x)
        self.library.adaptive_norm(x,g,b,out,*self.constants[key],threads=(x.numel()//channels)*32,group_size=32)
        label=str(list(x.shape));self.counts[label]=self.counts.get(label,0)+1
        return out

def run(torch):
    t=time.monotonic();op=AdaptiveNorm(torch);compile_seconds=time.monotonic()-t
    rng=np.random.default_rng(421);rows=[]
    for shape in [(19,32,128),(3,96,768),(1,602,128),(7,33),(3,257),(1,228,768)]:
        for regime in ('ordinary','near_constant'):
            a=rng.normal(size=shape).astype('float32')
            if regime=='near_constant':a=(1000+a*.001).astype('float32')
            b,c=[rng.normal(size=shape).astype('float32') for _ in range(2)]
            x,g,z=[torch.from_numpy(v).to('mps') for v in (a,b,c)]
            ref=a.astype('float64');ref=(ref-ref.mean(-1,keepdims=True))/np.sqrt(ref.var(-1,keepdims=True)+1e-5)
            ref=ref/(1+np.exp(-b.astype('float64')))+c
            candidate=lambda:op(x,g,z)
            stock=lambda:torch.sigmoid(g)*torch.nn.functional.layer_norm(x,(shape[-1],),eps=1e-5)+z
            got=candidate().cpu().numpy();old=stock().cpu().numpy()
            error=float(np.linalg.norm((got-ref).ravel())/np.linalg.norm(ref.ravel()))
            stock_error=float(np.linalg.norm((got-old).ravel())/np.linalg.norm(old.ravel()))
            passed=bool(np.isfinite(got).all() and error<=1e-5 and stock_error<=1e-5)
            for _ in range(8):stock();candidate()
            times={'stock':[],'metal':[]}
            for repeat in range(4):
                order=[('stock',stock),('metal',candidate)]
                if repeat%2:order.reverse()
                for label,fn in order:
                    torch.mps.synchronize();t=time.monotonic()
                    for _ in range(20):fn()
                    torch.mps.synchronize();times[label].append((time.monotonic()-t)/20)
            rows.append(dict(shape=shape,regime=regime,oracle_relative_l2=error,stock_relative_l2=stock_error,passed=passed,seconds=times))
    return dict(torch=torch.__version__,compile_seconds=compile_seconds,rows=rows,passed=all(r['passed'] for r in rows))
