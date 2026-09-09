#!/usr/bin/env python3
"""Audit immutable monomer predictions and compare paired strength interventions."""
import argparse
from collections import Counter
import csv
import importlib.util
import json
import math
import os
import copy
import random
import statistics
import sys
from pathlib import Path
import campaign as study

sys.path.insert(0, str(study.SOURCE / 'scripts'))
from initialization_assessment import assess_structure
from secondary_structure_control import generate_sequence

METRICS = ('helix', 'sheet', 'coil', 'plddt')
ASSESSMENT = dict(max_attempts=1, min_uncertain_coil_length=16, confidence_threshold=50)


def evaluate(path, sequence):
    a = assess_structure(path, sequence, ASSESSMENT)
    return {**a['fractions'], 'plddt': statistics.mean(a['confidence']),
            'psea': a['psea'], 'per_residue_confidence': a['confidence']}


def native_structures(directory, predictor):
    if predictor == 'boltz':
        return [p for p in (directory / 'boltz').glob('boltz_results_*/predictions/*/*') if p.suffix in ('.cif', '.pdb')]
    if predictor == 'intellifold':
        return [p for p in (directory / 'intellifold').rglob('*') if p.suffix in ('.cif', '.pdb') and 'predictions' in p.parts]
    if predictor.startswith('protenix'):
        return [p for p in directory.rglob('*.cif') if 'predictions' in p.parts and 'pred_min' not in p.parts]
    return list(directory.rglob('*_model.cif')) + list(directory.rglob('*_model.pdb'))


def check_logs(root, predictor):
    logs = sorted(root.rglob('predict.log'))
    study.require(bool(logs), 'Missing native prediction logs')
    warnings, evidence = [], []
    for path in logs:
        content = path.read_text(errors='replace')
        lower = content.lower()
        markers = [line for line in content.splitlines() if any(m in line.lower() for m in
                   ('gpu available: true (mps), used: true', 'iproteinstudio_device', 'device=mps',
                    'device: mps', 'device mps', 'device(type=\'mps\')', 'metal', 'mlx.core.gpu'))]
        study.require(bool(markers), f'Missing explicit Apple GPU execution evidence: {path}')
        evidence += [{'path': str(path.relative_to(root)), 'lines': markers}]
        for line in content.splitlines():
            low = line.lower()
            if ('fallback' in low or 'fall back' in low) and ('cpu' in low or '=1' in low):
                if predictor == 'boltz' and 'linalg_svd' in low:
                    warnings.append({'path': str(path.relative_to(root)), 'line': line})
                else:
                    study.require(False, f'Forbidden CPU fallback: {path}: {line}')
    return warnings, evidence


