# Ported from the validated RFD4 adapters; see Lab Books 0502, 0506, 0514 and 0538.
"""Experimental inference-only adapters; installed Diffusers stays unchanged.

Grouped projection layout follows native RFD4 _gated_projections at revision
2db07bb444d91695f8c10e6acb7648e9297f9221; the Metal gate/layout experiment is local.
Source and transfer rationale: project Lab Book 0501. No weights are shipped.
"""
import torch
import torch.nn.functional as F


METAL = r'''
#include <metal_stdlib>
using namespace metal;
kernel void gate_layout(device const bfloat* packed,
                        device const bool* mask,
                        device bfloat* left, device bfloat* right,
                        constant uint& n, constant uint& c,
                        uint i [[thread_position_in_grid]]) {
    uint spatial = n*n;
    uint batch = i/(c*spatial);
    uint channel = (i/spatial)%c;
    uint pos = i%spatial;
    uint p = (batch*spatial+pos)*4*c + channel;
    bfloat ga = bfloat(1.0f/(1.0f+exp(-float(packed[p+2*c]))));
    bfloat gb = bfloat(1.0f/(1.0f+exp(-float(packed[p+3*c]))));
    bfloat a = bfloat(float(packed[p])*float(ga));
    bfloat b = bfloat(float(packed[p+c])*float(gb));
    left[i] = bfloat(float(a)*float(mask[batch*spatial+pos]));
    right[i] = bfloat(float(b)*float(mask[batch*spatial+pos]));
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
        shader.gate_layout(p.contiguous(),mask.contiguous(),a,b,n,c,threads=a.numel())
    x=torch.matmul(a,b.transpose(-1,-2)) if module.outgoing else torch.matmul(a.transpose(-1,-2),b)
    x=module.linear_z(module.layer_norm_out(x.permute(0,2,3,1)))
    return x*module.linear_g(z).sigmoid()


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
