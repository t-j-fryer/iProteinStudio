"""Combine audited optimization screens; never modify native prediction outputs."""
import csv
import json
from pathlib import Path
from statistics import median

BASE = Path(__file__).resolve().parents[2] / 'output/paper_binder_matrix_v1'
PHASES = ('benchmark_retry01', 'compute_cache', 'positions', 'esm_offset', 'boltz_confirm', 'precision_probe', 'precision_confirm', 'esm_memory')


def main():
    records, screens = [], {}
    for phase in PHASES:
        path = BASE / phase / 'analysis/results.json'
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        assert not data['audit_errors'], (phase, data['audit_errors'])
        screens[phase] = data
        for summary in data['summaries']:
            pairs = [p for p in data['pairs'] if (p['engine'], p['variant']) == (summary['engine'], summary['variant'])]
            records.append(dict(phase=phase, **summary,
                                paired_median_percent_saving=median(100 * p['paired_saving_seconds'] / p['baseline_seconds'] for p in pairs) if pairs else None,
                                max_backbone_rmsd_A=max((p['complex_backbone_rmsd'] for p in pairs), default=None),
                                max_binder_rmsd_after_core_A=max((p['binder_rmsd_after_target_core'] for p in pairs), default=None),
                                passing_pairs=sum(p['pass_gate'] for p in pairs)))
    output = BASE / 'optimization_summary'
    output.mkdir(exist_ok=True)
    (output / 'results.json').write_text(json.dumps(records, indent=2) + '\n')
    with (output / 'comparisons.csv').open('w') as f:
        writer = csv.DictWriter(f, list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    selection = json.loads((BASE / 'selection.json').read_text()) if (BASE / 'selection.json').exists() else None
    lines = ['# Shared-target optimization results', '',
             'Measured on this M4 Max (40 GPU cores, 64 GB, macOS 26.6.1). Each full arm uses five distinct SUMO96 binders of 64–150 residues, with paired seeds 42–46. Warmup and cProfile replays are excluded. The precision probe uses only one pair and cannot qualify a change by itself.', '',
             'Positive paired saving means faster. Request and model medians are calculated independently; their difference is not necessarily the median outside-model time. Named stage timers synchronize the GPU and are nested, not additive. These are instrumented local timings, not an estimate of wet-lab binding success.', '',
             '| Phase | Engine | Variant | n | Request median, s | Paired saving, s (%) | Output gate |',
             '|---|---|---|---:|---:|---:|---|']
    for r in records:
        saving = 'not a speed contrast' if r['phase']=='esm_memory' else '—' if r['paired_median_saving'] is None else f"{r['paired_median_saving']:.3f} ({r['paired_median_percent_saving']:.1f}%)"
        gate = 'control' if not r['paired_n'] else f"{r['passing_pairs']}/{r['paired_n']} pass"
        lines.append(f"| {r['phase']} | {r['engine']} | {r['variant']} | {r['n']} | {r['request_seconds']:.3f} | {saving} | {gate} |")
    lines += ['', 'The output gate requires complete-complex backbone RMSD ≤0.1 Å, binder CA RMSD after aligning the SUMO core ≤0.2 Å, scalar confidence/per-residue normalized pLDDT changes ≤0.01, mean PAE/PDE error ≤0.1 Å, and no additional recorded geometry violations. Exact equality is reported separately. SUMO core comparisons exclude the flexible first 20 residues.', '',
              'The initial OpenFold parser-cache arm failed before producing predictions; its corrected CPU-only test saved about 2 ms and was not pursued. Initial ESM arms produced valid predictions but failed a cleanup-report hook; that hook was corrected for subsequent tests. Failed attempts and all native outputs are retained. See the Lab Books for complete provenance and untested cases.', '',
              'Original input audit: [INPUT_AUDIT.md](../INPUT_AUDIT.md). Full prediction campaign: [campaign/REPORT.md](../campaign/REPORT.md).']
    if selection:
        lines += ['', '## Selected campaign variants', '']
        for engine, variant in selection['variants'].items():
            lines.append(f"- **{engine}: {variant}.** {selection['reasons'][engine]}")
        lines += ['', 'Selection applies to this isolated prediction campaign. No app defaults or installed engines are changed. Sequence-dependent preprocessing is recomputed for each binder; learned complex features are never shared between different complexes.']
    (output / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(dict(screens=list(screens), measured_predictions=sum(s['normal_count'] for s in screens.values()), selection=selection and selection['variants'])))


if __name__ == '__main__':
    main()
