"""Per-prediction receipts for resident IntelliFold's unfinished batches.

Reuse requires matching model/settings/code, YAML and local input dependencies,
plus every requested seed/sample's structure and confidence content. Receipts
are committed after annotation/validation; an interrupted item alone is replayed.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            value.update(block)
    return value.hexdigest()


def atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.part')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def input_identity(path: Path) -> dict:
    """Hash local MSA/template files as well as the YAML pointing at them."""
    import yaml
    path = path.resolve()
    dependencies = {}
    seen = set()

    def visit(value, base, key=''):
        if isinstance(value, dict):
            for name, child in value.items():
                visit(child, base, name)
        elif isinstance(value, list):
            for child in value:
                visit(child, base, key)
        elif isinstance(value, str) and key in {'msa', 'cif', 'pdb', 'path', 'file', 'target_template_manifest',
                                                'normalized_mmcif', 'release_dates', 'a3m', 'mmcif_dir'}:
            if value in {'', 'auto', 'empty'}:
                return
            candidate = Path(value).expanduser()
            if not candidate.is_absolute():
                candidate = base / candidate
            candidate = candidate.resolve()
            if key == 'mmcif_dir' and candidate.is_dir():
                dependencies[str(candidate)] = tree_identity(candidate)
                return
            if not candidate.is_file():
                raise RuntimeError(f'Resume dependency missing: {candidate}')
            if candidate in seen:
                return
            seen.add(candidate)
            dependencies[str(candidate)] = digest(candidate)
            if candidate.suffix in {'.json', '.yaml', '.yml'}:
                visit(yaml.safe_load(candidate.read_text()), candidate.parent)

    visit(yaml.safe_load(path.read_text()), path.parent)
    return {'yaml_sha256': digest(path), 'dependencies': dependencies}


def tree_identity(directory: Path, pattern: str = '*') -> dict:
    return {str(path.relative_to(directory)): digest(path)
            for path in sorted(directory.rglob(pattern)) if path.is_file()}


class RecordSeedDataset:
    """Seed feature construction itself, including Accelerate's lookahead read.

    Seeding outside ``next(loader)`` is insufficient: DataLoaderShard reads the
    following record before yielding the current one. Keep the seed boundary
    inside each dataset access instead. The resident route uses zero workers.
    """
    def __init__(self, dataset, seed: int, set_seed):
        self.dataset, self.seed, self.set_seed = dataset, seed, set_seed

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, index):
        self.set_seed(self.seed)
        return self.dataset[index]


def content_digest(path: Path) -> str:
    """Lossless confidence compression does not invalidate a prediction."""
    if path.name.endswith(('.json', '.json.gz')):
        opener = gzip.open if path.suffix == '.gz' else open
        with opener(path, 'rt') as stream:
            value = json.load(stream)
        if not isinstance(value, dict) or not value:
            raise ValueError(f'Empty or invalid confidence document: {path}')
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                        allow_nan=False).encode()).hexdigest()
    return digest(path)


def artifacts(leaf: Path, name: str, seeds: list[int], samples: int, extension: str) -> dict:
    from validate_prediction_geometry import inspect_geometry
    files = {}
    expected_structures = set()
    for seed in seeds:
        for sample in range(samples):
            stem = f'{name}_seed-{seed}_sample-{sample}'
            structure = leaf / (stem + '.' + extension)
            expected_structures.add(structure.name)
            if not structure.is_file() or inspect_geometry(structure)['errors']:
                raise RuntimeError(f'Incomplete or unusable prediction: {structure}')
            files[structure.name] = content_digest(structure)
            for suffix in ['_summary_confidences.json', '_confidences.json']:
                logical = stem + suffix
                # The runner's trajectory materializer consumes plain summaries;
                # only detailed confidence is compressed by the storage policy.
                if suffix == '_summary_confidences.json' and not (leaf / logical).is_file():
                    raise RuntimeError(f'Missing confidence: {leaf / logical}')
                variants = [p for p in [leaf / logical, leaf / (logical + '.gz')] if p.is_file()]
                if not variants:
                    raise RuntimeError(f'Missing confidence: {leaf / logical}')
                values = {content_digest(p) for p in variants}
                if len(values) != 1:
                    raise RuntimeError(f'Conflicting compressed confidence: {leaf / logical}')
                files[logical] = values.pop()
    actual_structures = {p.name for ext in ['cif', 'pdb'] for p in leaf.glob(f'{name}_seed-*_sample-*.{ext}')}
    if actual_structures != expected_structures:
        raise RuntimeError(f'Unexpected seed/sample structures for {name}')
    return files


class PredictionLedger:
    def __init__(self, output: Path, prediction_root: Path, identity: dict,
                 inputs: dict, seeds: list[int], samples: int, extension: str):
        self.path = output / '.prediction_resume' / 'state.json'
        self.prediction_root = prediction_root
        self.inputs = inputs
        self.seeds, self.samples, self.extension = seeds, samples, extension
        # Upstream buckets are tuples; compare their persisted JSON form so a
        # new process does not mistake tuple/list normalization for a change.
        identity = json.loads(json.dumps(
            {**identity, 'seeds': seeds, 'samples': samples, 'extension': extension}, allow_nan=False))
        if not inputs or len(set(seeds)) != len(seeds) or not seeds or samples < 1:
            raise RuntimeError('Invalid prediction checkpoint cardinality')
        if any(Path(name).name != name or name in {'.', '..'} for name in inputs):
            raise RuntimeError('Invalid prediction checkpoint name')
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
            if self.state.get('schema') != 1 or self.state.get('identity') != identity:
                raise RuntimeError('Prediction resume model, settings, or runtime changed; use a new output directory.')
            if any(self.state['inputs'].get(name) != item for name, item in inputs.items()):
                raise RuntimeError('Prediction resume YAML, MSA, template, or batch membership changed; use a new output directory.')
        else:
            if prediction_root.exists() and any(prediction_root.iterdir()):
                raise RuntimeError('Existing predictions have no per-prediction resume provenance; use a new output directory. Original files were kept.')
            self.state = {'schema': 1, 'identity': identity, 'inputs': inputs, 'completed': {}}
            atomic(self.path, self.state)
        # Validate all saved completions, including records omitted because the
        # shell already materialized them before an interruption.
        for name, saved in self.state['completed'].items():
            if name not in self.state['inputs'] or Path(name).name != name or name in {'.', '..'}:
                raise RuntimeError('Invalid completed prediction name in receipt')
            actual = artifacts(prediction_root / name, name, seeds, samples, extension)
            if actual != saved:
                raise RuntimeError(f'Completed prediction changed: {name}; original receipt kept.')

    def complete(self, name: str) -> bool:
        return name in self.state['completed']

    def prepare(self, name: str) -> None:
        if name not in self.inputs:
            raise RuntimeError(f'Prediction was not requested: {name}')
        if self.complete(name):
            raise RuntimeError(f'Refusing to overwrite completed prediction {name}')
        leaf = self.prediction_root / name
        if leaf.exists():
            # The prior intent is known, but the final item was not committed.
            # Retain its partial evidence outside the predictor's scanned tree.
            destination = self.path.parent / 'interrupted' / uuid.uuid4().hex / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(leaf), str(destination))

    def commit(self, name: str) -> None:
        if name not in self.inputs or self.complete(name):
            raise RuntimeError(f'Cannot commit unrequested or completed prediction: {name}')
        self.state['completed'][name] = artifacts(self.prediction_root / name, name,
                                                self.seeds, self.samples, self.extension)
        atomic(self.path, self.state)

    def prepare_features(self, directory: Path, build) -> None:
        """Reuse only the exact processed manifest/MSAs/templates used previously."""
        saved = self.state.get('processed')
        if saved is not None:
            if not directory.is_dir() or tree_identity(directory) != saved:
                raise RuntimeError('Processed prediction inputs changed; original receipt kept.')
            return
        if directory.exists():
            destination = self.path.parent / 'interrupted' / uuid.uuid4().hex / 'processed'
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(directory), str(destination))
        build()
        if not (directory / 'manifest.json').is_file():
            raise RuntimeError('Prediction preprocessing did not produce a manifest')
        self.state['processed'] = tree_identity(directory)
        atomic(self.path, self.state)
