"""Atomic batch receipts for Studio NISE's RFdiffusion3 generation path.

The last committed batch owns the seed cursor. Uncommitted output is preserved
separately on restart; completed batches must pass all original file hashes.
"""
import hashlib
import json
from pathlib import Path
import uuid


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def atomic(path, value):
    temporary = path.with_suffix(path.suffix + '.part')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temporary.replace(path)


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
            self.saved = dict(schema=1, input=specification, accepted=0, attempted=0, rejected=[], files={})
            atomic(self.path, self.saved)
        files = self.saved['files']
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
