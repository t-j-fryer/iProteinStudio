"""Predict's Guide-mode adapter; reuses the Protein Hunter template preparers.

The public contract is stdlib-only. Preparation runs inside a selected engine's
environment without loading a model. Every generated input is checksummed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import uuid

SUPPORTED = {'boltz', 'intellifold', 'protenix-v2'}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def validate(cfg):
    template = cfg.get('template')
    if template is None:
        return
    if not isinstance(template, dict) or set(template) - {'path', 'chains', 'mode'}:
        raise ValueError('Template settings accept only path, chains and Guide mode.')
    if template.get('mode', 'guide') != 'guide':
        raise ValueError('Only Guide template mode is available.')
    if not isinstance(template.get('path'), str):
        raise ValueError('Choose a template structure file.')
    path = Path(template['path'])
    if not path.is_file() or path.suffix.lower() not in {'.pdb', '.cif', '.mmcif'}:
        raise ValueError('Choose an existing PDB, CIF or mmCIF template file.')
    if any(engine not in SUPPORTED for engine in cfg.get('predictors', [])):
        raise ValueError('Template guidance supports Boltz-2, IntelliFold and Protenix v2 only.')
    chains = template.get('chains')
    if (not isinstance(chains, list) or not chains or any(not isinstance(c, str) for c in chains)
            or len(set(chains)) != len(chains)):
        raise ValueError('Select distinct protein chains to guide in every fold.')
    for job in cfg.get('jobs', []):
        proteins = {c['id']: c for c in job['chains'] if c['kind'] == 'protein'}
        if not set(chains) <= set(proteins):
            raise ValueError(f"{job['name']}: selected template chains must all be protein chains in this fold.")
        by_sequence = {}
        for cid, protein in proteins.items():
            sequence = ''.join(protein['sequence'].split()).upper()
            by_sequence.setdefault(sequence, set()).add(cid in chains)
        if any(len(states) > 1 for states in by_sequence.values()):
            raise ValueError('Identical protein copies share template features; guide all copies or none.')


def atomic(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.part')
    tmp.write_text(json.dumps(document, indent=2, sort_keys=True) + '\n')
    tmp.replace(path)


def prepare(cfg, engine, inputs, output):
    import yaml
    validate(cfg)
    selected = cfg['template']['chains']
    source = Path(cfg['template']['path']).resolve()
    sources = sorted(inputs.glob('*.yaml'))
    docs = {p.stem: yaml.safe_load(p.read_text()) for p in sources}
    if set(docs) != {j['name'] for j in cfg['jobs']}:
        raise ValueError('Template preparation must include exactly the recorded prediction jobs.')
    msa_files = []
    for doc in docs.values():
        for entry in doc['sequences']:
            protein = entry.get('protein')
            if protein and str(protein.get('msa', 'empty')) not in {'empty', 'auto'}:
                msa_files.append(Path(protein['msa']))
    spec = dict(engine=engine, source_sha256=sha256(source), chains=selected, mode='guide',
                inputs={str(p): sha256(p) for p in sources + msa_files})
    receipt = output / 'completed.json'
    if receipt.exists():
        saved = json.loads(receipt.read_text())
        if saved['input'] != spec:
            raise ValueError('Saved template preparation inputs changed.')
        for name, checksum in saved['files'].items():
            path = output / name
            if Path(name).is_absolute() or '..' in Path(name).parts or not path.is_file() or sha256(path) != checksum:
                raise ValueError('Prepared template artifact is missing or changed: ' + name)
        return
    if output.exists():
        output.rename(output.with_name(output.name + '-interrupted-' + uuid.uuid4().hex))
    output.mkdir(parents=True)
    local_source = output / ('source' + source.suffix.lower())
    shutil.copyfile(source, local_source)
    if sha256(local_source) != spec['source_sha256']:
        raise ValueError('Template changed while being copied.')
    manifests = []
    for name, doc in docs.items():
        if engine == 'boltz':
            from prepare_boltz_template import normalize
            cif = output / 'template.cif'
            if not cif.exists():
                normalize(local_source, cif)
            doc['templates'] = [{'cif': str(cif), 'chain_id': selected}]
        elif engine == 'protenix-v2':
            doc['target_template'] = dict(path=str(local_source), sha256=sha256(local_source),
                query_chains=selected, mode='guide', scope='prediction')
        elif engine == 'intellifold':
            from prepare_intellifold_template import prepare as prepare_intellifold
            manifest = prepare_intellifold(local_source, inputs / (name + '.yaml'), output / 'bundles' / name, selected)
            payload = json.loads(manifest.read_text())
            for entry in doc['sequences']:
                protein = entry.get('protein')
                if not protein:
                    continue
                cid = protein['id']
                protein['template'] = payload['a3m_by_query_chain'].get(cid, -1)
                if cid in selected:
                    msa = str(protein.get('msa', 'empty'))
                    target = Path(payload['msa_by_query_chain'][cid])
                    if msa != 'empty':
                        if Path(msa).suffix.lower() != '.a3m':
                            raise ValueError('IntelliFold templates require an A3M alignment or Single sequence.')
                        shutil.copyfile(msa, target)
                    protein['msa'] = str(target)
            manifests.append(payload)
        else:
            raise ValueError('Unsupported template engine: ' + engine)
        path = output / 'inputs' / (name + '.yaml')
        path.parent.mkdir(exist_ok=True)
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
    if manifests:
        # All bundles derive from the same structure and template ID. Keep one
        # featurizer per loaded worker, auditing every job's alignment sidecar.
        combined = dict(manifests[0])
        combined['mappings'] = [mapping for m in manifests for mapping in m['mappings']]
        atomic(output / 'intellifold_manifest.json', combined)
    files = {str(p.relative_to(output)): sha256(p) for p in output.rglob('*') if p.is_file()}
    atomic(receipt, dict(input=spec, files=files))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config', type=Path, required=True)
    ap.add_argument('--engine', choices=sorted(SUPPORTED), required=True)
    ap.add_argument('--inputs', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    prepare(json.loads(args.config.read_text()), args.engine, args.inputs.resolve(), args.output.resolve())
