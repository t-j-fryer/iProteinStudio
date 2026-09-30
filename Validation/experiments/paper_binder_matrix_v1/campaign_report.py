"""Stream an independently audited, master-table-joined prediction export.

Run with the pinned analysis Python after each engine and at campaign completion.
Scientific outputs are read only; all derived files go into analysis/.
"""
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import numpy as np
from biotite.structure.io import pdbx

from common import save, sha
from analyse import confidence


def extract(measurement, row, target, reference):
    from quality import fit
    from ipsae_score import calculate_ipsae

    structure = Path(measurement['structure'])
    atoms = pdbx.get_structure(pdbx.CIFFile.read(structure), model=1)
    ca = atoms[atoms.atom_name == 'CA']
    assert np.isfinite(atoms.coord).all()
    assert sum(ca.chain_id == 'A') == len(row['binder_sequence'])
    assert sum(ca.chain_id == 'B') == len(target['sequence'])
    amino_acids = dict(zip('ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split(), 'ARNDCQEGHILKMFPSTWYV'))
    assert ''.join(amino_acids[name] for name in ca.res_name[ca.chain_id == 'A']) == row['binder_sequence']
    assert ''.join(amino_acids[name] for name in ca.res_name[ca.chain_id == 'B']) == target['sequence']
    values = confidence(structure)
    result = dict(row)
    fields = dict(
        engine=measurement['engine'], seed=measurement['seed'],
        optimization=measurement['variant'], structure=str(structure),
        steps_requested=measurement['steps'], recycles=measurement['recycles'],
        binder_length=len(row['binder_sequence']), target_length=len(target['sequence']),
        target_msa_rows=0 if measurement['engine'] == 'esmfold2_fast' else target['rows'],
        target_msa_query_only=measurement['engine'] == 'esmfold2_fast' or target['query_only'],
        request_seconds=measurement['request_seconds'],
        input_setup_seconds=measurement.get('input_setup_seconds'),
        unit_seconds_before_checkpoint=measurement.get('unit_seconds_before_checkpoint'),
        audit_seconds=measurement['audit_seconds'],
        geometry_violations=len(measurement['geometry']['violations']),
        model_seconds=measurement['stages']['model_total']['seconds'],
    )
    fields['outside_model_seconds'] = fields['request_seconds'] - fields['model_seconds']
    for name in ('ptm', 'iptm', 'ipsae_min', 'confidence_score'):
        if name in values:
            assert values[name].size == 1
            fields[name] = float(values[name])
    plddt_key = next(k for k in ('complex_plddt', 'avg_plddt', 'plddt') if k in values)
    # Native OpenFold and Protenix confidence is 0–100; Boltz/Intelli/ESM use 0–1.
    scale = 100 if measurement['engine'] == 'openfold3' or measurement['engine'].startswith('protenix') else 1
    fields['mean_plddt_0_1'] = float(values[plddt_key].mean()) / scale
    assert 0 <= fields['mean_plddt_0_1'] <= 1
    if measurement['engine'] != 'openfold3':
        pae = next((v for k, v in values.items() if 'pae' in k), None)
        assert pae is not None, ('Missing PAE', structure)
        token_chains = ['A'] * len(row['binder_sequence']) + ['B'] * len(target['sequence'])
        calculated = calculate_ipsae(pae, token_chains, ['A', 'B'])
        if 'ipsae_min' in fields:
            assert abs(fields['ipsae_min'] - calculated['ipsae_min']) < 1e-6
        fields['ipsae_min'] = calculated['ipsae_min']
        fields['ipsae_method'] = calculated['ipsae_method']
    else:
        fields['ipsae_method'] = 'Unavailable: native OpenFold output supplies PDE, not PAE'
    if target['sequence'] == reference['sequence']:
        points = ca.coord[ca.chain_id == 'B'][reference['core_indices']].astype(float)
        ref = np.asarray(reference['core_ca'])
        rotation, translation = fit(ref, points)
        fields['sumo_crystal_core_ca_rmsd_A'] = float(np.sqrt(np.mean(np.sum((points @ rotation + translation - ref) ** 2, axis=1))))
    result.update({'prediction_' + k: v for k, v in fields.items()})
    return result


def main():
    cfg = json.loads(Path(sys.argv[1]).read_text())
    assert cfg['phase'] == 'campaign'
    root = Path(cfg['output'])
    output = root / 'analysis'
    output.mkdir(exist_ok=True)
    reference = json.loads(Path(__file__).with_name('reference.json').read_text())
    designs = {r['design_name']: r for r in cfg['rows']}
    expected = {(e, r['design_name'], seed) for e, _ in cfg['arms'] for r in cfg['selected_rows'] for seed in cfg['seeds']}
    rows, stages, errors, seen = [], [], [], set()
    for receipt in sorted(root.glob('*__*/**/complete.json')):
        try:
            complete = json.loads(receipt.read_text())
            measurement = receipt.with_name('measurement.json')
            m = json.loads(measurement.read_text())
            if m['warmup'] or m['diagnostic']:
                continue
            assert sha(measurement) == complete['files'][str(measurement.resolve())]
            assert all(Path(p).is_file() and sha(p) == checksum for p, checksum in complete['files'].items())
            assert complete['design_name'] == m['design_name'] and complete['seed'] == m['seed']
            key = (m['engine'], m['design_name'], m['seed'])
            assert key in expected and key not in seen, ('Unexpected/duplicate output', key)
            row = designs[m['design_name']]
            result = extract(m, row, cfg['targets'][row['target_key']], reference)
            result['prediction_measurement'] = str(measurement)
            result['prediction_measurement_sha256'] = sha(measurement)
            rows.append(result)
            seen.add(key)
            for name, timing in m['stages'].items():
                stages.append(dict(engine=m['engine'], design_name=m['design_name'], seed=m['seed'], stage=name,
                                   nested_not_additive=True, timing_kind='CPU dispatch' if 'dispatch' in name else 'CPU wall' if name in ('preprocessing','featurization','output_write','structure_write','confidence_write','structure_serialization','decode','ccd_load') else 'GPU synchronized wall', **timing))
        except Exception as exc:
            errors.append(dict(path=str(receipt), error=repr(exc)))
    startups = []
    for load in sorted(root.glob('*__*/sessions/*/load.json')):
        startups.append(dict(receipt=str(load), **json.loads(load.read_text())))
    for name, data in [('predictions.csv', rows), ('stage_timings.csv', stages), ('startup_timings.csv', startups)]:
        fields = list(dict.fromkeys(k for row in data for k in row))
        temporary = output / (name + '.tmp')
        with temporary.open('w') as f:
            writer = csv.DictWriter(f, fields)
            writer.writeheader()
            writer.writerows(data)
        temporary.replace(output / name)
    groups = defaultdict(list)
    for row in rows:
        groups[row['prediction_engine']].append(row)
    summaries = []
    for engine, variant in cfg['arms']:
        rr = groups[engine]
        summaries.append(dict(engine=engine, variant=variant, completed=len(rr), expected=len(cfg['selected_rows']) * len(cfg['seeds']),
                              **{key: median(r['prediction_' + key] for r in rr) if rr else None for key in ('request_seconds', 'model_seconds', 'outside_model_seconds')}))
    generated_at = datetime.now(timezone.utc).isoformat()
    audit = dict(generated_at=generated_at, expected=len(expected), completed=len(seen), missing=sorted(expected-seen), errors=errors,
                 summaries=summaries, reference=reference, analysis_code_sha256=sha(__file__),
                 note='Independent medians; named stages are nested, not additive. Timers synchronize GPU at outer stages; dispatch stages measure host launch time. Raw outputs unchanged.')
    save(output / 'audit.json', audit)
    lines = ['# Paper binder prediction screen', '', f'{len(seen)}/{len(expected)} predictions independently audited; {len(errors)} audit errors. Report generated {generated_at}.', '',
             'One sample per design and engine. Binder chain A has no MSA; target chain B uses the frozen supplied alignment capped at 128 rows. ESMFold2 Fast uses no MSA and the full 50-step requested profile. SUMO is the 96-aa benchmark sequence. Query-only peptide-tag alignments are explicitly marked in the export.', '',
             '| Engine | Completed | Request median (s) | Model median (s) | Outside-model median (s) |', '|---|---:|---:|---:|---:|']
    for s in summaries:
        numbers = ['—' if s[k] is None else f'{s[k]:.3f}' for k in ('request_seconds', 'model_seconds', 'outside_model_seconds')]
        lines.append(f"| {s['engine']} | {s['completed']}/{s['expected']} | " + ' | '.join(numbers) + ' |')
    lines += ['', '[Joined design/score/timing table](analysis/predictions.csv) · [Every named timing stage](analysis/stage_timings.csv) · [Cold initialization and asset checks](analysis/startup_timings.csv) · [Coverage and integrity audit](analysis/audit.json)', '',
              'Timing units are different binder–target complexes, not five repeats. Warmup is excluded from these medians. Startup receipts preserve every resident process, including retries; initialization includes model loading, and asset verification is separate. Model timing is synchronized wall time, including host dispatch, rather than a hardware-only GPU utilization measure. Native confidence is not calibrated across engines. ipSAE(min) uses the existing Studio definition; OpenFold has no PAE and therefore no ipSAE value. SUMO crystal-core RMSD uses 3QHT residues corresponding to query positions 21–96 and evaluates the target fold, not binder affinity or pose correctness. Geometry flags are retained as advisories.', '',
              'Original table fields are preserved. Prediction fields have the prediction_ prefix. The main/designed binder sequence is used; 33 differing assayed sequences and the Myc/TrxA label discrepancy are documented in ../INPUT_AUDIT.md.']
    (root / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(dict(completed=len(seen), expected=len(expected), audit_errors=errors)))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
