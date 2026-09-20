"""Explicit experimental arithmetic profile; no production default changes.

Autocast only the diffusion neural network. Checkpoint/parameter storage,
noisy coordinates, diffusion update, alignment, guidance and confidence remain
on their existing FP32 path. Actual activation dtypes are recorded, not inferred
from a precision label. End-to-end practical gates decide eligibility.
"""


def install(session, torch):
    model=session.model.structure_module.score_model
    original=model.forward
    telemetry={'variant':'diffusion_bf16','score_calls':0,'first_linear_output_dtypes':{},'score_output_dtypes':{}}
    first=next(m for m in model.modules() if isinstance(m,torch.nn.Linear))
    def observe(module, inputs, output):
        key=str(output.dtype);counts=telemetry['first_linear_output_dtypes'];counts[key]=counts.get(key,0)+1
    first.register_forward_hook(observe)
    def forward(*args,**kwargs):
        with torch.autocast(device_type='mps',dtype=torch.bfloat16):
            result=original(*args,**kwargs)
        telemetry['score_calls']+=1
        key=str(result.dtype);counts=telemetry['score_output_dtypes'];counts[key]=counts.get(key,0)+1
        return result
    model.forward=forward
    return telemetry
