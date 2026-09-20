"""Bounded synchronized samples plus total call/shape census; diagnostic only."""
import functools
import time

def install(model,torch):
    rows={}
    wanted={'AdaLN','AdaptiveLayerNorm','ConditionedTransitionBlock','Transition',
            'AttentionPairBias','TriangleMultiplicationOutgoing','TriangleMultiplicationIncoming',
            'TriangleAttentionStartingNode','TriangleAttentionEndingNode'}
    for module in model.modules():
        name=type(module).__name__
        if name not in wanted:continue
        old=module.forward
        def wrap(old,name):
            @functools.wraps(old)
            def call(*args,**kwargs):
                row=rows.setdefault(name,dict(calls=0,sampled_seconds=[],shapes={}))
                row['calls']+=1
                shapes=str([list(a.shape) for a in args if isinstance(a,torch.Tensor)])
                row['shapes'][shapes]=row['shapes'].get(shapes,0)+1
                sample=len(row['sampled_seconds'])<8
                if sample:torch.mps.synchronize();start=time.monotonic()
                result=old(*args,**kwargs)
                if sample:torch.mps.synchronize();row['sampled_seconds'].append(time.monotonic()-start)
                return result
            return call
        module.forward=wrap(old,name)
    return rows
