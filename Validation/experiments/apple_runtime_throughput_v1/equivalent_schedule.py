"""Experimental host-read batching; leave GPU schedule arithmetic and RNG intact.

Never edits an installed package. Binds a narrowly transformed copy of the
sealed upstream method only within an explicitly opted-in benchmark worker.
"""
import inspect
import textwrap
import types

SCHEDULE='sigmas_and_gammas = list(zip(sigmas[:-1], sigmas[1:], gammas[1:]))'
SCALARS='sigma_tm, sigma_t, gamma = sigma_tm.item(), sigma_t.item(), gamma.item()'
REPLACEMENT='sigmas_and_gammas = torch.stack((sigmas[:-1], sigmas[1:], gammas[1:]), dim=1).detach().cpu().tolist()'


def transform(source):
    if source.count(SCHEDULE)!=1 or source.count(SCALARS)!=1:
        raise RuntimeError('Upstream schedule anchors changed; optimization not applied')
    return source.replace(SCHEDULE,REPLACEMENT).replace(SCALARS,'# Scalars retain the identical GPU-computed float32 values, read once above.')


def install(session):
    original=session.model.structure_module.sample
    source=textwrap.dedent(inspect.getsource(original))
    module=inspect.getmodule(original)
    namespace=dict(vars(module))
    exec(compile(transform(source),'<experimental-boltz-host-schedule>','exec'),namespace)
    session.model.structure_module.sample=types.MethodType(namespace['sample'],session.model.structure_module)
    return dict(variant='schedule_host_once',description='Batch host reads of unchanged GPU-computed sigma/gamma values; retain all steps, initial sigma tensor, arithmetic, guidance and RNG calls.',source_module=module.__file__)
