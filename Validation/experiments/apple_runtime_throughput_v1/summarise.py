#!/usr/bin/env python3
"""Audit completed units and write a cautious per-workload timing report."""
import argparse
import json
from pathlib import Path
from coordinator import verify_completed
from bench_worker import atomic
from analyse import compare_blocks


def main():
    ap=argparse.ArgumentParser();ap.add_argument('output',type=Path);args=ap.parse_args();out=args.output.resolve()
    records=[];comparisons=[];incomplete=[]
    for run in sorted(out.glob('*_*Z')):
        plan=run/'plan.json'
        if not plan.exists():continue
        host=json.loads((run/'host.json').read_text())
        cfg=json.loads((run/'frozen/run.json').read_text())
        for block in cfg['blocks']:
            done=sorted((run/block['id']).glob('attempt_*/completed.json'))
            if not done:incomplete.append(f'{run.name}/{block["id"]}');continue
            attempt=done[-1].parent;verify_completed(attempt,attempt.parent/(attempt.name+'.request.json'))
            result=json.loads((attempt/'result.json').read_text())
            fallback=json.loads((attempt.parent/(attempt.name+'.fallbacks.json')).read_text())
            for p in result['rows']:
                r=json.loads(Path(p).read_text())
                records.append(dict(run=run.name,block=block['id'],name=r['name'],seed=r['seed'],warmup=r['warmup'],
                    torch=r['torch'],threads=r['threads'],seconds=r['seconds'],cpu_seconds=r.get('process_cpu_seconds'),
                    geometry_discontinuities=len(r['geometry']['violations']),model_load_seconds=result['model_load_seconds'],
                    model_load_count=r['model_load_count'],svd_warning_count=len(fallback),path=p,host=host))
        # Early reverse-order plans named reference/candidate by execution order.
        # Preserve those raw reports, but consistently compare Torch2.13 ->2.14 here.
        if {'baseline','candidate'} <= {b['id'] for b in cfg['blocks']}:
            paths={name:sorted((run/name).glob('attempt_*/completed.json')) for name in ('baseline','candidate')}
            if all(paths.values()):
                result=compare_blocks(paths['baseline'][-1].parent,paths['candidate'][-1].parent,
                                      json.loads(Path(cfg['scientific_manifest']).read_text())['acceptance'])
                result['direction']='Torch2.13 baseline -> Torch2.14 candidate, independent of execution order'
                canonical=out/'analysis_v1'/run.name/'runtime_comparison.json';canonical.parent.mkdir(parents=True,exist_ok=True)
                atomic(canonical,result);comparisons.append(dict(path=str(canonical),**result))
            continue
        for p in run.glob('*.comparison.json'):
            comparisons.append(dict(path=str(p),**json.loads(p.read_text())))
    atomic(out/'measurements.json',dict(records=records,comparisons=comparisons,incomplete=incomplete))
    lines=['# Apple runtime throughput screen','',
           'M4 Max / 64 GB / macOS26.6.1. Experimental Boltz-2 monomers; no production changes.',
           'Identical model, 200 steps, three recycles, one sample, full potentials, empty MSA and allocator reset. FP32 except the explicitly labelled diffusion-BF16 arithmetic arm.',
           'Times cover a complete predict call (preparation, inference, writing and geometry); session initialization excluded. The model_load_seconds field includes engine imports, construction and checkpoint loading.',
           'One untimed-for-summary warmup per process. SUMO is its first shape-specific call in each block; this is not an all-shapes-warm benchmark.',
           'Separate inputs are not independent hardware replicates. Runtime comparisons are always oriented Torch2.13 baseline to2.14 candidate.', '',
           '| Stage/block | Torch | CPU threads | Input / seed | Seconds |', '|---|---|---:|---|---:|']
    for r in records:
        if r['warmup'] or r['block']=='profile':continue
        lines.append(f'| {r["run"].split("_")[0]}/{r["block"]} | {r["torch"]} | {r["threads"]} | {r["name"]} / {r["seed"]} | {r["seconds"]:.3f} |')
    lines += ['','## Numerical screening','']
    for c in comparisons:
        lines.append(f'- `{Path(c["path"]).parent.name}/{Path(c["path"]).name}`: '+('PASS' if c['passed'] else 'FAIL'))
        for p in c['pairs']:
            if p['warmup']:continue
            lines.append(f'  - {p["name"]}, seed{p["seed"]}: '+json.dumps(p.get('metrics',p.get('failures'))))
    lines += ['','## Limits','',
              'Small monomers do not validate design/interface rankings, large complexes, ligand affinity, other engines or M1/M2/M3/M5.',
              'CPU thread counts are requested budgets, not proof every core is busy. RSS and allocator counters are not physical-footprint measurements.',
              'SVD warning counts reflect logged warnings, not every fallback invocation. Keep failed/incomplete arms in the audit.',
              'No performance profile or package upgrade is promoted by this screening report.', '', 'Incomplete blocks: '+(', '.join(incomplete) or 'none'), '']
    reference=out/'external_reference/comparison.json'
    if reference.exists():
        refs=json.loads(reference.read_text())['rows']
        if refs:
            lines += ['## External structural context','',
                'Post-hoc comparison with [RCSB1UBQ](https://www.rcsb.org/structure/1UBQ); this common training-era protein is not an independent blind holdout.',
                f'Across included ubiquitin outputs: all76-residue C-alpha RMSD {min(r["rmsd_all_angstrom"] for r in refs):.3f}–{max(r["rmsd_all_angstrom"] for r in refs):.3f} A; separately reported residues1–72 {min(r["rmsd_residues_1_72_angstrom"] for r in refs):.3f}–{max(r["rmsd_residues_1_72_angstrom"] for r in refs):.3f} A.',
                'The crystal reports mobile terminal residues. Both full and core values are retained; no acceptance threshold changed after this comparison.','']
    (out/'REPORT.md').write_text('\n'.join(lines));print('\n'.join(lines))


if __name__=='__main__':main()
