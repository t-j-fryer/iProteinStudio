"""Rebuild analysis and figures from immutable completed block receipts."""
import csv,json,statistics
from pathlib import Path
from analyse import analyse
from preprocessing_audit import audit as preprocessing_audit
from worker import atomic

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2];OUT=REPO/'Validation/output/apple_runtime_kernels_v3'

def main():
    comparisons=[];kernels=[];failures=[];blocks={};profiles=[]
    for run in sorted(OUT.glob('*_20*')):
        if not (run/'frozen/run.json').exists():continue
        cfg=json.loads((run/'frozen/run.json').read_text());engine=cfg['blocks'][0]['engine']
        if (run/'failures.json').exists():failures.append(dict(run=run.name,failures=json.loads((run/'failures.json').read_text())))
        if not (run/'progress.json').exists():continue
        result=analyse(run)
        progress=json.loads((run/'progress.json').read_text())
        if engine=='nesso' and (run/'completed.json').exists():preprocessing_audit(run)
        for name,p in progress.items():
            p=Path(p);blocks[str(p)]=dict(engine=engine,run=run.name,block=name,path=str(p))
            if (p/'kernel.json').exists():kernels.append(dict(run=run.name,**json.loads((p/'kernel.json').read_text())))
            if cfg['blocks'][0].get('detailed_profile') and (p/'telemetry.json').exists():
                profiles.append(dict(run=run.name,census=json.loads((p/'telemetry.json').read_text())))
        if not result['complete'] or not result['pairs']:continue
        rows=[r for r in result['pairs'] if not r['warmup']]
        reference=sum(r['baseline_seconds'] for r in rows);candidate=sum(r['candidate_seconds'] for r in rows)
        parser=json.loads((run/'preprocessing_audit.json').read_text()) if (run/'preprocessing_audit.json').exists() else None
        comparisons.append(dict(run=run.name,engine=engine,seed=cfg['blocks'][0]['seed'],max_length=max(len(c['sequence']) for c in cfg['blocks'][0]['cases']),n=len(rows),reference_seconds=reference,candidate_seconds=candidate,
            time_reduction_percent=100*(1-candidate/reference),passed=result['passed'],
            failures=sorted({f for r in result['pairs'] for f in r['failures']}),
            parser_exact=parser['all_exact'] if parser else None,
            recovery_separated_controls=(run/'recovery_resume.json').exists()))
    units=[]
    for block in blocks.values():
        p=Path(block['path'])
        if not (p/'result.json').exists():continue
        for item in json.loads((p/'result.json').read_text())['rows']:
            m=json.loads(Path(item).read_text());units.append(dict(**block,measurement=m))
    atomic(OUT/'measurements.json',dict(comparisons=comparisons,kernels=kernels,failures=failures,profiles=profiles,
                                       completed_blocks=len(blocks),completed_units=len(units),units=units))
    if comparisons:
        with (OUT/'timings.csv').open('w') as f:
            writer=csv.DictWriter(f,fieldnames=list(comparisons[0]));writer.writeheader();writer.writerows(comparisons)
    lines=['# Mac runtime fusion and integration tests','',
        'Apple M4 Max /40-core GPU /64GB /macOS26.6.1. Same engine-specific runtimes, FP32, fixed seeds and scientific settings. '
        'Boltz keeps physical/FK guidance enabled. Kernel work uses Torch MPS directly; no Torch–MLX transfers.', '',
        f'{len(blocks)} completed blocks; {len(units)} completed prediction/scoring outputs audited. These include warmups and diagnostic profiles, not independent biological designs.', '',
        '## Full calls','',
        'Times sum measured requests, excluding warmups. Each row is a separate process pair. '
        'Repeated inputs are computational repetitions; n is not independent proteins. Positive change means less time. '
        'Recovery tests have controls separated by the queue and are labelled below.', '',
        '| Experiment | n | Reference(s) | Candidate(s) | Less time | Numerical gate | Parser tensors identical |',
        '|---|---:|---:|---:|---:|---|---|']
    for r in comparisons:
        label=r['run']+(' (recovery)' if r['recovery_separated_controls'] else '')
        lines.append(f"| {label} | {r['n']} | {r['reference_seconds']:.3f} | {r['candidate_seconds']:.3f} | {r['time_reduction_percent']:.1f}% | {'PASS' if r['passed'] else ', '.join(r['failures'])} | {r['parser_exact']} |")
    lines+=['','## Operator tests','',
        'Each operator uses an independent NumPy FP64 reference and stock FP32 comparison, relative L2<=1e-5. '
        'Timing includes Python dispatch, layout handling and output allocation:4 alternating blocks ×20 calls after8 warmups. '
        'Compilation is separate. Failed operators never proceed to model tests. See measurements.json for every numerical error and timing block.', '',
        '| Runtime/test | Operator cases | Passing | Compile(s) |', '|---|---:|---:|---:|']
    for k in kernels:lines.append(f"| {k['run']} | {len(k['rows'])} | {sum(r['passed'] for r in k['rows'])} | {k['compile_seconds']:.4f} |")
    lines+=['','## Profiles and retained failures','',
        'Module profiles provide call/shape counts and up to8 synchronized samples per class, including first-use effects. '
        'Nested timings overlap; do not add them or use them as unprofiled GPU kernel durations. Full records are in measurements.json.', '',
        *[f"- {f['run']}: {f['failures']}" for f in failures], '',
        '## Reproduce','',
        '`/usr/bin/python3 Validation/experiments/apple_runtime_kernels_v3/preflight.py ENGINE STAGE --start` creates a new immutable plan and starts it through the shared Studio broker. '
        'Use `--reverse`, `--seed 43` or `--larger` for explicitly recorded confirmation contrasts. '
        'Completed raw blocks are never overwritten; report.py rechecks receipts before analysis.', '',
        '## Limits','',
        'This is one Mac with short, empty-MSA computational fixtures. Larger-length fixtures, when present, are synthetic repeats, '
        'not claims of native biological structure. No interface ranking, MSA-rich campaign, other Apple chip or multi-hour soak is established. '
        'SUMO coordinate gates exclude residues1–20 and use the baseline pLDDT>=80 core; insufficient core remains unassessable. '
        'A passing computational comparison is not experimental binding validation.', '',
        '[Research and sources](../../../docs/APPLE_METAL_FUSION_TESTS.md). Project Lab Book0170; Validation0040.']
    decisions=OUT/'DECISIONS.md'
    if decisions.exists():lines[2:2]=[decisions.read_text(),'']
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
    if comparisons:plot(comparisons)
    print(json.dumps(dict(completed_blocks=len(blocks),completed_units=len(units),comparisons=len(comparisons),operator_cases=sum(len(k['rows']) for k in kernels))))

