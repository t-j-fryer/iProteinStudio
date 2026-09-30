"""Experimental MPS BF16 trunk only; diffusion/confidence remain outside AMP."""
from common import save


def install(model, out):
    import torch
    assert all(p.dtype == torch.float32 for p in model.parameters())
    original = model.get_pairformer_output
    dtypes = set()
    linear = next(m for m in model.pairformer_stack.modules() if isinstance(m, torch.nn.Linear))
    handle = linear.register_forward_hook(lambda module, args, output: dtypes.add(str(output.dtype)))

    def trunk(*args, **kwargs):
        with torch.autocast(device_type='mps', dtype=torch.bfloat16):
            result = original(*args, **kwargs)
        assert isinstance(result, tuple) and len(result) == 3
        return tuple(t.float() for t in result)

    model.get_pairformer_output = trunk

    def undo():
        model.get_pairformer_output = original
        handle.remove()
        save(out / 'precision.json', dict(scope='trunk-only MPS autocast', observed_pairformer_linear_dtypes=sorted(dtypes), stored_weights_fp32=all(p.dtype == torch.float32 for p in model.parameters())))
    return undo
