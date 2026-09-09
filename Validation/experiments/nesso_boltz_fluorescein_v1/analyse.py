#!/usr/bin/env python3
"""Audit paired receipts, then render timing and score-agreement artifacts."""
import argparse
import csv
import hashlib
import json
import os
import shutil
from pathlib import Path
import sys
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/iproteinstudio-nesso-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import pearsonr, spearmanr


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''): h.update(b)
    return h.hexdigest()


def read(path): return json.loads(Path(path).read_text())


def write_csv(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def analyse(output):
    stage=output/'full'; audit=read(stage/'audit.json')
    if audit['status']!='passed' or audit['paired_candidates']!=50: raise ValueError('Full paired audit required')
    for name,h in audit['completed_files'].items():
        if digest(stage/name)!=h: raise ValueError('Receipt changed: '+name)
    selection=read(output/'selection.json'); manifest=read(output/'manifest.json'); rows=[]
    for r in selection:
        results={}
        for engine in ('boltz','nesso'):
            receipt=read(stage/engine/r['name']/'completed.json')
            if receipt['input']['sequence']!=r['sequence']: raise ValueError('Sequence mismatch')
            for name,h in receipt['files'].items():
                if digest(stage/name)!=h: raise ValueError('Raw artifact changed: '+name)
            results[engine]=receipt['result']
        b,n=results['boltz'],results['nesso'];scores=n['scores']; ent=scores['entropy_crop_pl']
        valid=ent is not None and np.isfinite(ent) and 1e-6<ent<=1
        rows.append(dict(candidate=r['name'],phase=r['phase'],cycle=int(r['cycle']),origin=r['origin'],sequence=r['sequence'],length=len(r['sequence']),
                         historical_score=float(r['score']),historical_pbind=float(r['pbind']),historical_ligand_plddt=float(r['ligand_plddt']),
                         boltz_wall_s=b['wall_seconds'],nesso_wall_s=n['wall_seconds'],nesso_esm_s=n['native']['esm_seconds'],nesso_inference_s=n['native']['inference_seconds'],
                         boltz_pbind=b['scores']['pbind'],boltz_ligand_plddt=b['scores']['ligand_plddt'],boltz_combined=b['combined'],
                         nesso_pbind=scores['affinity_probability_binary'],nesso_entropy_crop_pl=ent,
                         nesso_placement_confidence=1-ent if valid else None,nesso_entropy_full_pl=scores['entropy_pl'],
                         nesso_combined=n['combined'],nesso_placement_eligible=valid,
                         nesso_affinity_pred_value=scores['affinity_pred_value'],boltz_affinity_pred_value=b['affinity']['affinity_pred_value'],
                         boltz_session=b['session'],nesso_session=n['session']))
    out=output/'analysis';out.mkdir(exist_ok=True)
    if Path(__file__).resolve() != (out/'generator.py').resolve():
        shutil.copy2(__file__,out/'generator.py')
    write_csv(out/'paired_metrics.csv',rows)
    def arr(key): return np.array([float('nan') if r[key] is None else r[key] for r in rows],float)
    rng=np.random.default_rng(17)
    bt,nt=arr('boltz_wall_s'),arr('nesso_wall_s')
    indices=rng.integers(0,len(rows),(10000,len(rows)))
    ratios=bt[indices].mean(axis=1)/nt[indices].mean(axis=1)
    ratio_ci=np.quantile(ratios,[.025,.975]).tolist()
    timing=[]
    for name,key in [('Boltz2 structure + affinity','boltz_wall_s'),('NESSO + fresh ESM','nesso_wall_s'),('NESSO model only','nesso_inference_s'),('ESM only','nesso_esm_s')]:
        a=arr(key); timing.append(dict(method=name,n=len(a),total_seconds=float(a.sum()),mean_seconds=float(a.mean()),median_seconds=float(np.median(a)),p10_seconds=float(np.quantile(a,.1)),p90_seconds=float(np.quantile(a,.9))))
    write_csv(out/'timing.csv',timing)
    pairs=[('nesso_pbind','boltz_pbind'),('nesso_placement_confidence','boltz_ligand_plddt'),('nesso_combined','boltz_combined'),
           ('nesso_pbind','boltz_combined'),('nesso_placement_confidence','boltz_combined'),('nesso_combined','boltz_pbind'),
           ('nesso_combined','boltz_ligand_plddt'),('nesso_entropy_full_pl','boltz_ligand_plddt'),
           ('nesso_affinity_pred_value','boltz_affinity_pred_value'),('historical_score','boltz_combined')]
    correlations=[]
    for x,y in pairs:
        a,b=arr(x),arr(y);mask=np.isfinite(a)&np.isfinite(b)
        correlations.append(dict(x=x,y=y,n=int(mask.sum()),pearson=float(pearsonr(a[mask],b[mask]).statistic),spearman=float(spearmanr(a[mask],b[mask]).statistic)))
    write_csv(out/'correlations.csv',correlations)
    valid=[r for r in rows if r['nesso_placement_eligible']]
    def top(key): return {r['candidate'] for r in sorted(valid,key=lambda r:(-r[key],r['candidate']))[:10]}
    overlap=len(top('nesso_combined')&top('boltz_combined'))
    retention=[]
    for k in (5,10,20,30,50):
        shortlist={r['candidate'] for r in sorted(valid,key=lambda r:(-r['nesso_combined'],r['candidate']))[:k]}
        retention.append(dict(nesso_shortlist_size=k,boltz_top10_retained=len(shortlist & top('boltz_combined'))))
    write_csv(out/'shortlist_retention.csv',retention)
    warmups=[]
    for p in stage.glob('*/warmups/*/warmup.json'):
        w=read(p);warmups.append(dict(engine=w['result']['engine'],startup_s=w['process_startup_wall_seconds'],warmup_s=w['result']['wall_seconds'],session=w['result']['session']))
    write_csv(out/'startup_and_warmup.csv',warmups)
    summary=dict(n=len(rows),origins=len({r['origin'] for r in rows}),hardware=manifest['hardware'],speed_ratio_boltz_over_nesso=float(bt.mean()/nt.mean()),
                 ratio_bootstrap_95ci=ratio_ci,ratio_ci_scope='paired resampling of these 50 cases; excludes between-run and thermal uncertainty',
                 timing=timing,correlations=correlations,shortlist_retention=retention,top10_overlap=overlap,eligible_placements=len(valid),warmups=warmups,sessions=audit['sessions'])
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    plt.rcParams.update({'font.family':'Arial','font.size':10,'text.color':'black','axes.labelcolor':'black','xtick.color':'black','ytick.color':'black','axes.edgecolor':'black','xtick.direction':'in','ytick.direction':'in','axes.grid':False,'svg.fonttype':'none'})
    fig,axs=plt.subplots(2,3,figsize=(14,8.3),layout='constrained')
    ax=axs[0,0]
    ax.bar([0,1],[bt.mean(),nt.mean()],color=['#d98852','#5b9bb2'],edgecolor='black',linewidth=1,width=.6)
    for j,a in enumerate((bt,nt)):
        ax.scatter(np.full(len(a),j)+np.linspace(-.18,.18,len(a)),a,s=11,c='black',alpha=.5,zorder=3)
    ax.set_xticks([0,1],['Boltz2 + affinity','NESSO + ESM']);ax.set_ylabel('Seconds per design');ax.set_title(f'A  Resident request time: {bt.mean()/nt.mean():.2f}× ratio',loc='left')
    labels={'nesso_pbind':'NESSO P(bind)','boltz_pbind':'Boltz2 P(bind)','nesso_placement_confidence':'NESSO 1 − cropped placement entropy','boltz_ligand_plddt':'Boltz2 ligand pLDDT','nesso_combined':'NESSO combined score','boltz_combined':'Boltz2 combined score','historical_score':'Historical Boltz combined score'}
    for ax,(x,y),letter in zip([axs[0,1],axs[0,2],axs[1,0],axs[1,1]],pairs[:3]+[pairs[-1]],'BCDE'):
        a,b=arr(x),arr(y);mask=np.isfinite(a)&np.isfinite(b)
        scatter=ax.scatter(a[mask],b[mask],c=arr('historical_score')[mask],cmap='viridis',vmin=arr('historical_score').min(),vmax=arr('historical_score').max(),s=35,edgecolor='black',linewidth=.4)
        rho=spearmanr(a[mask],b[mask]).statistic
        ax.set(xlabel=labels[x],ylabel=labels[y]);ax.set_title(f'{letter}  Spearman ρ = {rho:.3f}; n = {mask.sum()}',loc='left')
    fig.colorbar(scatter,ax=[axs[0,1],axs[0,2],axs[1,0],axs[1,1]],label='Historical combined score',shrink=.8,pad=.02)
    ax=axs[1,2]
    ax.scatter(arr('length'),bt,label='Boltz2 + affinity',c='#d98852',edgecolor='black',linewidth=.4)
    ax.scatter(arr('length'),nt,label='NESSO + ESM',c='#5b9bb2',edgecolor='black',linewidth=.4)
    ax.set(xlabel='Protein length (residues)',ylabel='Seconds per design');ax.set_title('F  Timing by protein length',loc='left');ax.legend(frameon=False)
    fig.suptitle('Fluorescein: resident NESSO versus Boltz2 scoring\n50 paired sequences · 16 source lineages · Apple M4 Max / 64 GB',fontsize=15)
    fig.savefig(out/'overview.svg',transparent=True);fig.savefig(out/'overview.png',dpi=180)
    plt.close(fig)
    report=['# Resident NESSO versus Boltz2: fluorescein scoring','',
            f"On {manifest['hardware']} / 64 GB, resident NESSO including fresh ESM averaged **{nt.mean():.2f} s/design**, versus **{bt.mean():.2f} s/design** for resident Boltz2 structure plus affinity: **{bt.mean()/nt.mean():.2f}× faster** on this selected cohort.",'',
            f"Score agreement is weak: combined-score Spearman ρ = {correlations[2]['spearman']:.3f}, and a NESSO top-20 shortlist retains only {retention[2]['boltz_top10_retained']}/10 of Boltz’s top ten. Fresh Boltz scores closely track the historical ranking (ρ = {correlations[-1]['spearman']:.3f}). This cohort does not support treating NESSO as a close replacement for Boltz ranking or using a narrow NESSO-only shortlist to preserve Boltz’s preferred designs.",'',
            '![Timing and score agreement](overview.png)','',
            'Figure: each point is one selected sequence (50 paired sequences from 16 lineages), with one measured request per model. Bars show arithmetic means; scatter colors show the historical combined score. Startup and warmup are excluded.','',
            '| Method | n | Mean s/design | Median s/design | Total seconds |','|---|---:|---:|---:|---:|']
    for t in timing:report.append(f"| {t['method']} | {t['n']} | {t['mean_seconds']:.3f} | {t['median_seconds']:.3f} | {t['total_seconds']:.2f} |")
    report += ['',f"The ratio of mean request times is {bt.mean()/nt.mean():.3f}; paired-case bootstrap 95% interval {ratio_ci[0]:.3f}–{ratio_ci[1]:.3f}. This interval only resamples the selected cases; it does not measure thermal, repeat-run or machine uncertainty.",'',
               'Model startup and one warmup per session are excluded above and reported in [startup_and_warmup.csv](startup_and_warmup.csv). Boltz warmup includes its lazy affinity checkpoint load. NESSO times include fresh ESM embeddings, preprocessing, scoring and output writing. Boltz times include preprocessing, structure diffusion, affinity, output writing and its normal geometry check. These are native production pipeline costs, not equal-operation model benchmarks.','',
               '| Metrics | n | Pearson r | Spearman ρ |','|---|---:|---:|---:|']
    for c in correlations:report.append(f"| {c['x']} vs {c['y']} | {c['n']} | {c['pearson']:.3f} | {c['spearman']:.3f} |")
    report += ['', '| NESSO shortlist size | Boltz top ten retained |', '|---:|---:|']
    report += [f"| {r['nesso_shortlist_size']} | {r['boltz_top10_retained']}/10 |" for r in retention]
    report += ['',f"Valid NESSO placements: **{len(valid)}/50**. Combined-score top-ten overlap: **{overlap}/10** among eligible placements. NESSO rank = P(bind)+(1−entropy_crop_pl); Boltz rank = P(bind)+ligand pLDDT/100. Invalid/near-zero entropy receives no rank, never a perfect score.",'',
               'All 50 protein sequences and the standardized ligand chemical state match across the paired methods. Historical scores were used only to freeze selection, including endpoints 0.6552–1.9683. Protein lengths are 65–141 residues, from 16 source lineages; related sequences are not independent backbones. The cohort includes designed initial-refinement sequences and NISE descendants, excluding masked cycle00.','',
               'The historical charged ligand is protonated by Boltz affinity standardization; both new methods receive that same recorded standardized SMILES. Historical YAMLs and constraints are retained. This comparison uses no template, no pocket restraint and an empty Boltz MSA. It is a fresh sequence-to-score comparison, not a backbone-rescoring or exact historical replay.','',
               'NESSO uses pinned float32 MPS, five recycles with refinement and ESM-2; Boltz uses float32 MPS, three recycles, 200 diffusion steps, one structure sample, physical potentials and its affinity head. The Boltz affinity head separately uses its native 5 recycles, 200 diffusion steps and 3 samples, frozen in source provenance. The only permitted CPU operator fallback is Boltz’s documented linalg SVD; its warning records are retained in the audit (warning count is not an operator-call count).','',
               'There is one measured pass and a fixed NESSO-then-Boltz order, following a separate three-case pilot. Neither model runs concurrently with the other or the stopped Studio design batch. Resident session IDs and model-load counts are audited; process caching is not evidence that Lightning keeps every tensor on GPU between calls. Any normal transfer overhead remains included.','',
               'These correlations describe agreement with another computational model for one ligand and a selected score range. They do not establish binding accuracy, calibrate entropy as pLDDT, or validate a complete NISE search. Lower affinity values denote stronger predicted binding, but the two model scales should not be treated as experimental measurements. No default is promoted.','',
               'Artifacts: [paired metrics](paired_metrics.csv), [correlations](correlations.csv), [timing](timing.csv), [machine-readable summary](summary.json), [SVG overview](overview.svg). Full model/input fingerprints, raw outputs, atomic receipts and audits are retained in the parent campaign directory.']
    (out/'REPORT.md').write_text('\n'.join(report)+'\n')
    (out/'artifact_audit.json').write_text(json.dumps(dict(status='passed',paired_candidates=50,raw_receipts_verified=100,derived_files={p.name:digest(p) for p in out.iterdir() if p.is_file() and p.name!='artifact_audit.json'}),indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    analyse(p.parse_args().output.resolve())
