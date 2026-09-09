#!/usr/bin/env python3
"""Recheck audited file hashes and inspect paired trajectories and cycle trends."""
import csv
import hashlib
import json
from pathlib import Path
import statistics

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / 'Validation/output/secondary_structure_seed_mask_v1'
ANALYSIS = OUTPUT / 'analysis/full'
ARMS = ('beta_seed_only', 'mixed_seed_only')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    audit = json.loads((ANALYSIS / 'audit.json').read_text())
    comparison = json.loads((ANALYSIS / 'comparison.json').read_text())
    manifest = json.loads((OUTPUT / 'manifest_full.json').read_text())
    assert audit['passed'] and audit['all_complete'] and audit['audited_structures'] == 120
    for relative, expected in audit['raw_sha256'].items():
        path = OUTPUT / relative
        if relative.startswith('job_state/'):
            # The shared audit labels broker state by job ID rather than
            # pretending it is stored inside the campaign output directory.
            path = Path(manifest['runtime']['root']) / 'agent/jobs' / Path(relative).stem / 'state.json'
        assert digest(path) == expected, f'Audited file changed: {relative}'
    inputs = {'manifest': OUTPUT / 'manifest_full.json', 'report': ANALYSIS / 'audit.json',
              'structures': ANALYSIS / 'audited_per_structure.csv',
              'trajectories': ANALYSIS / 'audited_per_trajectory.csv'}
    for name, path in inputs.items():
        assert digest(path) == comparison['input_sha256'][name], f'Summary input changed: {name}'
    with inputs['structures'].open() as handle:
        structures = list(csv.DictReader(handle))
    with inputs['trajectories'].open() as handle:
        trajectories = list(csv.DictReader(handle))
    result = {'raw_checksums_verified': len(audit['raw_sha256']), 'arms': {},
              'method': 'Descriptive follow-up; ten trajectories per arm, cycle00 initialization excluded from primary endpoints.'}
    for arm in ARMS:
        rows = sorted((r for r in trajectories if r['arm'] == arm), key=lambda r:r['run'])
        cycles = []
        for cycle in range(6):
            selected = [r for r in structures if r['arm'] == arm and int(r['cycle']) == cycle]
            assert len(selected) == 10
            cycles.append({'cycle': cycle, **{metric: statistics.mean(float(r[metric]) for r in selected)
                           for metric in ('helix_fraction', 'sheet_fraction', 'coil_fraction', 'binder_plddt')}})
        passed = lambda row, prefix: float(row[prefix+'sheet_fraction']) >= .25 and float(row[prefix+'helix_fraction']) < .4
        result['arms'][arm] = {
            'cohort_cycles': cycles,
            'trajectories_meeting_both_thresholds_on_optimized_mean': sum(passed(r, 'optimized_mean_') for r in rows),
            'trajectories_meeting_both_thresholds_at_final_cycle': sum(passed(r, 'final_') for r in rows),
            'per_trajectory': [{key:r[key] for key in ('run', 'optimized_mean_sheet_fraction', 'optimized_mean_helix_fraction',
                                                       'optimized_mean_binder_plddt', 'final_sheet_fraction', 'final_helix_fraction')}
                               for r in rows],
            'ca_distance_outliers': sum(int(r['ca_distance_outliers']) for r in structures if r['arm'] == arm),
        }
    (ANALYSIS / 'review.json').write_text(json.dumps(result, indent=2)+'\n')

    plt.rcParams.update({'font.family':'Arial', 'font.size':10, 'text.color':'black',
                         'axes.labelcolor':'black', 'xtick.color':'black', 'ytick.color':'black',
                         'svg.fonttype':'none'})
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2))
    colors = ('#2474A8', '#C56C28')
    names = ('Beta only', 'Beta + helix kill')
    ax = axes[0]
    for index,run in enumerate(sorted({r['run'] for r in trajectories})):
        values = [100*float(next(r for r in trajectories if r['run']==run and r['arm']==arm)['optimized_mean_sheet_fraction']) for arm in ARMS]
        offset = .06*(index-4.5)/4.5
        ax.plot([offset,1+offset], values, color='0.65', lw=.8, zorder=1)
        for x,value in enumerate(values):
            ax.scatter(x+offset,value,color=colors[x],edgecolors='black',linewidths=.4,s=28,zorder=2)
    ax.axhline(25,color='black',ls='--',lw=.9)
    ax.set(xticks=[0,1],xticklabels=names,ylabel='Sheet (%)',ylim=(-2,55),xlim=(-.3,1.3),title='Paired trajectory means')
    for index,(metric,label,title) in enumerate((('sheet_fraction','Sheet (%)','Sheet across cycles'),('binder_plddt','Binder pLDDT (0–100)','Confidence across cycles')),1):
        ax = axes[index]
        for arm,color,name in zip(ARMS,colors,names):
            cycles=result['arms'][arm]['cohort_cycles']
            ax.plot(range(6),[100*r[metric] for r in cycles],color=color,marker='o',ms=4,lw=1.3,label=name)
        ax.set(xlabel='Cycle (0 = initialization)',ylabel=label,xticks=range(6),title=title)
        if metric=='sheet_fraction':
            ax.axhline(25,color='black',ls='--',lw=.9)
            ax.set_ylim(0,32)
        else:
            ax.set_ylim(35,100)
    axes[2].legend(frameon=False,loc='lower right',fontsize=9)
    for ax in axes:
        ax.tick_params(direction='in',top=True,right=True)
        ax.grid(False)
    fig.text(.5,.025,'n = 10 trajectories per arm. Left: each line joins one paired seed; each point averages cycles 01–05 (horizontal jitter for visibility).\nMiddle/right: means across 10 trajectories at each cycle. Dashed line: 25% sheet target.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.12,1,1))
    fig.savefig(ANALYSIS/'trajectories.svg',transparent=True)
    fig.savefig(ANALYSIS/'trajectories.png',dpi=180)
    print(json.dumps({'verified_files':result['raw_checksums_verified'],'review':str(ANALYSIS/'review.json'),
                      'figure':str(ANALYSIS/'trajectories.svg')},indent=2))


if __name__ == '__main__':
    main()