def plot(rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.family':'Arial','font.size':10,'svg.fonttype':'none','axes.labelcolor':'black','text.color':'black'})
    fig,ax=plt.subplots(figsize=(14,max(5,len(rows)*.48+2)))
    y=np.arange(len(rows));left=[r['reference_seconds']/r['n'] for r in rows];right=[r['candidate_seconds']/r['n'] for r in rows]
    ax.barh(y-.18,left,.34,color='#b9b9b9',edgecolor='black',label='Reference')
    ax.barh(y+.18,right,.34,color=['#5b9c9b' if r['passed'] and r['parser_exact'] is not False else '#c78f68' for r in rows],edgecolor='black',label='Candidate')
    labels=[]
    for r in rows:
        label=r['run'].split('_20')[0].replace('_',' ')
        if r['recovery_separated_controls']:label+=' (recovery)'
        if r['parser_exact'] is False:label+=' [rejected]'
        labels.append(label+f"; seed{r['seed']}, ≤{r['max_length']}aa, n={r['n']}")
    ax.set_yticks(y,labels);ax.invert_yaxis();ax.set_xlabel('Seconds per measured request (arithmetic mean)')
    ax.tick_params(direction='in');ax.grid(False);ax.spines[['top','right']].set_visible(False)
    for i,r in enumerate(rows):
        change=r['time_reduction_percent'];label=f'{abs(change):.1f}% '+('less time' if change>=0 else 'slower')
        ax.text(max(left[i],right[i])+.15,i,label,va='center',fontsize=9)
    ax.set_xlim(0,max(left+right)*1.42);ax.legend(frameon=False,loc='lower right')
    ax.set_title('M4 Max: full-call effects of runtime fusions and caching',loc='left',pad=14)
    fig.text(.03,.025,'Fixed model, steps, recycles and guidance; warmups excluded. Teal: numerical/input checks passed; orange: gate incomplete or changed inputs.\n'
             'Separate process pairs; repeated inputs are not independent designs. See REPORT.md for parser identity, failed kernels and recovery timing caveats.',fontsize=8)
    fig.tight_layout(rect=(0,.09,1,1));fig.savefig(OUT/'OVERVIEW.svg',transparent=True);fig.savefig(OUT/'OVERVIEW.png',dpi=140);plt.close(fig)

if __name__=='__main__':main()
