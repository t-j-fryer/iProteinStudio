#!/usr/bin/env python3
"""Audit completed raw outputs and summarize coordinate-based paired endpoints.

Run with the prepared Biotite/NumPy Python. Never modifies raw campaigns.
Bootstrap units are paired trajectories, not individual correlated cycles.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics
import re
import biotite
import numpy as np
from biotite.sequence import ProteinSequence
from biotite.structure.io.pdbx import CIFFile, get_structure

ARMS = ['natural', 'antihelix_seed_only', 'antihelix_seed_and_cycles', 'beta_seed_only', 'beta_seed_and_cycles']
METRICS = ['helix_fraction', 'sheet_fraction', 'coil_fraction', 'iptm', 'ipsae_min', 'complex_plddt', 'binder_plddt']

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    out = root / 'analysis'
    psea = list(csv.DictReader((out / 'psea_per_structure.csv').open()))
    lookup = {(r['arm'], r['run'], int(r['cycle'])): r for r in psea}
    assert len(psea) == len(lookup) == 300, 'Expected 300 unique structures'
    audited, checksums, sequences = [], {}, {}
    for arm in ARMS:
        campaign = root / 'campaigns' / ('full__' + arm)
        assert len(list(campaign.glob('run_*/cycle_*/pred_min/model_0.*'))) == 60
        for run in range(1, 11):
            run_name = f'run_{run:03d}'
            metrics_path = campaign / run_name / 'metrics_per_cycle.csv'
            rows = list(csv.DictReader(metrics_path.open()))
            assert len(rows) == 6 and {int(r['cycle']) for r in rows} == set(range(6))
            checksums[str(metrics_path.relative_to(root))] = hashlib.sha256(metrics_path.read_bytes()).hexdigest()
            for record in rows:
                cycle = int(record['cycle'])
                key = arm, run_name, cycle
                result = dict(lookup[key])
                path = campaign / run_name / f'cycle_{cycle:02d}' / 'pred_min/model_0.cif'
                confidence = path.with_name('confidence.json')
                data = json.loads(confidence.read_text())
                for item in (path, confidence):
                    checksums[str(item.relative_to(root))] = hashlib.sha256(item.read_bytes()).hexdigest()
                atoms = get_structure(CIFFile.read(path), model=1, extra_fields=['b_factor'])
                assert np.isfinite(atoms.coord).all(), f'Nonfinite coordinates: {path}'
                ca = atoms[(atoms.chain_id == 'A') & (atoms.atom_name == 'CA')]
                assert len(ca) == int(result['residues']) == 90
                sequence = ''.join('X' if name == 'UNK' else ProteinSequence.convert_letter_3to1(name) for name in ca.res_name)
                assert sequence == record['binder_sequence'], f'Sequence mismatch: {path}'
                if cycle > 0: assert 'X' not in sequence
                sequences[key] = sequence
                for name in ['iptm', 'complex_plddt', 'ipsae_min']:
                    result[name] = float(data[name])
                    assert np.isfinite(result[name])
                for name in ['iptm', 'complex_plddt']:
                    assert abs(result[name] - float(record[name])) < 1e-6
                result['binder_plddt'] = float(np.mean(ca.b_factor)) / 100
                assert np.isfinite(result['binder_plddt'])
                distances = np.linalg.norm(np.diff(ca.coord, axis=0), axis=1)
                result['ca_distance_outliers'] = int(np.sum((distances < 2.5) | (distances > 4.5)))
                result['run'], result['cycle'] = run_name, cycle
                for name in METRICS: result[name] = float(result[name])
                audited.append(result)
    for prefix in ['antihelix', 'beta']:
        for run in range(1, 11):
            assert sequences[prefix+'_seed_only', f'run_{run:03d}', 0] == sequences[prefix+'_seed_and_cycles', f'run_{run:03d}', 0]
    summary = {}
    trajectory = {}
    for arm in ARMS:
        summary[arm] = {}
        for endpoint, cycles in [('initial', [0]), ('optimized_cycles', list(range(1, 6))), ('final_cycle', [5])]:
            rows = [r for r in audited if r['arm'] == arm and r['cycle'] in cycles]
            summary[arm][endpoint] = {name: statistics.mean(r[name] for r in rows) for name in METRICS}
            summary[arm][endpoint].update(structures=len(rows), trajectories=10, iptm_ge_0_70=sum(r['iptm'] >= .7 for r in rows), ca_distance_outliers=sum(r['ca_distance_outliers'] for r in rows))
            trajectory[arm, endpoint] = {name: np.array([statistics.mean(r[name] for r in rows if r['run'] == f'run_{run:03d}') for run in range(1, 11)]) for name in METRICS}
    rng = np.random.default_rng(20260904)
    indices = rng.integers(0, 10, size=(20000, 10))
    comparisons = {}
    for intervention, control in [(a, 'natural') for a in ARMS[1:]] + [('antihelix_seed_and_cycles', 'antihelix_seed_only'), ('beta_seed_and_cycles', 'beta_seed_only')]:
        label = intervention + '_minus_' + control
        comparisons[label] = {}
        for endpoint in ['optimized_cycles', 'final_cycle']:
            comparisons[label][endpoint] = {}
            for name in METRICS:
                delta = trajectory[intervention, endpoint][name] - trajectory[control, endpoint][name]
                ci = np.quantile(delta[indices].mean(axis=1), [.025, .975])
                comparisons[label][endpoint][name] = {'mean_delta': float(delta.mean()), 'paired_bootstrap_95_percent_interval': ci.tolist(), 'positive_pairs': int(sum(delta > 0)), 'negative_pairs': int(sum(delta < 0))}
    log_audit = {}
    for arm in ARMS:
        allowed, mps_evidence, other = 0, 0, []
        for path in (root / 'campaigns' / ('full__' + arm)).rglob('*.log'):
            if '.studio_runtime' in path.parts: continue
            for line in path.read_text(errors='replace').splitlines():
                if 'MPS' in line: mps_evidence += 1
                if re.search(r'fall.?back', line, re.I):
                    if 'aten::linalg_svd' in line: allowed += 1
                    else: other.append(line)
        assert mps_evidence > 0 and not other, f'Unexpected device/fallback evidence: {arm}: {other}'
        log_audit[arm] = {'allowed_svd_warning_occurrences_across_duplicated_logs': allowed, 'other_fallback_messages': len(other), 'mps_log_lines': mps_evidence}
    for path in [root / 'manifest_full.json', out / 'psea_per_structure.csv']:
        checksums[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = {'audit': {'structures': 300, 'optimized_structures': 250, 'initial_structures': 50, 'trajectories_per_arm': 10, 'paired_initial_sequences_equal': True, 'sequence_coordinate_confidence_checks': 'passed', 'biotite_version': biotite.__version__, 'numpy_version': np.__version__, 'device_log_audit': log_audit}, 'arms': summary, 'paired_comparisons': comparisons, 'raw_sha256': checksums}
    (out / 'comparison_summary.json').write_text(json.dumps(report, indent=2) + '\n')
    with (out / 'audited_per_structure.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(audited[0]))
        writer.writeheader(); writer.writerows(audited)
    print(json.dumps({'audit': report['audit'], 'arms': summary, 'paired_comparisons': comparisons}, indent=2))

if __name__ == '__main__':
    main()
