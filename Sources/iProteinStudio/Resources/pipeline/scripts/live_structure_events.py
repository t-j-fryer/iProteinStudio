"""Atomic, display-only records at native structure-writer completion boundaries.

No model calls, tensors, RNG changes or scientific resume authority. Every file
is relative to the managed campaign and includes a cheap stale-file identity.
"""
from __future__ import annotations
import ast
import functools
import hashlib
import inspect
import json
import os
from pathlib import Path
import runpy
import sys
import time

MODULES = {'boltz.data.write.writer', 'runner.dumper', 'openfold3.core.runners.writer'}


def root():
    value = os.environ.get('IPROTEINSTUDIO_LIVE_RESULTS_ROOT')
    return Path(value).resolve() if value else None


def receipt_path(directory):
    base = root()
    if base is None: return None
    try: relative = Path(directory).resolve().relative_to(base).as_posix()
    except ValueError: return None
    if '_calibration' in Path(relative).parts: return None
    return base / '.studio_live_results' / (hashlib.sha256(relative.encode()).hexdigest() + '.json')


def invalidate(directory):
    path = receipt_path(directory)
    if path: path.unlink(missing_ok=True)


def publish(directory, job, engine, pairs, *, generation=False):
    target = receipt_path(directory)
    if target is None: return
    base = root()
    from validate_prediction_geometry import inspect_geometry
    artifacts = []
    for structure, confidence in pairs:
        structure = Path(structure).resolve()
        if not structure.is_file() or inspect_geometry(structure)['errors']: continue
        stat = structure.stat()
        item = {'structure': structure.relative_to(base).as_posix(),
                'size': stat.st_size, 'mtime_ns': str(stat.st_mtime_ns),
                'mtime': stat.st_mtime, 'sample': structure.stem}
        if confidence:
            confidence = Path(confidence).resolve()
            if not confidence.is_file(): continue
            data = json.loads(confidence.read_text())
            if not isinstance(data, dict): continue
            item['confidence'] = confidence.relative_to(base).as_posix()
        elif not generation:
            continue
        artifacts.append(item)
    if not artifacts: return
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {'schema': 1, 'job': str(job), 'engine': engine,
               'generation': generation, 'artifacts': artifacts, 'updated': time.time()}
    temp = target.with_name(target.name + f'.{os.getpid()}.part')
    temp.write_text(json.dumps(payload, allow_nan=False) + '\n')
    temp.replace(target)


def pairs_in(directory, engine, job, seed=None):
    directory = Path(directory)
    result = []
    for structure in sorted(directory.glob('*.cif')) + sorted(directory.glob('*.pdb')):
        stem = structure.stem
        if engine == 'boltz': confidence = directory / f'confidence_{stem}.json'
        elif engine == 'openfold-3-mlx': confidence = directory / (stem.removesuffix('_model') + '_confidences_aggregated.json')
        elif engine == 'protenix':
            prefix, rank = stem.rsplit('_sample_', 1)
            confidence = directory / f'{prefix}_summary_confidence_sample_{rank}.json'
        else: confidence = directory / f'{stem}_summary_confidences.json'
        if seed is not None and f'_seed-{seed}_' not in stem: continue
        if confidence.is_file(): result.append((structure, confidence))
    return result


def observe(owner, name, locations):
    original = getattr(owner, name)
    if getattr(original, '_studio_live_writer', False): return
    signature = inspect.signature(original)
    @functools.wraps(original)
    def wrapper(*args, **kwargs):
        if root() is None: return original(*args, **kwargs)
        values = signature.bind(*args, **kwargs).arguments
        targets = locations(values)
        for directory, _, _, seed in targets:
            invalidate(Path(directory) / f'.seed-{seed}' if seed is not None else directory)
        result = original(*args, **kwargs)
        if values.get('prediction', {}).get('exception', False): return result
        for directory, job, engine, seed in targets:
            publish(Path(directory) / f'.seed-{seed}' if seed is not None else directory,
                    job, engine, pairs_in(directory, engine, job, seed))
        return result
    wrapper._studio_live_writer = True
    setattr(owner, name, wrapper)


def instrument(module):
    if module.__name__ == 'boltz.data.write.writer':
        observe(module.BoltzWriter, 'write_on_batch_end', lambda v: [
            (Path(v['self'].output_dir) / r.id, r.id, 'boltz', None) for r in v['batch']['record']])
    elif module.__name__ == 'runner.dumper':
        observe(module.DataDumper, 'dump_predictions', lambda v: [
            (Path(v['dump_dir']) / 'predictions', v['pdb_id'], 'protenix', None)])
    elif module.__name__ == 'openfold3.core.runners.writer':
        observe(module.OF3OutputWriter, 'write_all_outputs', lambda v: [
            (Path(v['self'].output_dir) / query / f'seed_{seed}', query, 'openfold-3-mlx', None)
            for query, seed in zip(v['batch']['query_id'], v['batch']['seed'])])


def instrument_intellifold(module):
    observe(module, 'predict_and_save', lambda v: [
        (Path(v['out_dir']) / 'predictions' / v['record'].id, v['record'].id, 'intellifold', v['seed'])])


def run_intellifold(path):
    """Retain the upstream CLI and main body; decorate only its save boundary."""
    if root() is None:
        return runpy.run_path(str(path), run_name='__main__')
    tree = ast.parse(Path(path).read_text(), filename=str(path))
    found = 0
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'predict_and_save':
            node.decorator_list.append(ast.Name(id='_studio_live_decorator', ctx=ast.Load()))
            found += 1
    if found != 1: raise RuntimeError('IntelliFold save boundary changed; live-output adapter needs updating')
    def decorate(function):
        from types import SimpleNamespace
        module = SimpleNamespace(predict_and_save=function)
        instrument_intellifold(module)
        return module.predict_and_save
    namespace = {'__name__': '__main__', '__file__': str(path), '__package__': None,
                 '__cached__': None, '_studio_live_decorator': decorate}
    exec(compile(ast.fix_missing_locations(tree), str(path), 'exec'), namespace)
    return namespace


def publish_backbone(path, index):
    # Each length/queue receives a stable offset matching final flatten order.
    index += int(os.environ.get('IPROTEINSTUDIO_RFD3_LIVE_OFFSET', '0'))
    publish(path, f'design_{index:04d}', 'rfdiffusion3', [(path, None)], generation=True)
