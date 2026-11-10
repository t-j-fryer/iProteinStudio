# Ported from the validated RFD4 adapters; see Lab Books 0502, 0506, 0514 and 0538.
"""Experimental inference-only adapters; installed Diffusers stays unchanged.

Grouped projection layout follows native RFD4 _gated_projections at revision
2db07bb444d91695f8c10e6acb7648e9297f9221; the Metal gate/layout experiment is local.
Source and transfer rationale: project Lab Book 0501. No weights are shipped.
"""
import torch
import torch.nn.functional as F


# This kernel is a transpose: the input is channel-fastest, the contraction wants
# position-fastest. Written as a per-output gather (one thread, four reads 4*c
# elements apart) it ran at ~105-118 GB/s against ~460 GB/s achievable on an M4 Max,
# because consecutive threads read addresses 2 KiB apart. Staging a 32x32
# (position x channel) tile through threadgroup memory coalesces both the reads and
# the writes. The arithmetic and its order are unchanged, so output is bit-identical
# to the gather form; the tile is padded to 33 columns to avoid bank conflicts.
# Lab Book 0825 (measured 3.3-5.4x on the kernel, 3.70% of generation).
TILE = 32
METAL = r'''
#include <metal_stdlib>
using namespace metal;
#define TILE 32
kernel void gate_layout(device const bfloat* packed,
                        device const bool* mask,
                        device bfloat* left, device bfloat* right,
                        constant uint& n, constant uint& c,
                        uint3 tg [[threadgroup_position_in_grid]],
                        uint3 tid [[thread_position_in_threadgroup]]) {
    threadgroup bfloat ta[TILE][TILE+1];
    threadgroup bfloat tb[TILE][TILE+1];
    uint spatial = n*n;
    uint batch = tg.z;
    uint pos0 = tg.x*TILE, ch0 = tg.y*TILE;
    uint channel = ch0 + tid.x, pos = pos0 + tid.y;
    if (channel < c && pos < spatial) {
        uint p = (batch*spatial+pos)*4*c + channel;
        bfloat ga = bfloat(1.0f/(1.0f+exp(-float(packed[p+2*c]))));
        bfloat gb = bfloat(1.0f/(1.0f+exp(-float(packed[p+3*c]))));
        bfloat a = bfloat(float(packed[p])*float(ga));
        bfloat b = bfloat(float(packed[p+c])*float(gb));
        bfloat m = bfloat(float(mask[batch*spatial+pos]));
        ta[tid.y][tid.x] = bfloat(float(a)*float(m));
        tb[tid.y][tid.x] = bfloat(float(b)*float(m));
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    uint opos = pos0 + tid.x, och = ch0 + tid.y;
    if (och < c && opos < spatial) {
        uint o = (batch*c + och)*spatial + opos;
        left[o]  = ta[tid.x][tid.y];
        right[o] = tb[tid.x][tid.y];
    }
}
// `values * sigmoid(logits)` as one pass instead of three (sigmoid, then multiply,
// each reading and writing the whole pair tensor). Rounds to bfloat at the same two
// points the eager statement does, so the result is bit-identical. Lab Book 0826.
kernel void gate_mul(device const bfloat* values, device const bfloat* logits,
                     device bfloat* out, uint i [[thread_position_in_grid]]) {
    bfloat s = bfloat(1.0f/(1.0f+exp(-float(logits[i]))));
    out[i] = bfloat(float(values[i])*float(s));
}
'''


def prepare(module):
    names=('linear_a_p','linear_b_p','linear_a_g','linear_b_g')
    for name in names:
        layer=getattr(module,name)
        if type(layer) is not torch.nn.Linear or layer.bias is not None:
            raise ValueError('Only unwrapped bias-free frozen linears supported')
    return torch.cat([getattr(module,n).weight.detach() for n in names]).contiguous()


def grouped(module,pairs,mask,packed=None,shader=None):
    z=module.layer_norm_in(pairs)
    p=F.linear(z,prepare(module) if packed is None else packed)
    if shader is None:
        payload,gate=p.chunk(2,dim=-1)
        a,b=(payload*gate.sigmoid()*mask[...,None]).chunk(2,dim=-1)
        a=a.permute(0,3,1,2);b=b.permute(0,3,1,2)
    else:
        if p.dtype!=torch.bfloat16 or mask.dtype!=torch.bool:
            raise ValueError('Metal adapter requires BF16 and Boolean mask')
        batch,n,_,_=p.shape;c=module.linear_a_p.out_features
        a=torch.empty((batch,c,n,n),device=p.device,dtype=p.dtype);b=torch.empty_like(a)
        spatial=n*n
        shader.gate_layout(p.contiguous(),mask.contiguous(),a,b,n,c,
                           threads=(-(-spatial//TILE)*TILE,-(-c//TILE)*TILE,batch),
                           group_size=(TILE,TILE,1))
    x=torch.matmul(a,b.transpose(-1,-2)) if module.outgoing else torch.matmul(a.transpose(-1,-2),b)
    x=module.linear_z(module.layer_norm_out(x.permute(0,2,3,1)))
    g=module.linear_g(z)
    if shader is None:
        return x*g.sigmoid()
    out=torch.empty_like(x)
    shader.gate_mul(x.contiguous(),g.contiguous(),out,threads=out.numel())
    return out


class Adapter:
    def __init__(self,model,variant):
        self.variant=variant;self.originals=[];self.calls=0
        self.shader=torch.mps.compile_shader(METAL) if variant=='metal_layout' else None
        for module in model.modules():
            if type(module).__name__!='RFD4ProteinaTriangleMultiplication':continue
            old=module.forward
            packed=None if variant=='grouped' else prepare(module)
            def fn(pairs,mask,m=module,p=packed):
                return grouped(m,pairs,mask,p,self.shader)
            if variant in ['compiled','compiled_precise']:
                fn=torch.compile(fn,fullgraph=True,dynamic=False,options={'emulate_precision_casts':variant=='compiled_precise'})
            if variant!='baseline':module.forward=fn
            self.originals.append((module,old))
    def restore(self):
        for module,old in self.originals:module.forward=old
