"""Fingerprint external model assets without copying weights into the experiment."""
from pathlib import Path
from common import sha


def paths(root, engine):
    root = Path(root)
    if engine == 'boltz':
        files = [root / 'models/boltz2/boltz2_conf.ckpt']
        # Native boltz.data.mol.load_canonicals loads these 21 components for
        # every protein input, including UNK even when no unknown AA is present.
        canonical = 'ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL UNK'.split()
        files += [root / 'models/boltz2/mols' / (name + '.pkl') for name in canonical]
    elif engine == 'intellifold_flash':
        files = [root / 'models/intellifold' / name for name in ('intellifold_v2_flash.pt', 'ccd_v2.pkl')]
    elif engine == 'openfold3':
        files = [root / 'models/openfold3/of3_ft3_v1.pt']
    elif engine.startswith('protenix'):
        component = 'protenix_constraint' if engine == 'protenix_constraint' else 'protenix'
        name = {'protenix_v2': 'protenix-v2.pt', 'protenix_mini': 'protenix_mini_default_v0.5.0.pt',
                'protenix_constraint': 'protenix_base_constraint_v0.5.0.pt'}[engine]
        model_root = root / 'models' / component
        files = [model_root / 'checkpoint' / name]
        files += sorted(p for p in (model_root / 'common').rglob('*') if p.is_file())
    elif engine.startswith('esmfold2'):
        base = root / 'models/esmfold2'
        folder = base / ('ESMFold2-Fast' if engine.endswith('fast') else 'ESMFold2')
        files = [folder / 'model.safetensors', folder / 'config.json', base / 'ESMFold2/ccd.pkl']
        files += sorted((base / 'ESMC-6B').glob('*.safetensors'))
        files += [base / 'ESMC-6B/config.json', base / 'ESMC-6B/model.safetensors.index.json']
    else:
        raise ValueError(engine)
    assert files and all(p.is_file() for p in files), (engine, files)
    return files


def fingerprint(root, engines):
    root = Path(root)
    result, digests = {}, {}
    for engine in engines:
        records = {}
        for path in paths(root, engine):
            resolved = path.resolve()
            if resolved not in digests:
                digests[resolved] = sha(resolved)
            stat = path.stat()
            records[str(path.relative_to(root))] = dict(sha256=digests[resolved], size=stat.st_size, mtime_ns=stat.st_mtime_ns)
        result[engine] = records
    return result


def verify(root, records):
    root = Path(root)
    for relative, record in records.items():
        path = root / relative
        assert path.is_file() and path.stat().st_size == record['size'], ('Missing/changed model asset', relative)
        assert sha(path) == record['sha256'], ('Model asset checksum mismatch', relative)
