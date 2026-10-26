# Ported from the validated RFD4 adapters; see Lab Books 0502, 0506, 0514 and 0538.
"""Experimental exact-output additions to the qualified triangle Metal adapter."""
import inspect
import textwrap
import types
import torch
from .triangle_metal import Adapter as MetalAdapter

PAIR_METAL = r'''
#include <metal_stdlib>
using namespace metal;
kernel void outer_add_mask(device const bfloat* packed, device const bfloat* pairs,
                           device const bool* mask, device bfloat* out,
                           constant uint& n, constant uint& c,
                           uint i [[thread_position_in_grid]]) {
    uint channel=i%c, col=(i/c)%n, row=(i/(c*n))%n, batch=i/(c*n*n);
    bfloat product=bfloat(float(packed[(batch*n+col)*2*c+channel]) *
                          float(packed[(batch*n+row)*2*c+c+channel]));
    bfloat sum=bfloat(float(pairs[i])+float(product));
    out[i]=bfloat(float(sum)*float(mask[i/c]));
}
kernel void add_mask(device const bfloat* pairs, device const bfloat* update,
                     device const bool* mask, device bfloat* out,
                     constant uint& c, uint i [[thread_position_in_grid]]) {
    bfloat sum=bfloat(float(pairs[i])+float(update[i]));
    out[i]=bfloat(float(sum)*float(mask[i/c]));
}
'''


def pair_forward(module, values, pairs, mask, shader):
    if values.dtype != torch.bfloat16 or pairs.dtype != torch.bfloat16 or mask.dtype != torch.bool:
        raise ValueError('BF16 values/pairs and Boolean mask required')
    b,n,c=pairs.shape[0],pairs.shape[1],pairs.shape[-1]
    if pairs.shape!=(b,n,n,c) or mask.shape!=(b,n) or values.shape[:2]!=(b,n):
        raise ValueError('Pair input shape mismatch')
    if any(x.device.type!='mps' for x in (values,pairs,mask)):
        raise ValueError('MPS inputs required')
    pair_mask=(mask[:,:,None] & mask[:,None,:]).contiguous()
    packed=module.linear_x(module.layer_norm_in(values*mask[...,None]))
    out=torch.empty_like(pairs,memory_format=torch.contiguous_format)
    shader.outer_add_mask(packed.contiguous(),pairs.contiguous(),pair_mask,out,n,c,threads=out.numel())
    pairs=out
    for child in (module.tri_mult_out,module.tri_mult_in,module.transition_out):
        update=child(pairs,pair_mask)
        out=torch.empty_like(pairs)
        shader.add_mask(pairs,update.contiguous(),pair_mask,out,c,threads=out.numel())
        pairs=out
    return pairs


class SchedulerAdapter:
    """Private pipeline fast path: immutable schedule, canonical scalar views only.

    Keep upstream tensor math and RNG statements literally unchanged. CPU plans
    replace only control flow. Public installed scheduler code remains untouched.
    """
    def __init__(self,scheduler):
        self.scheduler=scheduler;self.calls=0
        self.old_set=scheduler.set_timesteps;self.old_step=scheduler.step
        source=textwrap.dedent(inspect.getsource(type(scheduler).step))
        replacements={
            'if not torch.equal(timestep, self.timesteps[self._step_index]):':'if not self._incremental_adapter.valid_timestep(timestep):',
            'if t[0] == 0:':'if self._incremental_adapter.flags[index][0]:',
            'if t[0] > self.config.t_lim_ode or t[0] < self.config.t_lim_ode_below:':'if self._incremental_adapter.flags[index][1]:',
        }
        for old,new in replacements.items():
            if source.count(old)!=1:raise RuntimeError('Pinned scheduler source contract changed: '+old)
            source=source.replace(old,new)
        self.source=source
        namespace=dict(type(scheduler).step.__globals__)
        exec(compile(source,'<rfd4-planned-scheduler>','exec'),namespace)
        self.generated=types.MethodType(namespace['step'],scheduler)
        scheduler._incremental_adapter=self
        scheduler.set_timesteps=self.set_timesteps;scheduler.step=self.step
        self.flags=None

    def set_timesteps(self,*args,**kwargs):
        self.old_set(*args,**kwargs);s=self.scheduler
        self.limits=(s.config.t_lim_ode,s.config.t_lim_ode_below)
        self.flags=[(bool(t==0),bool((t>self.limits[0]) | (t<self.limits[1]))) for t in s._times[:-1]]
        self.schedule=s.timesteps

    def valid_timestep(self,t):
        s=self.scheduler
        if (s.config.t_lim_ode,s.config.t_lim_ode_below)!=self.limits:
            raise ValueError('ODE limits changed after schedule planning')
        if s.timesteps is not self.schedule:raise ValueError('Schedule replaced after planning')
        expected=s.timesteps[s._step_index]
        return (t.shape==expected.shape and t.dtype==expected.dtype and t.device==expected.device
                and t.untyped_storage().data_ptr()==expected.untyped_storage().data_ptr()
                and t.storage_offset()==expected.storage_offset())

    def step(self,*args,**kwargs):
        result=self.generated(*args,**kwargs);self.calls+=1;return result

    def restore(self):
        self.scheduler.set_timesteps=self.old_set;self.scheduler.step=self.old_step
        del self.scheduler._incremental_adapter


class Adapter:
    def __init__(self,pipe,variant):
        if variant not in ['baseline','scheduler','pair','combined']:raise ValueError(variant)
        self.base=MetalAdapter(pipe.transformer,'metal_layout');self.originals=[];self.schedulers=[]
        self.pair_calls=0
        if variant in ['pair','combined']:
            shader=torch.mps.compile_shader(PAIR_METAL)
            for module in pipe.transformer.modules():
                if type(module).__name__!='RFD4ProteinaPairUpdate':continue
                self.originals.append((module,module.forward))
                def forward(values,pairs,mask,m=module):
                    self.pair_calls+=1
                    return pair_forward(m,values,pairs,mask,shader)
                module.forward=forward
            if len(self.originals)!=7:raise RuntimeError('Expected seven pair updates')
        if variant in ['scheduler','combined']:
            for s in [pipe.bb_ca_scheduler,pipe.local_latents_scheduler]:self.schedulers.append(SchedulerAdapter(s))

    def restore(self):
        for s in self.schedulers:s.restore()
        for m,old in self.originals:m.forward=old
        self.base.restore()
