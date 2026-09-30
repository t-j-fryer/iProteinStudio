"""Reuse identical template rows within one recycle, preserving native accumulation.

Protenix pads missing templates. Their learned contribution is NOT zero and must
not be removed. Identical rows can reuse one deterministic single-template result.
Never reuse a learned result across recycles, predictions or different features.
"""
import functools
from common import save


def install(model, out):
    import torch
    layer = model.template_embedder
    native_trunk = model.get_pairformer_output
    native_forward = layer.forward
    native_single = layer.single_template_forward
    keys = ('template_aatype', 'template_distogram', 'template_pseudo_beta_mask',
            'template_unit_vector', 'template_backbone_frame_mask')
    groups = None
    cache = None
    stats = dict(predictions=0, native_single_calls=0, reused_single_calls=0, groups=[])

    @functools.wraps(native_trunk)
    def trunk(*args, **kwargs):
        nonlocal groups
        assert groups is None and not layer.training
        features = kwargs.get('input_feature_dict', args[0] if args else None)
        if layer.n_blocks > 0 and 'template_aatype' in features:
            assert all(k in features for k in keys)
            groups = []
            for i in range(features['template_aatype'].shape[0]):
                match = next((j for j in groups if all(torch.equal(features[k][i], features[k][j]) for k in keys)), i)
                groups.append(match)
            stats['groups'].append(groups.copy())
        stats['predictions'] += 1
        try:
            return native_trunk(*args, **kwargs)
        finally:
            groups = None

    @functools.wraps(native_forward)
    def forward(*args, **kwargs):
        nonlocal cache
        assert cache is None and not layer.training
        cache = {}
        try:
            return native_forward(*args, **kwargs)
        finally:
            cache = None

    @functools.wraps(native_single)
    def single(*args, **kwargs):
        template_id = kwargs.get('template_id', args[0] if args else None)
        if groups is None or cache is None:
            return native_single(*args, **kwargs)
        key = groups[template_id]
        if key not in cache:
            cache[key] = native_single(*args, **kwargs)
            stats['native_single_calls'] += 1
        else:
            stats['reused_single_calls'] += 1
        return cache[key]

    model.get_pairformer_output = trunk
    layer.forward = forward
    layer.single_template_forward = single

    def undo():
        model.get_pairformer_output = native_trunk
        layer.forward = native_forward
        layer.single_template_forward = native_single
        save(out / 'template_duplicates.json', stats)
    return undo
