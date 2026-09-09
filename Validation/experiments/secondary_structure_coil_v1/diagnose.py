#!/usr/bin/env python3
"""Localize coil in the complete paired seed-mask campaign; derived data only.

P-SEA coil is a structural category, not an experimental disorder assignment.
All confidence and gate cutoffs are exploratory. Cycles are averaged within
trajectories before arm summaries; cycle00 is always separately labelled.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path
import numpy as np
from biotite.structure import annotate_sse
from biotite.structure.io.pdbx import CIFFile, get_structure

ROOT = Path(__file__).resolve().parents[3]
ARMS = ('beta_seed_only', 'mixed_seed_only')
LENGTH_BINS = ('1-3', '4-7', '8-15', '16+')
CONFIDENCE_BINS = ('below50', '50to70', '70plus')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contiguous_segments(codes, wanted='c'):
    """Half-open zero-based intervals, including terminal intervals."""
    start = None
    for index, code in enumerate(codes):
        if code == wanted and start is None:
            start = index
        if code != wanted and start is not None:
            yield start, index
            start = None
    if start is not None:
        yield start, len(codes)


def length_bin(length):
    return '1-3' if length <= 3 else '4-7' if length <= 7 else '8-15' if length <= 15 else '16+'


def confidence_bin(value):
    return 'below50' if value < 50 else '50to70' if value < 70 else '70plus'


def summarize_structure(codes, confidence, plan):
    n = len(codes)
    require(n == len(confidence) == len(plan['positions']), 'residue cardinality mismatch')
    require(set(codes) <= set('abc'), 'invalid P-SEA code')
    require(all(np.isfinite(confidence)) and all(0 <= x <= 100 for x in confidence), 'invalid confidence')
    mask = set(plan['x_positions'])
    residues, segments = [], []
    for index, (code, value, position) in enumerate(zip(codes, confidence, plan['positions']), 1):
        require(position['index'] == index, 'seed plan is out of order')
        residues.append(dict(position=index, psea=code, plddt=float(value), confidence_bin=confidence_bin(value), planned_region=position['region'], originally_masked=index in mask))
    for start, end in contiguous_segments(codes):
        values = confidence[start:end]
        terminal = start == 0 or end == n
        visible_values = [r['plddt'] for r in residues[start:end] if not r['originally_masked']]
        masked_values = [r['plddt'] for r in residues[start:end] if r['originally_masked']]
        segments.append(dict(start=start+1, end=end, length=end-start, length_bin=length_bin(end-start), terminal=terminal, mean_plddt=float(np.mean(values)), min_plddt=float(min(values)), visible_count=len(visible_values), visible_mean_plddt=float(np.mean(visible_values)) if visible_values else None, masked_mean_plddt=float(np.mean(masked_values)) if masked_values else None, below50_count=int(sum(values < 50)), below70_count=int(sum(values < 70)), planned_turn_count=sum(row['planned_region']=='turn' for row in residues[start:end]), originally_masked_count=sum(row['originally_masked'] for row in residues[start:end])))
    metrics = dict(helix_fraction=codes.count('a')/n, sheet_fraction=codes.count('b')/n, coil_fraction=codes.count('c')/n, binder_plddt=float(np.mean(confidence)))
    for label in LENGTH_BINS:
        metrics[f'coil_length_{label}_fraction'] = sum(s['length'] for s in segments if s['length_bin']==label)/n
    for label in CONFIDENCE_BINS:
        metrics[f'coil_confidence_{label}_fraction'] = sum(r['psea']=='c' and r['confidence_bin']==label for r in residues)/n
    for terminal, label in ((True,'terminal'), (False,'internal')):
        metrics[f'coil_{label}_fraction'] = sum(s['length'] for s in segments if s['terminal']==terminal)/n
    for region in ('strand','turn'):
        selected = [r for r in residues if r['planned_region']==region]
        metrics[f'coil_at_planned_{region}_fraction_all_residues'] = sum(r['psea']=='c' for r in selected)/n
        metrics[f'coil_rate_within_planned_{region}'] = sum(r['psea']=='c' for r in selected)/len(selected)
    for masked, label in ((True,'masked'), (False,'visible')):
        selected = [r for r in residues if r['originally_masked']==masked]
        metrics[f'coil_rate_within_originally_{label}'] = sum(r['psea']=='c' for r in selected)/len(selected)
        metrics[f'plddt_originally_{label}'] = statistics.mean(r['plddt'] for r in selected)
        for cutoff in (50,60,70):
            metrics[f'low{cutoff}_coil_rate_within_originally_{label}'] = sum(r['psea']=='c' and r['plddt']<cutoff for r in selected)/len(selected)
    for cutoff in (50,60,70):
        # A coil segment's mean confidence and a contiguous run of individually
        # low-confidence coil residues are deliberately distinct metrics.
        metrics[f'max_coil_length_visible_mean_below{cutoff}'] = max((s['length'] for s in segments if s['visible_count']>=4 and s['visible_mean_plddt']<cutoff), default=0)
        metrics[f'long_coil_mean_below{cutoff}_fraction'] = sum(s['length'] for s in segments if s['length']>=16 and s['mean_plddt']<cutoff)/n
        lowcodes = ''.join('c' if c=='c' and p<cutoff else '-' for c,p in zip(codes,confidence))
        metrics[f'max_contiguous_coil_below{cutoff}'] = max((end-start for start,end in contiguous_segments(lowcodes)), default=0)
    metrics['max_coil_length'] = max((s['length'] for s in segments), default=0)
    return residues, segments, metrics


def write_csv(path, rows):
    require(bool(rows), f'no rows for {path}')
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def trajectory_means(rows):
    groups = {}
    for row in rows:
        groups.setdefault((row['arm'],row['run']), []).append(row)
    keys = [key for key in rows[0] if key not in ('arm','run','cycle')]
    return [dict(arm=arm, run=run, **{key:statistics.mean(row[key] for row in group) for key in keys}) for (arm,run),group in sorted(groups.items())]


def endpoint_summary(rows):
    trajectories = trajectory_means(rows)
    keys = [key for key in trajectories[0] if key not in ('arm','run')]
    means = {arm:{key:statistics.mean(row[key] for row in trajectories if row['arm']==arm) for key in keys} for arm in ARMS}
    return dict(arms=means, mixed_minus_beta={key:means[ARMS[1]][key]-means[ARMS[0]][key] for key in keys})


def gates_for_row(row):
    return {
        'coil_ge16_visiblemean_below50': row['max_coil_length_visible_mean_below50'] >= 16,
        'coil_ge16_visiblemean_below60': row['max_coil_length_visible_mean_below60'] >= 16,
        'coil_ge24_visiblemean_below50': row['max_coil_length_visible_mean_below50'] >= 24,
        'coil_ge24_visiblemean_below60': row['max_coil_length_visible_mean_below60'] >= 24,
        'long_low50_run_ge16': row['max_contiguous_coil_below50'] >= 16,
        'long_low60_run_ge16': row['max_contiguous_coil_below60'] >= 16,
        'long_low70_run_ge16': row['max_contiguous_coil_below70'] >= 16,
        'long_low50_run_ge24': row['max_contiguous_coil_below50'] >= 24,
        'long_low60_run_ge24': row['max_contiguous_coil_below60'] >= 24,
        'low50_coil_fraction_ge_one_third': row['coil_confidence_below50_fraction'] >= 1/3,
        'low60_segment_fraction_ge_one_third': row['long_coil_mean_below60_fraction'] >= 1/3,
        'coil_ge70pct_and_mean_plddt_below60': row['coil_fraction'] >= .7 and row['binder_plddt'] < 60,
    }


def retrospective_gates(rows):
    initial = [r for r in rows if r['cycle']==0]
    optimized = {(r['arm'],r['run']):r for r in trajectory_means([r for r in rows if r['cycle']>0])}
    final = {(r['arm'],r['run']):r for r in rows if r['cycle']==5}
    output = {}
    for gate in gates_for_row(initial[0]):
        output[gate] = {}
        for arm in ARMS:
            groups = {}
            for flag in (True,False):
                selected = [r for r in initial if r['arm']==arm and gates_for_row(r)[gate]==flag]
                future = [optimized[(r['arm'],r['run'])] for r in selected]
                last = [final[(r['arm'],r['run'])] for r in selected]
                keys = ('coil_fraction','sheet_fraction','helix_fraction','binder_plddt','coil_confidence_below50_fraction','long_coil_mean_below60_fraction')
                groups['flagged' if flag else 'unflagged'] = dict(n=len(selected), runs=[r['run'] for r in selected], optimized_mean={k:statistics.mean(r[k] for r in future) for k in keys} if future else None, cycle05_mean={k:statistics.mean(r[k] for r in last) for k in keys} if last else None, optimized_structural_target_count=sum(r['sheet_fraction']>=.25 and r['helix_fraction']<.4 for r in future))
            output[gate][arm] = groups
    return output


def initial_coil_fates(residues):
    """Track exact seed coil positions into cycle05 without selecting outcomes."""
    final = {(r['arm'],r['run'],r['position']):r for r in residues if r['cycle']==5}
    groups = {}
    for row in residues:
        if row['cycle'] != 0 or row['psea'] != 'c':
            continue
        key=(row['arm'],row['run'])
        counts=groups.setdefault(key,dict(initial_coil_residues=0,final_helix=0,final_sheet=0,final_coil_below50=0,final_coil_50to70=0,final_coil_70plus=0))
        counts['initial_coil_residues']+=1
        later=final[(row['arm'],row['run'],row['position'])]
        label='final_helix' if later['psea']=='a' else 'final_sheet' if later['psea']=='b' else 'final_coil_'+later['confidence_bin']
        counts[label]+=1
    trajectories=[dict(arm=arm,run=run,**counts) for (arm,run),counts in sorted(groups.items())]
    arms={}
    keys=('final_helix','final_sheet','final_coil_below50','final_coil_50to70','final_coil_70plus')
    for arm in ARMS:
        selected=[r for r in trajectories if r['arm']==arm]
        arms[arm]={'mean_fraction_of_initial_coil_positions':{k:statistics.mean(r[k]/r['initial_coil_residues'] for r in selected) for k in keys},'n_trajectories':len(selected)}
    return dict(arms=arms,per_trajectory_counts=trajectories)


def plot_maps(residues, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    plt.rcParams.update({'font.family':'Arial','text.color':'black','axes.labelcolor':'black','xtick.direction':'in','ytick.direction':'in','svg.fonttype':'none'})
    fig, axes = plt.subplots(2,3,figsize=(15,7),sharex=True,sharey=True)
    for ai,arm in enumerate(ARMS):
        for ci,cycle in enumerate((0,1,5)):
            data=np.zeros((10,90))
            for r in residues:
                if r['arm']==arm and r['cycle']==cycle:
                    value=0 if r['psea']=='a' else 1 if r['psea']=='b' else 2 if r['plddt']>=70 else 3 if r['plddt']>=50 else 4
                    data[int(r['run'].split('_')[1])-1,r['position']-1]=value
            ax=axes[ai,ci]
            ax.imshow(data,aspect='auto',interpolation='nearest',cmap=ListedColormap(['#db8c78','#557ca8','#c4c4c4','#efb95d','#8c4aa1']),vmin=0,vmax=4,extent=(.5,90.5,10.5,.5))
            ax.set_title(f'{arm.replace("_seed_only", "")} · cycle {cycle:02d}')
            ax.set_xticks([1,30,60,90]);ax.set_yticks(range(1,11));ax.set_xlabel('Binder residue');ax.set_ylabel('Trajectory')
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(facecolor=c,edgecolor='black',label=l) for c,l in zip(['#db8c78','#557ca8','#c4c4c4','#efb95d','#8c4aa1'],['Helix','Sheet','Coil pLDDT ≥70','Coil 50–70','Coil <50'])],loc='lower center',ncol=5)
    fig.suptitle('P-SEA and residue confidence; 10 paired trajectories per arm (cycle 00 is initialization)')
    fig.tight_layout(rect=(0,.055,1,.96))
    fig.savefig(output/'residue_maps.svg',transparent=True)
    fig.savefig(output/'residue_maps.png',dpi=150)
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT/'Validation/output/secondary_structure_seed_mask_v1')
    parser.add_argument('--output',type=Path,default=ROOT/'Validation/output/secondary_structure_coil_v1/diagnosis')
    parser.add_argument('--binder-chain',default='A')
    args=parser.parse_args(); source=args.root.resolve(); output=args.output.resolve()
    report_path=source/'analysis/full/audit.json'
    audit=json.loads(report_path.read_text())
    require(audit['passed'] and audit['all_complete'] and audit['audited_structures']==120,'requires complete passing 120-structure audit')
    source_csv=source/'analysis/full/audited_per_structure.csv'
    rows=list(csv.DictReader(source_csv.open()))
    require(len(rows)==120 and len({(r['arm'],r['run'],r['cycle']) for r in rows})==120,'duplicate/missing input rows')
    residues,segments,structures=[],[],[]
    verified={}
    for row in rows:
        arm,run,cycle=row['arm'],row['run'],int(row['cycle'])
        require(arm in ARMS and 1<=int(run.split('_')[1])<=10 and 0<=cycle<=5,'unexpected arm/run/cycle')
        path=source/row['structure']
        actual=sha256(path)
        require(actual==audit['raw_sha256'][row['structure']],f'coordinate hash mismatch: {path}')
        verified[row['structure']]=actual
        plan_label=f'campaigns/full__{arm}/{run}/secondary_structure_plan.json'
        plan_path=source/plan_label
        require(sha256(plan_path)==audit['raw_sha256'][plan_label],f'seed plan hash mismatch: {plan_path}')
        verified[plan_label]=sha256(plan_path)
        plan=json.loads(plan_path.read_text())
        atoms=get_structure(CIFFile.read(path),model=1,extra_fields=['b_factor'])
        require(bool(np.isfinite(atoms.coord).all()),'nonfinite coordinates')
        chain=atoms[atoms.chain_id==args.binder_chain]; ca=chain[chain.atom_name=='CA']
        codes=''.join(annotate_sse(chain))
        require(len(ca)==len(codes)==90 and codes==row['psea'],'P-SEA/cardinality differs from original audit')
        rr,ss,mm=summarize_structure(codes,np.asarray(ca.b_factor,dtype=float),plan)
        require(abs(mm['binder_plddt']/100-float(row['binder_plddt']))<1e-9,'residue confidence differs from audit')
        identity=dict(arm=arm,run=run,cycle=cycle)
        residues.extend(dict(**identity,**r) for r in rr)
        segments.extend(dict(**identity,**s) for s in ss)
        structures.append(dict(**identity,**mm))
    result=dict(schema=1,method={'assignment':'Biotite P-SEA recomputed against verified raw coordinates','confidence':'Binder CA b_factor, pLDDT on 0–100 scale','unit':'Average cycles01–05 within trajectory, then equal-weight average of 10 trajectories; cycle00 and cycle05 separately','coil_warning':'P-SEA coil includes structured loops and turns; low confidence is not a validated disorder annotation','gate_warning':'All gates are retrospective exploratory sensitivity analyses, not prospectively validated classifiers; no intervention effects can be inferred','segment_definition':'Maximal contiguous P-SEA coil; terminal if touches either binder terminus','long_segment_definition':'At least 16 residues; segment-mean thresholds differ from contiguous individually-low-confidence runs','planned_regions_warning':'Seed-plan positional labels are hypotheses, not observed strand/turn labels; carried across cycles for positional localization only','fraction_denominator':'All 90 binder residues unless metric explicitly says rate_within'},source_audit_sha256=sha256(report_path),source_csv_sha256=sha256(source_csv),verified_raw_sha256=verified,counts=dict(structures=len(structures),residues=len(residues),coil_segments=len(segments)),endpoints={label:endpoint_summary([r for r in structures if predicate(r['cycle'])]) for label,predicate in [('cycle00',lambda c:c==0),('optimized_cycles01_05',lambda c:c>0),('cycle05',lambda c:c==5)]},retrospective_cycle00_gates=retrospective_gates(structures),initial_coil_fates_at_cycle05=initial_coil_fates(residues))
    output.mkdir(parents=True,exist_ok=True)
    write_csv(output/'per_residue.csv',residues);write_csv(output/'coil_segments.csv',segments);write_csv(output/'per_structure.csv',structures)
    write_csv(output/'per_trajectory_optimized.csv',trajectory_means([r for r in structures if r['cycle']>0]))
    (output/'diagnosis.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    plot_maps(residues,output)
    print(json.dumps({'output':str(output),'counts':result['counts'],'optimized':result['endpoints']['optimized_cycles01_05']},indent=2))

if __name__=='__main__':
    main()
