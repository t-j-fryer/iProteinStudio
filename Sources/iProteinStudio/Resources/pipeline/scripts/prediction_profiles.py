"""Versioned prediction settings shared by native, MCP and CLI entry points.

MSA depth includes the query. Zero means preserve the supplied alignment (Fast
is always sequence-only). Caps preserve input ordering and never edit a cached
alignment. Explicit engine CLI flags take precedence over the profile.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path

ENV = 'IPROTEINSTUDIO_PREDICTION_SETTINGS'
DEFAULTS = json.loads(Path(__file__).with_suffix('.json').read_text())


def normalize(overrides=None):
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict) or set(overrides) - set(DEFAULTS):
        raise ValueError('Unknown prediction engine in prediction_settings.')
    result = {key: dict(value) for key, value in DEFAULTS.items()}
    for engine, values in overrides.items():
        if not isinstance(values, dict) or set(values) - {'msa_depth', 'diffusion_steps', 'recycles'}:
            raise ValueError('Unknown scientific setting for ' + engine)
        for key, value in values.items():
            low = 1 if key == 'diffusion_steps' else 0
            high = {'msa_depth': 1000000, 'diffusion_steps': 10000, 'recycles': 1000}[key]
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f'{engine}.{key} must be an integer from {low} to {high}.')
        result[engine].update(values)
    if result['esmfold2-fast-mlx']['msa_depth'] != 0:
        raise ValueError('ESMFold2 Fast is sequence-only; msa_depth must be zero.')
    return result


def activate(overrides=None):
    settings = normalize(overrides)
    os.environ[ENV] = json.dumps(settings, sort_keys=True, separators=(',', ':'))
    return settings


def profile(engine, model=None):
    if engine == 'intellifold' and model == 'v2':
        engine = 'intellifold-full'
    aliases = {'v2': 'protenix-v2', 'mini': 'protenix-mini',
               'constraint': 'protenix-constraint-v0.5', 'openfold3': 'openfold-3-mlx'}
    engine = aliases.get(engine, engine)
    return normalize(json.loads(os.environ.get(ENV, '{}')))[engine]


def arguments(engine, argv, model=None):
    """Add explicit settings without overriding caller-supplied native flags."""
    settings = profile(engine, model)
    flags = {'boltz': {'diffusion_steps': '--sampling_steps', 'recycles': '--recycling_steps'},
             'intellifold': {'diffusion_steps': '--sampling_steps', 'recycles': '--recycling_iters'}}[engine]
    if engine == 'boltz' and settings['msa_depth']:
        flags['msa_depth'] = '--max_msa_seqs'
    result = list(argv)
    for key, flag in flags.items():
        if not any(a == flag or a.startswith(flag + '=') for a in result):
            result += [flag, str(settings[key])]
    return result


def _atomic(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f'Saved prediction settings or inputs changed: {path}. Start a new run.')
        return
    temp = path.with_name(path.name + f'.{os.getpid()}.part')
    temp.write_bytes(content)
    temp.replace(path)


def record(output, engine, settings):
    _atomic(Path(output) / 'prediction_profile.json',
            (json.dumps(dict(version=1, engine=engine, settings=settings,
                             msa_selection='first rows, query included; original alignment preserved'),
                        sort_keys=True, indent=2) + '\n').encode())
    print('IPROTEINSTUDIO_PREDICTION_SETTINGS|' + engine + '|' + json.dumps(settings, sort_keys=True), flush=True)


def cap_a3m(path, depth, directory):
    """Content-addressed cap. Keep wrapped A3M records and metadata intact."""
    path = Path(path)
    if not depth:
        return path
    raw = path.read_bytes()
    text = raw.decode('utf-8')
    records, prefix = [], []
    for line in text.splitlines(keepends=True):
        if line.startswith('>'):
            records.append([line])
        elif records:
            records[-1].append(line)
        else:
            prefix.append(line)
    if not records or any(not any(line.strip() and not line.startswith('#') for line in r[1:]) for r in records):
        raise ValueError(f'Expected a complete A3M alignment: {path}')
    if len(records) <= depth:
        return path.resolve()
    data = ''.join(prefix + [line for r in records[:depth] for line in r]).encode()
    destination = Path(directory) / (hashlib.sha256(raw + str(depth).encode()).hexdigest() + '.a3m')
    _atomic(destination, data)
    return destination.resolve()


def prepare_inputs(source, output, engine, settings=None):
    """Stage capped YAML dependencies; never modify supplied inputs or cache."""
    import yaml
    settings = settings or profile(engine)
    source, output = Path(source), Path(output)
    record(output, engine, settings)
    depth = settings['msa_depth']
    if not depth:
        return source
    files = [source] if source.is_file() else sorted(source.glob('*.yaml'))
    input_set = hashlib.sha256()
    for path in files:
        input_set.update(path.name.encode() + b'\0' + path.read_bytes() + b'\0')
    destination = output / '_profile_inputs' / input_set.hexdigest() / source.name
    staged = []
    changed = False
    for path in files:
        document = yaml.safe_load(path.read_text())
        for entity in document.get('sequences', []):
            chain = entity.get('protein')
            if not chain:
                continue
            msa = chain.get('msa')
            if msa and str(msa).lower() not in {'empty', 'auto', 'none', 'null'}:
                original = Path(msa).expanduser()
                if not original.is_absolute():
                    original = path.resolve().parent / original
                chain['msa'] = str(cap_a3m(original, depth, output / '_profile_msas'))
                changed = changed or chain['msa'] != str(msa)
        def relocate(value, key=''):
            nonlocal changed
            if isinstance(value, dict):
                return {k: relocate(v, k) for k, v in value.items()}
            if isinstance(value, list):
                return [relocate(v, key) for v in value]
            if isinstance(value, str) and key in {'cif', 'pdb', 'path', 'file', 'target_template_manifest',
                                                  'normalized_mmcif', 'release_dates', 'a3m', 'mmcif_dir'}:
                candidate = Path(value).expanduser()
                if value and not candidate.is_absolute():
                    candidate = path.resolve().parent / candidate
                    if candidate.exists():
                        changed = True
                        return str(candidate.resolve())
            return value
        document = relocate(document)
        target = destination if source.is_file() else destination / path.name
        staged.append((target, yaml.safe_dump(document, sort_keys=False).encode()))
    if not changed:
        return source
    for target, content in staged:
        _atomic(target, content)
    return destination


def effective(engine, argv, model=None):
    result = profile(engine, model)
    flags = {'boltz': {'diffusion_steps': '--sampling_steps', 'recycles': '--recycling_steps'},
             'intellifold': {'diffusion_steps': '--sampling_steps', 'recycles': '--recycling_iters'}}[engine]
    if engine == 'boltz':
        flags['msa_depth'] = '--max_msa_seqs'
    for key, flag in flags.items():
        for i, value in enumerate(argv):
            if value == flag:
                result[key] = int(argv[i + 1])
            elif value.startswith(flag + '='):
                result[key] = int(value.split('=', 1)[1])
    if result['diffusion_steps'] < 1 or result['recycles'] < 0 or result['msa_depth'] < 0:
        raise ValueError('Diffusion steps must be positive; recycles and MSA depth must be nonnegative.')
    return result
