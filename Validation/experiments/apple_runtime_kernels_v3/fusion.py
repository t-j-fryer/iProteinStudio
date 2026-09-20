"""Narrow inference fusions; projections, normalization, masks and RNG unchanged."""
import hashlib,inspect
from metal_ops import MetalOps

def install(model,engine,torch, *, lean=False):
    ops=MetalOps(torch, lean=lean)
    evidence=dict(engine=engine,modules={},source_hashes={},calls=ops.counts,aside={})
    for module in model.modules():
        cls=type(module);name=cls.__name__;origin=cls.__module__
        if not origin.startswith(engine+'.'):continue
        old=module.forward
        forward=None
        if engine=='protenix' and name=='AdaptiveLayerNorm':
            def create(m):
                def forward(a,s):
                    a=m.layernorm_a(a);s=m.layernorm_s(s)
                    return ops.call('gate_add',m.linear_s(s),a,m.linear_nobias_s(s))
                return forward
            forward=create(module)
        elif engine=='protenix' and name=='ConditionedTransitionBlock':
            def create(m):
                def forward(a,s):
                    a=m.adaln(a,s)
                    b=ops.call('silu_mul',m.linear_nobias_a1(a),m.linear_nobias_a2(a))
                    return ops.call('gate_mul',m.linear_s(s),m.linear_nobias_b(b))
                return forward
            forward=create(module)
        elif engine=='boltz' and name=='AdaLN':
            def create(m):
                def forward(a,s):
                    a=m.a_norm(a);s=m.s_norm(s)
                    return ops.call('gate_add',m.s_scale(s),a,m.s_bias(s))
                return forward
            forward=create(module)
        elif engine=='boltz' and name=='ConditionedTransitionBlock':
            def create(m):
                def forward(a,s):
                    a=m.adaln(a,s)
                    b=m.swish_gate(a)*m.a_to_b(a)
                    return ops.call('gate_mul',m.output_projection[0](s),m.b_to_a(b))
                return forward
            forward=create(module)
        elif engine in ('boltz','nesso') and name=='Transition':
            def create(m,old):
                def forward(x,chunk_size=None):
                    if chunk_size is not None:
                        evidence['aside']['chunked_transition']=evidence['aside'].get('chunked_transition',0)+1
                        return old(x,chunk_size)
                    x=m.norm(x)
                    return m.fc3(ops.call('silu_mul',m.fc1(x),m.fc2(x)))
                return forward
            forward=create(module,old)
        if forward:
            if module.training:raise RuntimeError('Cannot patch a training module')
            module.forward=forward
            key=origin+'.'+name
            evidence['modules'][key]=evidence['modules'].get(key,0)+1
            evidence['source_hashes'][key]=hashlib.sha256(inspect.getsource(cls.forward).encode()).hexdigest()
    if not evidence['modules']:raise RuntimeError('No eligible modules found')
    return evidence
