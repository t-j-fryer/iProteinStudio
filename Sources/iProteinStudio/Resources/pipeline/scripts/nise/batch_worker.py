"""Resident Boltz with atomic, per-input completion markers for directory requests."""
import argparse
from contextlib import contextmanager
import json
import hashlib
import random
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import resident_predictor as resident


@contextmanager
def observe_writers(session, source, output):
    """Emit only after the native writer closes all of an input's output files."""
    from boltz.data.write.writer import BoltzWriter, BoltzAffinityWriter
    source, output = Path(source), Path(output)
    phase = session.request_phase
    batch_root = source.parent
    descriptor = json.loads((batch_root / 'batch.json').read_text())
    wanted = set(descriptor['specifications'])
    deterministic = descriptor.get('rng_policy') == 'per-input-v1'
    restore = []
    feature_hashes = {}
    def input_seed(name):
        spec = descriptor['specifications'][name]
        value = spec.get('prediction_seed')
        if value is None:
            material = json.dumps([descriptor['seed'], name], separators=(',', ':')).encode()
            value = int.from_bytes(hashlib.sha256(material).digest()[:4], 'big') % 2147483647
        return value
    def seed_input(name):
        import numpy as np
        import torch
        value = input_seed(name)
        random.seed(value); np.random.seed(value); torch.manual_seed(value); torch.mps.manual_seed(value)
        return value
    if wanted != {p.stem for p in source.glob('*.yaml')} or descriptor['phase'] != phase:
        raise ValueError('Batch descriptor does not match request')
    cls = BoltzAffinityWriter if phase == 'affinity' or descriptor['affinity'] else BoltzWriter
    original = cls.write_on_batch_end
    original_step = session.model.predict_step
    started = {}
    last_event = [time.time()]
    def predict_step(batch, *args, **kwargs):
        if deterministic:
            if len(batch['record']) != 1: raise ValueError('Per-input seeding requires native batch size one')
            seed_input(batch['record'][0].id)
        for record in batch['record']:
            started[record.id] = time.time()
        return original_step(batch, *args, **kwargs)
    session.model.predict_step = predict_step
    if deterministic:
        import torch
        from boltz.data.module.inferencev2 import PredictionDataset
        original_get = PredictionDataset.__getitem__
        def getitem(dataset, index):
            name = dataset.manifest.records[index].id
            seed_input(name)
            features = original_get(dataset, index)
            if features['record'].id != name:
                raise RuntimeError('Native failed-input substitution is forbidden')
            h = hashlib.sha256()
            for key in sorted(features):
                value = features[key]
                if isinstance(value, torch.Tensor):
                    if value.device.type != 'cpu': raise RuntimeError('Expected CPU input features')
                    h.update(key.encode()); h.update(str(value.dtype).encode()); h.update(str(tuple(value.shape)).encode())
                    h.update(value.contiguous().numpy().tobytes())
            feature_hashes[name] = h.hexdigest()
            return features
        # The affinity checkpoint is a separate model of the same class and may
        # only be loaded later inside predict(). Patch its class for this request.
        if phase == 'affinity':
            model_class = session.boltz_main.Boltz2
            original_affinity_step = model_class.predict_step
            def affinity_step(model, batch, *args, **kwargs):
                if len(batch['record']) != 1: raise ValueError('Expected one affinity input')
                name = batch['record'][0].id
                seed_input(name); started[name] = time.time()
                return original_affinity_step(model, batch, *args, **kwargs)
            model_class.predict_step = affinity_step
            restore.append(lambda: setattr(model_class, 'predict_step', original_affinity_step))
        PredictionDataset.__getitem__ = getitem
        restore.append(lambda: setattr(PredictionDataset, '__getitem__', original_get))
    def write(writer, trainer, module, prediction, batch_indices, batch, batch_idx, dataloader_idx):
        original(writer, trainer, module, prediction, batch_indices, batch, batch_idx, dataloader_idx)
        if prediction.get('exception'):
            raise RuntimeError('Boltz failed to predict a batch input')
        for record in batch['record']:
            name = record.id
            if name not in wanted:
                raise ValueError('Unexpected Boltz output identity')
            leaf = output / 'boltz_results_yaml/predictions' / name
            if phase != 'affinity':
                resident.validate_geometry(session.root, leaf)
            files = sorted(p for p in leaf.rglob('*') if p.is_file())
            processed = output / 'boltz_results_yaml/processed'
            files += [p for p in processed.rglob('*') if p.is_file() and p.stem == name]
            if not files:
                raise ValueError('Native writer did not produce artifacts')
            event = dict(schema=1, name=name, phase=phase,
                yaml_sha256=resident.sha256(source / f'{name}.yaml'),
                rng_policy=descriptor.get('rng_policy'),
                prediction_seed=input_seed(name) if deterministic else None,
                feature_sha256=feature_hashes.get(name),
                resident_identity=dict(pid=__import__('os').getpid(),structure_model=id(session.model),
                    affinity_model=id(session.checkpoints.affinity_model) if getattr(session,'checkpoints',None) and session.checkpoints.affinity_model is not None else None),
                files={str(p.relative_to(batch_root)):resident.sha256(p) for p in files},
                timing=dict(completed_jobs=1, model_load_count=session.model_load_count,
                    start_epoch=started.get(name,last_event[0]), end_epoch=time.time(),
                    wall_seconds=time.time()-started.get(name,last_event[0]),
                    timing_scope='structure model plus writer; affinity interval includes setup for first item',
                    phase=phase, batch_directory=str(batch_root)))
            resident.atomic_json(batch_root / 'items' / f'{name}.json', event)
            last_event[0]=time.time()
            print(f'NISE_BATCH|written|{phase}|{name}', flush=True)
    cls.write_on_batch_end = write
    try:
        yield
    finally:
        cls.write_on_batch_end = original
        session.model.predict_step = original_step
        for cleanup in reversed(restore): cleanup()


def main(config):
    settings = json.loads(Path(config).read_text()) if Path(config).is_file() else {}
    if 'cpu_threads' in settings:
        import torch
        torch.set_num_threads(settings['cpu_threads'])
        torch.set_num_interop_threads(1)
    original = resident.make_session
    def create(settings):
        session = original(settings)
        predict = session.predict
        def batched(source, output, expected):
            with observe_writers(session, source, output):
                return predict(source, output, expected)
        session.predict = batched
        return session
    resident.make_session = create
    resident.serve(Path(config))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True)
    main(parser.parse_args().config)
