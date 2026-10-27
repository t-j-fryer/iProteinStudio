"""Pinned Synthyra 600M loader for the existing immutable MLX runtime.

No remote Python is executed. Remapping changes tensor names only; every tensor,
including the adapted confidence head and encoder MLM head, loads strictly.
"""
import hashlib
import json
from pathlib import Path

FOLD_REVISION = '38fa0be7397a485afd4a752202447693098f3d50'
ENCODER_REVISION = 'f813401638b3fddab09748aec1ad2bf537aa4208'


def validate_assets(root):
    root = Path(root)
    items = json.loads(Path(__file__).with_name('runtime_assets.json').read_text())['assets']['esmfold2_600']
    result = {}
    for item in items:
        path = root / item['path']
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(8 << 20), b''): h.update(block)
        if h.hexdigest() != item['sha256']:
            raise ValueError('ESMFold2Fast-600M asset changed: ' + item['path'])
        result[item['path']] = h.hexdigest()
    return dict(folding_revision=FOLD_REVISION, encoder_revision=ENCODER_REVISION,
                confidence='Synthyra adapted v1; Mac calibration unqualified', files=result)


def remap_encoder(weights):
    result = {}
    for key, tensor in weights.items():
        if key.startswith('sequence_head.'):
            target = 'lm_head.' + key.removeprefix('sequence_head.')
        elif key.startswith(('embed.', 'transformer.')):
            target = 'esmc.' + key
            for old, new in (('.attn.layernorm_qkv.0.', '.attn.ln_qkv.'),
                             ('.attn.layernorm_qkv.1.', '.attn.qkv.'),
                             ('.ffn.0.', '.ffn.ln.'), ('.ffn.1.', '.ffn.fc1.'),
                             ('.ffn.3.', '.ffn.fc2.')):
                target = target.replace(old, new)
        else:
            raise ValueError('Unknown ESM++ tensor: ' + key)
        if target in result: raise ValueError('Duplicate mapped ESM++ tensor: ' + target)
        result[target] = tensor
    return result


def sanitize_fold(weights, esmfold2):
    converted = esmfold2.sanitize_esmfold2(weights)
    for key in ('confidence_head.s_norm.weight','confidence_head.s_norm.bias',
                'confidence_head.s_inputs_to_single.weight','confidence_head.s_input_to_s.weight'):
        if key not in weights: raise ValueError('Missing pinned confidence tensor: ' + key)
        converted[key] = weights[key]
    return converted


def load(root, mx, esmfold2, esmc):
    validate_assets(root)
    assets = Path(root) / 'models/esmfold2'
    fold, encoder = assets / 'ESMFold2-600', assets / 'ESMplusplus-large'
    config = json.loads((fold / 'config.json').read_text())
    if (config.get('lm_d_model') != 1152 or config.get('lm_num_layers') != 36
            or config.get('msa_encoder', {}).get('enabled') is not False
            or config.get('confidence_head', {}).get('enabled') is not True
            or config.get('folding_trunk', {}).get('n_layers') != 24):
        raise ValueError('Unsupported 600M architecture')
    tokenizer = json.loads((encoder / 'tokenizer.json').read_text())
    vocab = tokenizer['model']['vocab']
    if any(vocab.get(token) != i for i, token in enumerate(esmc.SEQUENCE_VOCAB)):
        raise ValueError('ESM++ tokenizer differs from MLX ESMC token identities')
    from esmfold2_600_model import Experimental600
    model = Experimental600(config)
    weights = sanitize_fold(mx.load(str(fold / 'model.safetensors')), esmfold2)
    weights = {k: v.astype(mx.float32) if mx.issubdtype(v.dtype, mx.floating) else v for k,v in weights.items()}
    model.load_weights(list(weights.items()), strict=True)
    model.set_dtype(mx.float32); model.eval(); mx.eval(model.parameters())
    del weights
    ecfg = json.loads((encoder / 'config.json').read_text())
    lm = esmc.Model(esmc.ModelArgs.from_dict(ecfg))
    weights = remap_encoder(mx.load(str(encoder / 'model.safetensors')))
    weights = {k: v.astype(mx.bfloat16) if mx.issubdtype(v.dtype, mx.floating) else v for k,v in weights.items()}
    mx.eval(list(weights.values()))
    lm.load_weights(list(weights.items()), strict=True)
    lm.set_dtype(mx.bfloat16); lm.eval(); mx.eval(lm.parameters())
    model._esmc = lm
    return model
