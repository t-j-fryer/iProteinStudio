"""Inference-only FP32 pointwise fusions on the existing Torch MPS stream.

Own implementation; deliberately retain native matrix multiplication/LayerNorm.
Unsupported layouts are made contiguous explicitly and measured in the wrapper.
No training/autograd support, reduced precision, or cross-framework transfers.
"""
SOURCE = r'''
#include <metal_stdlib>
using namespace metal;
#pragma clang fp contract(off)
kernel void gate_mul(device const float* g, device const float* x,
                     device float* o, uint i [[thread_position_in_grid]]) {
  float s = 1.0f / (1.0f + precise::exp(-g[i]));
  o[i] = s * x[i];
}
kernel void gate_add(device const float* g, device const float* x,
                     device const float* b, device float* o,
                     uint i [[thread_position_in_grid]]) {
  float s = 1.0f / (1.0f + precise::exp(-g[i]));
  float p = s * x[i];
  o[i] = p + b[i];
}
kernel void silu_mul(device const float* x, device const float* y,
                     device float* o, uint i [[thread_position_in_grid]]) {
  float s = x[i] / (1.0f + precise::exp(-x[i]));
  o[i] = s * y[i];
}
'''

class MetalOps:
    def __init__(self, torch, *, lean=False):
        self.torch = torch
        self.library = torch.mps.compile_shader(SOURCE)
        self.counts = {}
        self.lean = lean
        self.functions = {name: getattr(self.library, name) for name in ('gate_mul', 'gate_add', 'silu_mul')}

    def call(self, name, *tensors):
        t = self.torch
        if t.is_grad_enabled() and any(x.requires_grad for x in tensors):
            raise RuntimeError('Metal fusion is inference-only')
        if any(x.device.type != 'mps' or x.dtype != t.float32 for x in tensors):
            raise RuntimeError('Metal fusion requires FP32 MPS inputs')
        same = self.lean and all(x.shape == tensors[0].shape for x in tensors[1:])
        values = [x.contiguous() for x in (tensors if same else t.broadcast_tensors(*tensors))]
        out = t.empty_like(values[0])
        if out.numel():
            function = self.functions[name] if self.lean else getattr(self.library, name)
            function(*values, out, threads=out.numel())
        key = name if self.lean else name + ':' + str(list(out.shape))
        self.counts[key] = self.counts.get(key, 0) + 1
        return out
