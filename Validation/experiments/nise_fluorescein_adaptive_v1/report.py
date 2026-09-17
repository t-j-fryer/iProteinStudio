#!/usr/bin/env python3
"""Generate a readable report from the audited immutable extraction."""
import argparse,csv,html,json,statistics
from pathlib import Path
import numpy as np

def read(p): return list(csv.DictReader(p.open()))
def render(out):
    audit=json.loads((out/'audit.json').read_text());assert audit['status']=='passed'
    summary=json.loads((out/'summary.json').read_text());rows=read(out/'cycles.csv');sim=read(out/'adaptive_subsets.csv')
    candidates=read(out/'candidates.csv');group={}
    for r in candidates:group.setdefault((int(r['cycle']),int(r['trajectory'])),[]).append(r)
    rng=np.random.default_rng(20260916);comparison=[]
    for st in rows:
        if int(st['missing_affinity']):continue
        rs=sorted(group[int(st['cycle']),int(st['trajectory'])],key=lambda r:int(r['sample']))
        vals=np.array([float(r['score']) if r['geometry_passed']=='True' else -np.inf for r in rs])
        orders=np.array([rng.permutation(64) for _ in range(2000)])
        cum=np.maximum.accumulate(vals[orders],axis=1)
        for policy in ('fixed16','fixed32','adaptive16','adaptive32','fixed64'):
            if policy.startswith('fixed'):sizes=np.full(2000,int(policy[5:]))
            else:
                sizes=np.full(2000,64)
                for n in ((32,16) if policy=='adaptive16' else (32,)):
                    sizes[cum[:,n-1]>float(st['prior_best'])+.01]=n
            best=cum[np.arange(2000),sizes-1];loss=float(st['best_score'])-best
            comparison.append(dict(cycle=int(st['cycle']),trajectory=int(st['trajectory']),policy=policy,
                mean_proposals=float(sizes.mean()),exact_best=float(np.mean(loss<1e-10)),
                within_001=float(np.mean(loss<=.01)),no_passing=float(np.mean(~np.isfinite(best)))))
    with (out/'policy_comparison.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(comparison[0]));w.writeheader();w.writerows(comparison)
    lines=['# Fluorescein NISE: score progression and adaptive-sampling retrospective','',
        'Analysis date: 2026-09-16. Original NanoHunter `output/nise_fluorescein` campaign; not `nise_fluorescein_v2` or a recent Studio trial.', '',
        '**Recommendation: keep adaptive sampling off and retain 64 proposals per parent while deciding the policy. Separate the top-up stopping threshold from the patience threshold. The proposed >0.01 top-up rule offers modest conditional savings and sometimes skips much better candidates.**','',
        'New Studio defaults have been changed, at the user’s request, to **1,000 starts, maximum 30 optimisation cycles and four-cycle patience**. Eight seed trajectories and beam three are unchanged. Existing saved settings are retained. The current shared improvement setting remains 0.01; this report recommends separating it before adopting an adaptive policy, not treating that number as empirically validated.', '',
        '## Evidence and audit','',
        f"Read {audit['folds']:,} raw NISE PDB predictions across {audit['cycles']} trajectory-cycles, each with 64 proposals and beam one. All 85 parent structures were verified by their preparation remarks and exact Cα coordinates. Candidate protein sequences matched the saved YAMLs; all 2,615 recorded passing rows agreed with recomputed Cα/ligand RMSDs. The next-cycle preparations confirm 79 actual advances; the six final-cycle winners were not advanced.", '',
        '53 predictions lack affinity, all in cycle 5. Their scores remain missing. Fifteen appear in the historical passing table with the old ligand-pLDDT-only fallback; that fallback is not accepted as a combined score here. Six cycle-five groups are excluded from sampling simulations, leaving 79 complete groups. Historical progression includes only observed combined scores and therefore cannot recover the missing affinity values. Source files are checksum-audited (21,807 files).','',
        'The saved config’s `num_starts=12` was overwritten on resume: the historical campaign actually began with 100 cycle-00 starts. Neither that field nor the currently installed code establishes the original runtime/checkpoint fingerprint. No neural inference or throughput benchmarking was performed.','',
        '## Progress in each trajectory','',
        'Trajectory identifiers below are the original **zero-based T0–T5**; the Studio interface may display them as 1–6. Score = ligand pLDDT/100 + P(bind).','',
        '| Trajectory | Seed score | Peak score | Peak cycle | Last cycle | Peak ligand pLDDT | Peak P(bind) | Typical winner − passing median |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in summary['trajectories']:
        lines.append(f"| T{r['trajectory']} ({r['origin']}) | {r['seed_score']:.4f} | {r['peak']:.4f} | {r['peak_cycle']} | {r['last_cycle']} | {r['ligand_plddt']:.2f} | {r['pbind']:.4f} | {r['median_winner_minus_median']:.3f} |")
    lines += ['', '![Score distributions and confirmed advanced parents](trajectory_distributions.png)',
        '[Vector figure](trajectory_distributions.svg) · [Cycle-by-cycle data](cycles.csv) · [All 5,440 candidates](candidates.csv)', '',
        'Bands show the 10th–90th percentiles of all scored candidates (grey) and geometry-passing scored candidates (blue); lines show their medians. Orange is the best passing score of each cycle, black dashed is best-so-far, and black circles confirm actual next-parent use. Cycle-five distributions omit missing affinity values. The statistical unit is a proposal within an observed trajectory-cycle; late cycles contain only surviving trajectories.', '',
        '**Winner quality:** the median cycle had 32 geometry-passing, fully scored candidates but only **one within 0.01 of the cycle winner**. The median winner-to-passing-median gap was **0.171**. All 79 confirmed advances were the highest-scoring eligible candidates. In **24/79**, at least one geometry-rejected candidate had a higher raw score. One advanced candidate ranked 35th of 64 by raw score; its higher-scoring alternatives failed geometry. Geometry cannot be ignored when evaluating sampling quality.','',
        '## The 0.01 threshold hides real improvements','',
        'Across the 85 cycles, **30** increased best-so-far by >0.0001, but only **20** exceeded 0.01. Ten observed gains would therefore fail that larger test. These are model-score differences, not evidence of experimentally meaningful affinity improvements.','',
        '- T4, the global winner: cycle 5 **1.95471** → cycle 6 **1.96148** (+0.00678) → cycle 9 **1.96828** (+0.00679).',
        '- T3: cycle 10 **1.93712** → cycle 11 **1.93758** (+0.00046) → cycle 13 **1.94114** (+0.00356).',
        '- T5: its best score arrived in **cycle 20**, through several small improvements separated by unproductive cycles. This is one reason an eight-cycle cap was poorly matched to this run.','',
        '![Cycle increments](cycle_improvements.png)', '[Vector increments](cycle_improvements.svg)', '',
        '![Score components](score_components.png)', '[Vector components](score_components.svg)', '',
        'Most seed-to-peak gains came from P(bind), rather than ligand pLDDT. For T4 the contributions were +0.29587 P(bind) and +0.14080 normalized ligand pLDDT; for T5, +0.39073 and +0.04796. T2 instead increased normalized pLDDT by +0.06735 while P(bind) decreased by 0.01795. A single total-score improvement threshold conceals these different behaviours.','',
        '## Conditional replay of proposal subsets','',
        'For each complete 64-proposal cycle, sample 2,000 permutations without replacement. Keep its **historical parent and prior best fixed**. Stop at 16 or 32 only if the subset winner improves on the prior best by >0.01; otherwise use all 64. All filters remain in force. These are 79 observed groups, not 158,000 independent biological replicates.','',
        '| Proposal policy | Mean proposals | Reduction vs 64 | Exact cycle winner retained | Within 0.01 of full-batch winner |', '|---|---:|---:|---:|---:|']
    for policy in ('fixed16','fixed32','adaptive16','adaptive32','fixed64'):
        a=[r for r in comparison if r['policy']==policy];count=statistics.mean(r['mean_proposals'] for r in a)
        lines.append(f"| {policy} | {count:.2f} | {100*(1-count/64):.1f}% | {100*statistics.mean(r['exact_best'] for r in a):.1f}% | {100*statistics.mean(r['within_001'] for r in a):.1f}% |")
    lines+=['', '**16→32→64 with >0.01:** mean **56.35 proposals**, a **12.0% proposal reduction**. It retains the exact full-batch cycle winner **92.3%** of the time; **7.2%** of decisions lose more than 0.01. Most cycles still exhaust 64. These are conditional proposal counts, not measured elapsed-time savings.','',
        'Using the actual recorded sample order instead of random permutations gives **56.51 proposals** on average and changes the winner in **5/79** complete cycles. Examples:','',
        '| Trajectory / cycle | Stops at | Full-batch score missed by |','|---|---:|---:|']
    for r in sim:
        if float(r['threshold'])==.01 and float(r['prefix_score_loss'])>1e-10:
            lines.append(f"| T{r['trajectory']} / {r['cycle']} | {r['prefix_proposals']} | {float(r['prefix_score_loss']):.5f} |")
    lines+=['','In particular, T3 cycle 10 would stop at 32, missing another **0.1062** score improvement. Satisfying a modest improvement threshold is not evidence that a batch has found its best proposals.','',
        'Once a different parent is advanced, later historical proposals are no longer a valid counterfactual. Therefore these calculations do **not** establish final-winner retention, campaign-wide savings, three-parent-beam behaviour, or benefits with NESSO/RFdiffusion3.','',
        '## Four-cycle patience: explicit trade-off','',
        'Applied to the recorded path, four-cycle patience would retain the peaks of T0–T4. T5 would stop at cycle **9** with an improvement tolerance of 0.0001 (or 0.001), missing its later gain from **1.94325 to 1.95860**. With the current shared 0.01 setting it would stop as early as cycle **6**, retaining the same observed peak. This is the compute/exploration trade-off of the requested four-cycle patience; the missing cycle-five affinities prevent a complete-data counterfactual.','',
        '[Patience sensitivity table](patience4.csv) · [All adaptive-subset results](adaptive_subsets.csv) · [Policy comparison](policy_comparison.csv)','',
        '## Recommendation before changing adaptive behaviour','',
        '1. Keep the requested 1,000-start / 30-cycle / four-patience defaults and keep adaptive sampling **off** for now.',
        '2. Separate **patience tolerance** from **top-up stopping tolerance**. Test 0.0001 or 0.001 for patience; 0.01 is too large to represent every observed improvement. No threshold has been prospectively validated.',
        '3. If piloting adaptation, compare **32→64** against fixed 64 first, and evaluate the quality of the **whole three-parent beam**. The old one-parent run cannot identify a validated beam-wide stopping rule.',
        '4. Use independent prospective trajectories and final-filter-passing candidates per unit compute to decide adoption. Do not infer final search quality from retaining this cycle’s best score. No rollback or rescue is proposed.','',
        '## Reproducibility','',
        'The extraction script, settings and source hashes are in `generator.py` and `manifest.json`; `audit.json` records validation. Executable code and commands are under `Validation/experiments/nise_fluorescein_adaptive_v1/`. Raw campaign files were read only.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    page='<!doctype html><meta charset="utf-8"><title>Fluorescein NISE retrospective</title><style>body{font:16px Arial;max-width:1500px;margin:30px auto;padding:0 20px;color:#111}img{width:100%}pre{white-space:pre-wrap;line-height:1.5}</style><h1>Fluorescein NISE retrospective</h1><p><a href="REPORT.md">Full report</a> · <a href="cycles.csv">Per-cycle data</a></p>'
    for name in ['trajectory_distributions','cycle_improvements','score_components']:page+=f'<img src="{name}.svg" alt="{name}">'
    page+='<pre>'+html.escape('\n'.join(lines))+'</pre>'
    (out/'GALLERY.html').write_text(page)
    print(out/'REPORT.md')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);render(p.parse_args().output)