def audit(phase, arm_name):
    study.prepare()
    path = study.OUTPUT / 'audits' / phase / f'{arm_name}.json'
    if path.exists():
        value = study.read(path)
        study.require(value['manifest_sha256'] == study.sha(study.OUTPUT / 'manifest.json'), 'Audit identity changed')
        for relative, checksum in value['raw_sha256'].items():
            study.require(study.sha(study.OUTPUT / relative) == checksum, 'Audited raw output changed')
        return value
    if phase == 'pilot' and arm_name in study.CONFIG.get('reused_pilots', {}):
        receipt = study.CONFIG['reused_pilots'][arm_name]
        origin = study.ROOT / receipt['audit']
        study.require(study.sha(origin) == receipt['sha256'], 'Original pilot audit changed')
        original = study.read(origin)
        source_output = origin.parents[2]
        study.require(original['operational_passed'], 'Cannot reuse a failed pilot')
        for relative, checksum in original['raw_sha256'].items():
            study.require(study.sha(source_output / relative) == checksum, 'Original raw output changed')
        value = copy.deepcopy(original)
        value['raw_sha256'] = {os.path.relpath(source_output / relative, study.OUTPUT): checksum
                              for relative, checksum in original['raw_sha256'].items()}
        for row in value['structures']:
            row['structure'] = os.path.relpath(source_output / row['structure'], study.OUTPUT)
        value['reused_from'] = receipt
        value['original_manifest_sha256'] = original['manifest_sha256']
        value['manifest_sha256'] = study.sha(study.OUTPUT / 'manifest.json')
        study.atomic(path, value)
        return value
    plan = study.read(study.OUTPUT / 'plans' / phase / f'{arm_name}.json')
    state = study.read(study.OUTPUT / 'status' / phase / f'{arm_name}.json')
    root = Path(plan['normalized_request']['campaign'])
    arm, c = study.CONFIG['arms'][arm_name], study.CONFIG['campaign']
    offset, count = (0, 1) if phase == 'pilot' else (1, 9)
    snapshot = root / '.studio_runtime/pipeline'
    stage = study.read(study.OUTPUT / 'stage_receipt.json')
    for name in ('nanohunter_run.sh', 'scripts/secondary_structure_control.py', 'scripts/initialization_assessment.py', 'scripts/validate_prediction_geometry.py'):
        study.require(study.sha(snapshot / name) == stage['files'][name]['after_sha256'], f'Snapshot changed: {name}')
    spec = importlib.util.spec_from_file_location('geometry', snapshot / 'scripts/validate_prediction_geometry.py')
    geometry = importlib.util.module_from_spec(spec); spec.loader.exec_module(geometry)
    trajectories, rows, failures = [], [], []
    for local in range(1, count + 1):
        global_index = local + offset
        run = root / f'run_{local:03d}'
        summary = dict(arm=arm_name, phase=phase, trajectory=global_index, outcome='failed', completed_cycles=0)
        if not run.exists():
            summary['outcome'] = 'not_started'; trajectories.append(summary); continue
        seed_plan = study.read(run / 'secondary_structure_plan.json')
        sequence, expected = generate_sequence(90, 90, 50, arm['predictor'], c['binder_seed'] + global_index,
            'antihelix', arm['strength'], .5, .5, .5, 0, 'seed-only', 'mask-first')
        study.require(seed_plan == expected, f'Initialization does not replay: {run}')
        study.require(not (run / 'initialization_refinement').exists(), 'Retired inspection executed')
        study.require(not list(run.rglob('secondary_structure_bias.json')), 'Secondary bias escaped initialization')
        metric_path = run / 'metrics_per_cycle.csv'
        metrics = list(csv.DictReader(metric_path.open())) if metric_path.exists() else []
        this_run = []
        for metric in metrics:
            cycle = int(metric['cycle']); directory = run / f'cycle_{cycle:02d}'
            structures = [directory / 'pred_min' / n for n in ('model_0.cif', 'model_0.pdb') if (directory / 'pred_min' / n).is_file()]
            study.require(len(structures) == 1, f'Normalized cardinality differs: {directory}')
            study.require(bool(study.read(directory / 'pred_min/confidence.json')), 'Empty confidence')
            raw = native_structures(directory, arm['predictor'])
            study.require(len(raw) == 1, f'Native prediction cardinality differs ({len(raw)}): {directory}')
            seq = metric['binder_sequence']
            study.require(len(seq) == 90 and (seq == sequence if cycle == 0 else 'X' not in seq), 'Sequence contract changed')
            diagnostics = geometry.inspect_geometry(structures[0])
            study.require(not diagnostics['errors'], f'Unusable coordinates: {diagnostics["errors"]}')
            receipt = study.read(directory / 'pred_min/geometry_report.json')
            study.require(receipt['policy'] == 'record_only' and receipt['coordinate_input_usable'], 'Geometry policy differs')
            study.require(len(receipt['structures']) == 1, 'Geometry report cardinality differs')
            recorded = receipt['structures'][0]
            study.require(recorded['sha256'] == study.sha(structures[0]) and recorded['violations'] == diagnostics['violations'], 'Geometry record differs from coordinates')
            row = dict(arm=arm_name, phase=phase, trajectory=global_index, cycle=cycle, sequence=seq,
                       structure=str(structures[0].relative_to(study.OUTPUT)),
                       geometry_violations=diagnostics['violations'], geometry_violation_count=len(diagnostics['violations']),
                       **evaluate(structures[0], seq))
            this_run.append(row); rows.append(row)
            if cycle < 5 and (directory / 'ligandmpnn/seed.txt').exists():
                study.require(int((directory / 'ligandmpnn/seed.txt').read_text()) == c['mpnn_seed'] + 1000 * global_index + cycle, 'MPNN seed pairing differs')
        summary['geometry_violations_total'] = sum(r['geometry_violation_count'] for r in this_run)
        summary['cycles_with_geometry_violations'] = [r['cycle'] for r in this_run if r['geometry_violation_count']]
        summary['completed_cycles'] = sum(r['cycle'] > 0 for r in this_run)
        completed = [r['cycle'] for r in this_run] == list(range(6)) and (run / 'run_exit_code.txt').read_text().strip() == '0'
        if completed:
            summary['outcome'] = 'completed'
            summary['initial_geometry_violations'] = this_run[0]['geometry_violation_count']
            summary['final_geometry_violations'] = this_run[-1]['geometry_violation_count']
            summary['initial_violations_resolved_by_final'] = bool(this_run[0]['geometry_violation_count'] and not this_run[-1]['geometry_violation_count'])
            timing = list(csv.DictReader((run / 'timing_run.csv').open()))
            summary['wall_seconds_including_initialization'] = float(timing[0]['duration_sec'])
            for metric in METRICS:
                summary['mean_' + metric] = statistics.mean(r[metric] for r in this_run if r['cycle'] > 0)
                summary['final_' + metric] = this_run[-1][metric]
        else:
            failures.append(dict(trajectory=global_index, diagnostics=state.get('error'), pipeline_log_tail=state.get('pipeline_log_tail')))
        trajectories.append(summary)
    warnings, evidence = check_logs(root, arm['predictor'])
    raw = {str(p.relative_to(study.OUTPUT)): study.sha(p) for p in root.rglob('*') if p.is_file()
           and '.studio_runtime' not in p.parts and '__pycache__' not in p.parts}
    value = dict(schema=1, phase=phase, arm=arm_name, operational_passed=all(t['outcome']=='completed' for t in trajectories),
                 trajectories=trajectories, structures=rows, failures=failures, raw_sha256=raw,
                 svd_fallback_log_lines=warnings, device_evidence=evidence, job=study.compact(state),
                 manifest_sha256=study.sha(study.OUTPUT / 'manifest.json'))
    study.atomic(path, value)
    return value


