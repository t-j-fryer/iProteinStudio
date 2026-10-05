#!/usr/bin/env python3
"""Exercise installed Foundry preprocessing without running a neural model.

Run with the managed RFD3 Python. The checkpoint is memory-mapped only to read
its actual inference transform configuration; no weights are exported. An
explicit --report path saves measured coordinates and source hashes for audits.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Sources/iProteinStudio/Resources/rfd3'))
import prepare_campaign
from test_rfd3_worked_examples import request, STRUCTURE

TOL = 0.002  # Angstrom; PDB precision plus float32 subtraction at large offsets.
SHIFT = np.array([300., -180., 120.])


def translated_pdb(source, destination):
    lines = []
    for line in source.read_text().splitlines():
        if line.startswith(('ATOM  ', 'HETATM')):
            xyz = np.array([float(line[i:i+8]) for i in (30, 38, 46)]) + SHIFT
            line = line[:30] + ''.join(f'{x:8.3f}' for x in xyz) + line[54:]
        lines.append(line)
    destination.write_text('\n'.join(lines) + '\n')


def emitted_spec(work, runtime, mode, length, translated):
    work.mkdir(parents=True)
    req = request(mode, work, runtime)
    req['lengths'] = [length]
    if translated:
        source = work / 'translated.pdb'
        translated_pdb(STRUCTURE, source)
        req['target_structure'] = str(source)
    # Stale de-novo overrides must not leak into either existing-complex mode.
    req['infer_ori_strategy'] = 'com'
    req['ori_token'] = [999., 999., 999.]
    prepare_campaign.normalize_protein_target(req, work)
    path = prepare_campaign.write_design_yaml(req, work, None, None)
    spec = next(iter(yaml.safe_load(path.read_text()).values()))
    assert 'infer_ori_strategy' not in spec and 'ori_token' not in spec
    if mode == 'motifScaffolding':
        # This is the same fixed-target count used by design_from_yaml bins.
        target_length = req['normalized_chain_ranges'][req['target_chains'][0]]
        start, end = map(int, target_length[1:].split('-'))
        spec['length'] = str(length + end - start + 1)
    return spec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runtime', type=Path, default=Path(os.environ.get(
        'NANOHUNTER_ROOT', str(Path.home() / '.iproteinstudio'))) / 'rfd3')
    ap.add_argument('--report', type=Path)
    ap.add_argument('--allow-expanded-motif', action='store_true',
                    help='Audit the known old RASA patch without accepting its atom mask.')
    args = ap.parse_args()
    os.environ.setdefault('CCD_MIRROR_PATH', str(args.runtime / 'assets/fluorescein/ccd'))
    os.environ.setdefault('DEBUG', 'false')
    import torch
    import hydra
    from omegaconf import OmegaConf
    import rfd3.inference.input_parsing as parsing
    import rfd3.utils.inference as origin_module
    import rfd3.transforms.pipelines as pipelines
    import rfd3.transforms.design_transforms as transforms

    checkpoint = torch.load(args.runtime / 'checkpoints/rfd3_latest.ckpt',
                            map_location='cpu', weights_only=False, mmap=True)
    transform = copy.deepcopy(next(iter(checkpoint['train_cfg'].datasets.val.values())).dataset.transform)
    transform.diffusion_batch_size = 1  # matches Studio's feature-only oracle
    pipeline = hydra.utils.instantiate(transform)
    results = []
    snapshots = {}
    translation_checks = []
    original_set_origin = parsing.DesignInputSpecification._set_origin
    captured = {}

    def capture_origin(self, atoms):
        captured['before'] = atoms.copy()
        return original_set_origin(self, atoms)

    def evaluate(spec, policy, key):
        if policy == 'com':
            spec['infer_ori_strategy'] = 'com'
        elif policy == 'explicit_motif':
            # Resolve selections with Foundry itself, before adding placeholders.
            reference = parsing.DesignInputSpecification(**copy.deepcopy(spec))
            motif = reference.unindex.get_mask() & reference.select_fixed_atoms.get_mask()
            assert motif.any()
            spec['ori_token'] = reference.atom_array_input.coord[motif].mean(0).tolist()
        np.random.seed(0)
        torch.manual_seed(0)
        with patch.object(parsing.DesignInputSpecification, '_set_origin', capture_origin):
            data = parsing.DesignInputSpecification(**spec).to_pipeline_input('centre_audit')
        pre = captured['before']
        fixed_pre = pre.is_motif_atom_with_fixed_coord.astype(bool)
        out = pipeline(data)
        coords = out['coord_atom_lvl_to_be_noised'].numpy()[0]
        fixed = out['feats']['is_motif_atom_with_fixed_coord'].numpy().astype(bool)
        unindexed = out['feats']['is_motif_atom_unindexed'].numpy().astype(bool) & fixed
        assert np.isfinite(coords).all()
        assert fixed.sum() == fixed_pre.sum()
        if 'partial_t' not in spec and not args.allow_expanded_motif:
            assert unindexed.sum() == 9, f'Expected nine selected motif atoms, got {unindexed.sum()}'
        # Every real fixed atom receives the SAME translation, including target.
        offsets = pre.coord[fixed_pre] - coords[fixed]
        np.testing.assert_allclose(offsets, np.broadcast_to(offsets.mean(0), offsets.shape), atol=TOL)
        metric = {'case': key, 'policy': policy, 'fixed_atoms': int(fixed.sum()),
                  'unindexed_fixed_atoms': int(unindexed.sum()),
                  'pre_origin_atoms': len(pre), 'origin_xyz': offsets.mean(0).tolist(),
                  'fixed_centroid_norm_a': float(np.linalg.norm(coords[fixed].mean(0))),
                  'motif_centroid_norm_a': float(np.linalg.norm(coords[unindexed].mean(0))) if unindexed.any() else None}
        if 'partial_t' in spec:
            # Real scaffold coordinates survive; no de-novo zero initialization.
            assert np.linalg.norm(coords[~fixed]) > 1
            np.testing.assert_allclose(pre.coord[~fixed_pre].mean(0), offsets.mean(0), atol=TOL)
            # Atom14 drops terminal OXT, inserts virtual atoms, and may
            # renumber residues. Check each retained real scaffold coordinate.
            real = ~fixed_pre & (pre.atom_name != 'OXT')
            expected = pre.coord[real] - offsets.mean(0)
            distances = np.linalg.norm(expected[:, None, :] - coords[~fixed][None, :, :], axis=-1)
            np.testing.assert_allclose(distances.min(axis=1), 0, atol=TOL)
            metric['partial_real_atoms_preserved'] = int(real.sum())
            metric['partial_terminal_atoms_omitted'] = int((~fixed_pre & (pre.atom_name == 'OXT')).sum())
        else:
            placeholders = ~fixed_pre
            assert np.all(pre.coord[placeholders] == 0)
            np.testing.assert_allclose(coords[~fixed], 0, atol=TOL)
            if policy == 'default':
                np.testing.assert_allclose(coords[fixed].mean(0), 0, atol=TOL)
            elif policy == 'explicit_motif':
                np.testing.assert_allclose(offsets.mean(0), spec['ori_token'], atol=TOL)
                if not args.allow_expanded_motif:
                    np.testing.assert_allclose(coords[unindexed].mean(0), 0, atol=TOL)
            else:
                # Positive reproduction of the reported finite-zero COM bug.
                expected = pre.coord[fixed_pre].mean(0) * placeholders.sum() / len(pre)
                np.testing.assert_allclose(coords[fixed].mean(0), expected, atol=TOL)
        snapshots[key] = coords[fixed].copy()
        results.append(metric)

    with tempfile.TemporaryDirectory(prefix='iprotein-centre-') as raw:
        work = Path(raw)
        selection_spec = emitted_spec(work / 'rasa', args.runtime, 'motifScaffolding', 70, False)
        selection_spec.update(select_buried={'A19': 'CG'},
                              select_partially_buried={'A19': 'CE1'},
                              select_exposed={'A19': 'CZ'})
        selected = parsing.DesignInputSpecification(**selection_spec).atom_array_input
        for atom, expected in [('CG', 0), ('CE1', 1), ('CZ', 2), ('CA', 3)]:
            mask = (selected.chain_id == 'A') & (selected.res_id == 19) & (selected.atom_name == atom)
            assert mask.sum() == 1
            assert selected.rasa_bin[mask].item() == expected
        for length in (200, 300):
            for policy in ('default', 'com', 'explicit_motif'):
                keys = []
                for moved in (False, True):
                    key = f'{length}_{policy}_{int(moved)}'
                    spec = emitted_spec(work / key, args.runtime, 'motifScaffolding', length, moved)
                    evaluate(spec, policy, key)
                    keys.append(key)
                delta = snapshots[keys[1]] - snapshots[keys[0]]
                translation_checks.append({'length': length, 'policy': policy,
                                           'max_abs_difference_a': float(np.max(np.abs(delta))),
                                           'centroid_displacement_a': float(np.linalg.norm(delta.mean(0)))})
                if policy == 'com':
                    assert np.linalg.norm(delta.mean(0)) > 100
                else:
                    np.testing.assert_allclose(delta, 0, atol=TOL)
        for policy in ('default', 'explicit_motif'):
            np.testing.assert_allclose(snapshots[f'200_{policy}_0'], snapshots[f'300_{policy}_0'], atol=TOL)
        for moved in (False, True):
            key = f'partial_{int(moved)}'
            spec = emitted_spec(work / key, args.runtime, 'partialDiffusion', 13, moved)
            evaluate(spec, 'default', key)
        np.testing.assert_allclose(snapshots['partial_0'], snapshots['partial_1'], atol=TOL)

    paths = [Path(m.__file__) for m in (parsing, origin_module, pipelines, transforms)]
    paths += [Path(prepare_campaign.__file__), Path(__file__), STRUCTURE,
              args.runtime / 'mlx_port/sampler.py', args.runtime / 'milestone0_oracle.py']
    paths = [p for p in paths if p.is_file()]
    report = {'translation_a': SHIFT.tolist(), 'tolerance_a': TOL,
              'transform': OmegaConf.to_container(transform, resolve=True),
              'source_sha256': {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
              'cases': results, 'translation_checks': translation_checks,
              'status': 'PASS_CENTRING_ONLY_KNOWN_MASK_BUG' if args.allow_expanded_motif else 'PASS',
              'limits': 'Preprocessing only; no model forward, backbone generation, clash or quality measurements.'}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(results, indent=2))
    print('RFD3 coordinate centring: 14 real preprocessing cases PASS')
    if args.allow_expanded_motif:
        print('Known expanded motif mask allowed for baseline audit only.')


if __name__ == '__main__':
    main()
