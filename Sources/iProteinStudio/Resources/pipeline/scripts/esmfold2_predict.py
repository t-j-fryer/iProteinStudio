#!/usr/bin/env python3
"""Studio I/O adapter for Fausto Milletari's pinned ESMFold2 MLX port.

Model and Biohub feature/decode code are shipped unchanged in the portable
runtime. One loaded model handles a directory; each audited input is committed
atomically and can be resumed. No implicit downloads or CPU model fallback.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import uuid

PORT_REVISION = "c26b9af872158d822a8c95589708eedd3b9c0831"
PROFILES = {"full": (20, 100), "fast": (3, 50)}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''): h.update(block)
    return h.hexdigest()


def atomic(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.part')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temp.replace(path)


def read_input(path, model, unrestrained_check=False):
    import yaml
    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict) or not data.get('sequences'):
        raise ValueError('ESMFold2 requires a nonempty sequences list.')
    if unrestrained_check:
        # Explicit independent verification contract: remove design-only guidance
        # and Boltz-only affinity requests; Fast additionally has no MSA encoder.
        for key in ('constraints', 'properties', 'templates', 'target_template'):
            data.pop(key, None)
        if model == 'fast':
            for item in data['sequences']:
                if 'protein' in item: item['protein']['msa'] = 'empty'
    unsupported = set(data) - {'version', 'sequences'}
    if unsupported:
        raise ValueError('ESMFold2 does not support affinity, templates or restraints: ' + ', '.join(sorted(unsupported)))
    chains, ids, msas = [], set(), {}
    for entry in data['sequences']:
        if not isinstance(entry, dict) or len(entry) != 1:
            raise ValueError('Each sequence entry must contain one protein or ligand.')
        kind, item = next(iter(entry.items()))
        if kind not in {'protein', 'ligand'} or not isinstance(item, dict):
            raise ValueError('Studio ESMFold2 supports protein chains and SMILES ligands.')
        allowed = {'id', 'sequence', 'msa'} if kind == 'protein' else {'id', 'smiles'}
        if set(item) - allowed: raise ValueError('Unsupported ESMFold2 chain options: ' + str(set(item) - allowed))
        cid = item.get('id')
        if not isinstance(cid, str) or not cid or cid in ids:
            raise ValueError('ESMFold2 requires unique chain IDs.')
        ids.add(cid)
        if kind == 'protein':
            sequence = ''.join(str(item.get('sequence', '')).split()).upper()
            if not sequence or set(sequence) - set('ACDEFGHIKLMNPQRSTVWY'):
                raise ValueError('ESMFold2 requires complete amino-acid sequences; X-token hallucination is not supported.')
            msa = str(item.get('msa', 'empty'))
            if model == 'fast' and msa != 'empty':
                raise ValueError('ESMFold2 Fast is sequence-only. Prepare an explicitly sequence-only input.')
            if msa != 'empty':
                p = Path(msa)
                if not p.is_absolute(): p = Path(path).parent / p
                if not p.is_file(): raise ValueError('Requested ESMFold2 MSA is missing: ' + str(p))
                records = p.read_text().split('>')
                if len(records) < 2: raise ValueError('Requested MSA is not A3M: ' + str(p))
                query = records[1].splitlines()[1:]
                query = ''.join(c for c in ''.join(query) if c.isupper())
                if query != sequence: raise ValueError('ESMFold2 MSA query does not match chain ' + cid)
                msas[str(p.resolve())] = sha(p)
                msa = str(p.resolve())
            chains.append(dict(kind=kind, id=cid, sequence=sequence, msa=msa))
        else:
            smiles = str(item.get('smiles', '')).strip()
            if not smiles: raise ValueError('Ligands require a SMILES string.')
            chains.append(dict(kind=kind, id=cid, smiles=smiles))
    if not any(c['kind'] == 'protein' for c in chains): raise ValueError('At least one protein chain is required.')
    return chains, msas


def ligand_atom_maps(chains):
    """Mirror upstream SMILES atom naming; preserve input-order identity for NISE."""
    from rdkit import Chem, rdBase
    records = {}
    for c in chains:
        if c['kind'] != 'ligand': continue
        mol = Chem.MolFromSmiles(c['smiles'])
        if mol is None: raise ValueError('Invalid ligand SMILES')
        mol = Chem.AddHs(mol)
        ranks = Chem.CanonicalRankAtoms(mol)
        records[c['id']] = dict(smiles=c['smiles'], rdkit_version=rdBase.rdkitVersion,
            atoms=[dict(index=i, el=a.GetSymbol(), name=a.GetSymbol().upper()+str(ranks[a.GetIdx()]+1))
                   for i, a in enumerate(a for a in mol.GetAtoms() if a.GetAtomicNum()!=1)])
    return records


def complete(directory, identity):
    try:
        record = json.loads((directory / 'complete.json').read_text())
        return (record['identity'] == identity and bool(record['files'])
                and all((directory / name).is_file() and sha(directory / name) == digest
                        for name, digest in record['files'].items()))
    except (OSError, ValueError, KeyError): return False


class Session:
    def __init__(self, root, model):
        import torch
        import mlx.core as mx
        from mlx_lm.models import esmc, esmfold2
        from esm.models.esmfold2 import ESMFold2InputBuilder
        if not mx.metal.is_available(): raise RuntimeError('ESMFold2 requires Apple Metal; CPU prediction is unavailable.')
        mx.set_default_device(mx.gpu)
        torch.set_num_threads(4)
        assets = Path(root) / 'models/esmfold2'
        fold = assets / ('ESMFold2-Fast' if model == 'fast' else 'ESMFold2')
        encoder = assets / 'ESMC-6B'
        # Match the tested checkpoint layout, precision and strict loading.
        self.model = esmfold2.ESMFold2Model(json.loads((fold / 'config.json').read_text()))
        weights = esmfold2.sanitize_esmfold2(mx.load(str(fold / 'model.safetensors')))
        weights = {k: v.astype(mx.float32) if mx.issubdtype(v.dtype, mx.floating) else v for k, v in weights.items()}
        self.model.load_weights(list(weights.items()), strict=True)
        self.model.set_dtype(mx.float32); self.model.eval(); mx.eval(self.model.parameters())
        del weights
        lm = esmc.Model(esmc.ModelArgs.from_dict(json.loads((encoder / 'config.json').read_text())))
        weights = {}
        for shard in sorted(encoder.glob('*.safetensors')):
            part = {k: v.astype(mx.bfloat16) if mx.issubdtype(v.dtype, mx.floating) else v for k, v in mx.load(str(shard)).items()}
            mx.eval(list(part.values())); weights.update(part)
        lm.load_weights(list(lm.sanitize(weights).items()), strict=True)
        lm.set_dtype(mx.bfloat16); lm.eval(); mx.eval(lm.parameters())
        self.model._esmc = lm
        self.builder = ESMFold2InputBuilder(ccd_cache=assets / 'ESMFold2')
        self.profile = model

    def predict(self, chains, seed, samples, directory, job):
        import numpy as np
        import torch
        import mlx.core as mx
        from esm.models.esmfold2 import ProteinInput, StructurePredictionInput
        from esm.utils.structure.input_builder import LigandInput
        from esm.utils.msa import MSA
        seqs = []
        for c in chains:
            if c['kind'] == 'ligand': seqs.append(LigandInput(id=c['id'], smiles=c['smiles']))
            else:
                msa = None if c['msa'] == 'empty' else MSA.from_a3m(c['msa'], remove_insertions=True)
                seqs.append(ProteinInput(id=c['id'], sequence=c['sequence'], msa=msa))
        features, infos = self.builder.prepare_input(StructurePredictionInput(sequences=seqs), seed=seed, device='cpu')
        torch.manual_seed(seed); mx.random.seed(seed)
        loops, steps = PROFILES[self.profile]
        mx.synchronize(); started = time.perf_counter()
        outputs = self.model(**features, num_loops=loops, num_sampling_steps=steps,
                             num_diffusion_samples=samples, msa_max_depth=1024)
        mx.synchronize(); seconds = time.perf_counter() - started
        arrays = {k: v.detach().cpu().numpy() for k, v in outputs.items() if isinstance(v, torch.Tensor)}
        for key in ('sample_atom_coords', 'plddt', 'ptm', 'pae'):
            if key not in arrays or not np.isfinite(arrays[key]).all(): raise RuntimeError('Missing/nonfinite ' + key)
        for key in ('plddt', 'ptm', 'iptm'):
            if key in arrays and (arrays[key].min() < 0 or arrays[key].max() > 1): raise RuntimeError('Confidence outside 0–1: ' + key)
        results = self.builder.decode(outputs, features, infos, num_diffusion_samples=samples, complex_id=job)
        if samples == 1: results = [results]
        if len(results) != samples: raise RuntimeError('ESMFold2 output count mismatch')
        from validate_prediction_geometry import inspect_geometry
        pairs = []
        for i, result in enumerate(results):
            stem = f'{job}_seed_{seed}_model_{i}'
            structure = directory / (stem + '.cif')
            structure.write_text(result.complex.to_mmcif())
            from Bio.SeqUtils import seq1
            mc = result.complex
            token_chains = [mc.metadata.chain_lookup[int(v)] for v in mc.chain_id]
            if set(token_chains) != {c['id'] for c in chains}: raise RuntimeError('Output chain identity mismatch')
            for c in chains:
                indices = [j for j, cid in enumerate(token_chains) if cid == c['id']]
                if c['kind'] == 'protein':
                    observed = ''.join(seq1(mc.sequence[j]) for j in indices)
                    if observed != c['sequence']: raise RuntimeError('Output sequence mismatch: ' + c['id'])
                else:
                    from rdkit import Chem
                    mol = Chem.MolFromSmiles(c['smiles'])
                    count = sum(sum(e != 'H' for e in mc.atom_elements[int(mc.token_to_atoms[j, 0]):int(mc.token_to_atoms[j, 1])]) for j in indices)
                    if mol is None or count != mol.GetNumHeavyAtoms(): raise RuntimeError('Ligand atom count mismatch: ' + c['id'])
            audit = inspect_geometry(structure)
            if audit['errors']: raise RuntimeError('ESMFold2 structure failed geometry audit: ' + str(audit['errors']))
            confidence = dict(engine='esmfold2-' + self.profile + '-mlx',
                              complex_plddt=float(arrays['plddt'][i].mean()), ptm=float(arrays['ptm'].reshape(-1)[i]),
                              seed=seed, sample=i, num_loops=loops, num_sampling_steps=steps,
                              msa_policy='sequence-only' if self.profile == 'fast' else 'per-chain',
                              model_call_seconds=seconds, upstream_revision=PORT_REVISION)
            if 'iptm' in arrays: confidence['iptm'] = float(arrays['iptm'].reshape(-1)[i])
            confidence['confidence_score'] = confidence.get('iptm', confidence['ptm'])
            asym_map = {info.asym_id: info.chain_id for info in infos}
            token_map = [asym_map[int(v)] for v in features['asym_id'][0]]
            protein_ids = [c['id'] for c in chains if c['kind'] == 'protein']
            if len(protein_ids) >= 2:
                from ipsae_score import calculate_ipsae
                confidence.update(calculate_ipsae(arrays['pae'][i], token_map, protein_ids))
            confidence['chain_plddt'] = {cid: float(arrays['plddt'][i][np.array(token_map) == cid].mean()) for cid in asym_map.values()}
            ligand_mask = np.array([cid not in protein_ids for cid in token_map])
            if ligand_mask.any(): confidence['ligand_plddt'] = float(arrays['plddt'][i][ligand_mask].mean()) * 100
            if 'pair_chains_iptm' in arrays: confidence['pair_chains_iptm'] = arrays['pair_chains_iptm'][i].tolist()
            conf = directory / ('confidence_' + stem + '.json')
            atomic(conf, confidence)
            np.savez_compressed(directory / ('pae_' + stem + '.npz'), pae=arrays['pae'][i])
            np.savez_compressed(directory / ('plddt_' + stem + '.npz'), plddt=arrays['plddt'][i])
            pairs.append((structure, conf))
        return pairs


def run(root, model, paths, output, seeds, samples, unrestrained_check=False, session=None, progress=None):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    from live_structure_events import invalidate, publish
    for index, path in enumerate(paths, 1):
        chains, msas = read_input(path, model, unrestrained_check)
        identity = dict(input_sha256=sha(path), msas=msas, model=model, seeds=seeds, samples=samples,
                        profile=PROFILES[model], port=PORT_REVISION, unrestrained_check=unrestrained_check, schema=1)
        # JSON round trip makes tuple/list identity stable across resumptions.
        identity = json.loads(json.dumps(identity))
        dest = output / path.stem
        if complete(dest, identity):
            print(f'ESMFOLD2|reused|{path.stem}', flush=True)
            if progress: progress(index, len(paths), True)
            continue
        monitor = None
        if dest.is_dir() and not list(dest.iterdir()): dest.rmdir()
        if dest.exists() and all(p.name in {'studio_prediction_request.json'} for p in dest.iterdir()):
            monitor = (dest / 'studio_prediction_request.json').read_bytes()
            dest.rename(output / ('.monitor-' + path.stem + '-' + uuid.uuid4().hex))
        if dest.exists():
            raise RuntimeError('Existing ESMFold2 output is incomplete or changed; preserve it and choose a fresh output directory: ' + str(dest))
        staging = output / ('.' + path.stem + '-' + uuid.uuid4().hex)
        staging.mkdir()
        if monitor is not None: (staging / 'studio_prediction_request.json').write_bytes(monitor)
        invalidate(dest)
        if session is None:
            print('ESMFOLD2|loading|' + model + ' and shared ESMC-6B', flush=True)
            session = Session(root, model)
        atomic(staging / 'ligand_atom_map.json', ligand_atom_maps(chains))
        pairs = []
        for seed in seeds: pairs.extend(session.predict(chains, seed, samples, staging, path.stem))
        best = max(pairs, key=lambda pair: json.loads(pair[1].read_text())['confidence_score'])
        minimum = staging / 'pred_min'; minimum.mkdir()
        shutil.copyfile(best[0], minimum / 'model_0.cif')
        shutil.copyfile(best[1], minimum / 'confidence.json')
        atomic(staging / 'complete.json', dict(identity=identity, files={str(p.relative_to(staging)): sha(p) for p in staging.rglob('*') if p.is_file()}))
        staging.rename(dest)
        publish(dest, path.stem, 'esmfold2-' + model + '-mlx',
                [(dest / a.name, dest / b.name) for a, b in pairs])
        print(f'ESMFOLD2|completed|{path.stem}', flush=True)
        if progress: progress(index, len(paths), False)
    return session


def main():
    p = argparse.ArgumentParser()
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--yaml', type=Path); group.add_argument('--inputs', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--nanohunter-root', type=Path, required=True)
    p.add_argument('--model', choices=PROFILES, required=True)
    p.add_argument('--unrestrained-check', action='store_true', help='Independent verification: remove design guidance and affinity; Fast also removes MSAs, with the policy recorded in the receipt.')
    p.add_argument('--seeds', default='42'); p.add_argument('--samples', type=int, default=1)
    a = p.parse_args()
    seeds = [int(s) for s in a.seeds.split(',')]
    if not 1 <= len(seeds) <= 20 or len(set(seeds)) != len(seeds) or any(s < 0 or s >= 2**32 for s in seeds): p.error('Choose 1–20 distinct 32-bit seeds.')
    if not 1 <= a.samples <= 20: p.error('Choose 1–20 diffusion samples.')
    paths = [a.yaml] if a.yaml else sorted(a.inputs.glob('*.yaml'))
    if not paths: p.error('No YAML inputs found.')
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTORCH_ENABLE_MPS_FALLBACK='0')
    run(a.nanohunter_root, a.model, paths, a.output, seeds, a.samples, a.unrestrained_check)


if __name__ == '__main__': main()
