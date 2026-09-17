"""Atomic batch receipts for Studio NISE's RFdiffusion3 generation path.

The last committed batch owns the seed cursor. Uncommitted output is preserved
separately on restart; completed batches must pass all original file hashes.
"""
import hashlib
import json
import re
from pathlib import Path
import uuid


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.part')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temporary.replace(path)


def bind_inputs(path, specification):
    """Freeze a request before doing work, including an interrupted first attempt."""
    if path.exists():
        if json.loads(path.read_text()) != specification:
            raise RuntimeError(f"RFdiffusion3 inputs changed: {path}. Use a new output directory.")
    else:
        atomic(path, specification)


def save_receipt(path, specification, files):
    files = list(files)
    if not files or any(not p.is_file() or p.stat().st_size == 0 for p in files):
        raise RuntimeError(f"Cannot checkpoint missing/empty RFdiffusion3 artifacts: {path}")
    atomic(path, {"schema": 1, "input": specification,
                  "files": {str(p.absolute()): sha256(p) for p in files}})


def verify_receipt(path, specification):
    if not path.exists():
        return False
    saved = json.loads(path.read_text())
    if saved.get("schema") != 1 or saved.get("input") != specification or not saved.get("files"):
        raise RuntimeError(f"RFdiffusion3 receipt inputs changed or invalid: {path}")
    for name, checksum in saved["files"].items():
        if not Path(name).is_file() or sha256(name) != checksum:
            raise RuntimeError(f"Completed RFdiffusion3 artifact missing or changed: {name}")
    return True


def validate_input_names(output, names):
    if not names or len(names) != len(set(names)):
        raise ValueError("Prediction inputs must have non-empty, unique design names")
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in {".", ".."} for name in names):
        raise ValueError("Unsafe prediction input name")
    stale = {p.stem for p in output.glob("*.yaml")} - set(names)
    if stale:
        raise ValueError(f"Unexpected stale prediction inputs: {sorted(stale)}. Use a new output directory.")


class BatchState:
    def __init__(self, output, specification):
        self.output = Path(output)
        self.path = self.output / 'batch_state.json'
        self.specification = specification
        if self.path.exists():
            self.saved = json.loads(self.path.read_text())
            if self.saved.get('input') != specification or self.saved.get('schema') != 1:
                raise RuntimeError('RFdiffusion3 batch inputs changed')
        else:
            if any((self.output / "results").glob("design_*.json")):
                raise RuntimeError("Legacy RFdiffusion3 outputs have no audited batch receipt; use a new output directory")
            self.saved = dict(schema=1, input=specification, accepted=0, attempted=0, rejected=[], files={})
            atomic(self.path, self.saved)
        files = self.saved['files']
        accepted, attempted = self.saved['accepted'], self.saved['attempted']
        if (type(accepted) is not int or type(attempted) is not int
                or attempted < accepted or attempted < 0):
            raise RuntimeError('Invalid RFdiffusion3 batch seed cursor')
        for name, checksum in files.items():
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise RuntimeError('Invalid RFdiffusion3 batch receipt path')
            path = self.output / name
            if not path.is_file() or sha256(path) != checksum:
                raise RuntimeError('Completed RFdiffusion3 artifact missing or changed: ' + name)
        expected = {f'{folder}/design_{index:04d}.{extension}'
                    for index in range(1, self.saved['accepted'] + 1)
                    for folder, extension in [('backbones', 'pdb'), ('results', 'json')]}
        if set(files) != expected or not 0 <= self.saved['accepted'] <= specification['num_designs']:
            raise RuntimeError('Invalid RFdiffusion3 batch completion count')
        # A crash may occur between writing a PDB and committing the batch. It
        # is safe to replay that uncommitted batch, retaining its raw evidence.
        orphans = [p for folder, glob in [('backbones', '*.pdb'), ('results', '*.json')]
                   for p in (self.output / folder).glob(glob)
                   if str(p.relative_to(self.output)) not in files]
        if orphans:
            archive = self.output / 'interrupted' / uuid.uuid4().hex
            for path in orphans:
                target = archive / path.relative_to(self.output)
                target.parent.mkdir(parents=True, exist_ok=True)
                path.rename(target)

    def commit(self, accepted, attempted, rejected):
        files = dict(self.saved['files'])
        for index in range(self.saved['accepted'] + 1, accepted + 1):
            for folder, extension in [('backbones', 'pdb'), ('results', 'json')]:
                name = f'{folder}/design_{index:04d}.{extension}'
                files[name] = sha256(self.output / name)
        self.saved = dict(schema=1, input=self.specification, accepted=accepted,
                          attempted=attempted, rejected=rejected, files=files)
        atomic(self.path, self.saved)
