"""Resident Boltz with atomic, per-input completion markers for directory requests."""
import argparse
from contextlib import contextmanager
import json
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
    if wanted != {p.stem for p in source.glob('*.yaml')} or descriptor['phase'] != phase:
        raise ValueError('Batch descriptor does not match request')
    cls = BoltzAffinityWriter if phase == 'affinity' or descriptor['affinity'] else BoltzWriter
    original = cls.write_on_batch_end
    original_step = session.model.predict_step
    started = {}
    last_event = [time.time()]
    def predict_step(batch, *args, **kwargs):
        for record in batch['record']:
            started[record.id] = time.time()
        return original_step(batch, *args, **kwargs)
    session.model.predict_step = predict_step
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


def main(config):
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
