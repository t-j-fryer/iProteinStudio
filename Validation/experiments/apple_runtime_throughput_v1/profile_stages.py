"""Optional coarse synchronized stage measurements; excluded from speed claims.

Hooks leave tensors and outputs untouched. MPS barriers perturb overlap, so
use these observations only to select follow-up investigations, not as the
unprofiled benchmark's throughput numbers.
"""
from collections import defaultdict
import time


class StageProfile:
    def __init__(self, session, torch):
        self.torch=torch;self.rows=defaultdict(list);self.restores=[];self.svd_calls=[]
        for name in ('input_embedder','template_module','msa_module','pairformer_module','diffusion_conditioning','confidence_module'):
            module=getattr(session.model,name,None)
            if module is not None:self.wrap(module,'forward',name)
        self.wrap(session.model.structure_module,'sample','diffusion_sample')
        self.wrap(session.boltz_main,'process_inputs','preprocessing')
        original=torch.linalg.svd
        def svd(a,*args,**kwargs):
            self.svd_calls.append(dict(shape=list(a.shape),device=str(a.device),dtype=str(a.dtype)))
            return original(a,*args,**kwargs)
        torch.linalg.svd=svd;self.restores.append((torch.linalg,'svd',original))

    def wrap(self,obj,method,label):
        original=getattr(obj,method)
        def timed(*args,**kwargs):
            self.torch.mps.synchronize();before=time.monotonic();cpu=time.process_time()
            try:return original(*args,**kwargs)
            finally:
                self.torch.mps.synchronize()
                self.rows[label].append(dict(seconds=time.monotonic()-before,cpu_seconds=time.process_time()-cpu))
        setattr(obj,method,timed);self.restores.append((obj,method,original))

    def reset(self):
        self.rows.clear();self.svd_calls.clear()

    def report(self):
        return dict(stages={k:dict(calls=len(v),seconds=sum(r['seconds'] for r in v),cpu_seconds=sum(r['cpu_seconds'] for r in v)) for k,v in self.rows.items()},svd_calls=list(self.svd_calls),warning='Synchronized diagnostic only; excludes concurrency and cannot establish GPU kernel duration.')