def paired(left, right, metric):
    keys = sorted(left.keys() & right.keys())
    differences = [right[k]['mean_'+metric] - left[k]['mean_'+metric] for k in keys]
    if not differences:
        return dict(n_pairs=0, mean_difference=None, bootstrap_95_ci=None)
    rng = random.Random(906026)
    draws = sorted(statistics.mean(rng.choices(differences, k=len(differences))) for _ in range(10000))
    return dict(n_pairs=len(keys), mean_difference=statistics.mean(differences), bootstrap_95_ci=[draws[249], draws[9749]])


def report():
    summaries, data, trajectories = {}, {}, []
    for name in study.CONFIG['arms']:
        records = [r for phase in ('pilot','remaining') for r in audit(phase,name)['trajectories']]
        study.require(sorted(r['trajectory'] for r in records) == list(range(1,11)), 'Declared outcomes missing')
        trajectories += records; complete = {r['trajectory']:r for r in records if r['outcome']=='completed'}; data[name]=complete
        summaries[name] = dict(declared_n=10, completed_n=len(complete), failed_n=10-len(complete),
            geometry_violations_total=sum(r['geometry_violations_total'] for r in records),
            trajectories_with_violations=sum(bool(r['geometry_violations_total']) for r in records),
            final_structures_with_violations=sum(bool(r['final_geometry_violations']) for r in complete.values()),
            **{m: statistics.mean(r['mean_'+m] for r in complete.values()) if complete else None for m in METRICS})
    contrasts = {name:{m:paired(data[arm['reference']],data[name],m) for m in METRICS}
                 for name,arm in study.CONFIG['arms'].items() if arm['reference']}
    output = study.OUTPUT / 'analysis'; output.mkdir(exist_ok=True)
    result = dict(complete=True,summaries=summaries,paired_contrasts=contrasts,methods=study.CONFIG['methods'],
                  optimized_structures=sum(r['completed_cycles'] for r in trajectories), manifest_sha256=study.sha(study.OUTPUT/'manifest.json'))
    study.atomic(output/'report.json',result)
    fields = sorted(set().union(*(r.keys() for r in trajectories)))
    with (output/'trajectories.csv').open('w') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(trajectories)
    lines=['# Initialization helix strength across installed engines','','90 residues; 10 declared trajectories per arm. P-SEA and CA pLDDT averaged over cycles01–05 within trajectories; cycle00 excluded.','',
           '| Engine / strength | Completed | Helix | Sheet | Coil | pLDDT |','|---|---:|---:|---:|---:|---:|']
    for name,row in summaries.items():
        values=[f'{row[m]:.1%}' if row[m] is not None else '—' for m in ('helix','sheet','coil')]
        confidence=f"{row['plddt']:.1f}" if row['plddt'] is not None else '—'
        lines.append(f"| {name} | {row['completed_n']}/10 | {' | '.join(values)} | {confidence} |")
    lines += ['', 'Paired bootstrap: 10,000 resamples, seed906026, no multiplicity adjustment. Fold summaries are conditional on completion; failures retain their declared seeds. Engine-native settings and OpenFold mask substitution limit direct cross-engine comparisons. No experimental folding validation, throughput/default promotion or inference beyond the declared campaign.']
    lines += ['', 'Geometry policy: record only at every cycle. Violations are included in structural endpoints and recorded per residue in audited structures; cycle00 is excluded from H/S/C endpoints. See geometry_by_cycle.csv for initial, intermediate and final violations.']
    geometry_rows = [dict(arm=name, trajectory=row['trajectory'], cycle=row['cycle'], violations=row['geometry_violation_count'], details=json.dumps(row['geometry_violations'])) for name in study.CONFIG['arms'] for phase in ('pilot','remaining') for row in audit(phase,name)['structures']]
    with (output/'geometry_by_cycle.csv').open('w') as handle:
        writer=csv.DictWriter(handle,fieldnames=['arm','trajectory','cycle','violations','details']);writer.writeheader();writer.writerows(geometry_rows)
    (output/'REPORT.md').write_text('\n'.join(lines)+'\n')
    return result

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['pilot','remaining']);p.add_argument('--arm',choices=list(study.CONFIG['arms']));p.add_argument('--report',action='store_true');a=p.parse_args()
    result=report() if a.report else audit(a.phase,a.arm)
    print(json.dumps({k:v for k,v in result.items() if k in ('complete','arm','phase','operational_passed','optimized_structures')}))
