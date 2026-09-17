#!/usr/bin/env python3
"""Read-only audit and within-cycle sampling retrospective of saved fluorescein NISE."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import numpy as np
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/nise-fluorescein-retrospective-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

AA=dict(zip('ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split(),'ARNDCQEGHILKMFPSTWYV'))

def sha(data): return hashlib.sha256(data).hexdigest()
def write_json(path,value): path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def table(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def coordinates(text):
    ca=[]; ligand=[]; names=[]; b=[];seq=[]
    for line in text.splitlines():
        if not line.startswith(('ATOM  ','HETATM')):continue
        xyz=[float(line[a:a+8]) for a in (30,38,46)]
        if not np.isfinite(xyz).all():raise ValueError('Nonfinite coordinates')
        if line[21]=='A' and line[12:16].strip()=='CA':
            ca.append(xyz);seq.append(AA.get(line[17:20],'X'))
        if line[21]=='B' and line[76:78].strip()!='H':
            ligand.append(xyz);names.append((line[12:16].strip(),line[76:78].strip()));b.append(float(line[60:66]))
    return np.array(ca),np.array(ligand),names,float(np.mean(b)) if b else None,''.join(seq)

def consistency(pred,ref):
    P,L,ids,_,_=pred;Q,M,jds,_,_=ref
    if len(P)!=len(Q) or len(P)<3 or ids!=jds or not ids:raise ValueError('Atom correspondence mismatch')
    Pc=P-P.mean(0);Qc=Q-Q.mean(0)
    U,_,Vt=np.linalg.svd(Pc.T@Qc);D=np.diag([1,1,np.sign(np.linalg.det(Vt.T@U.T))]);R=Vt.T@D@U.T
    return float(np.sqrt(np.mean(np.sum(((R@Pc.T).T-Qc)**2,axis=1)))),float(np.sqrt(np.mean(np.sum(((R@(L-P.mean(0)).T).T+Q.mean(0)-M)**2,axis=1))))

def analyse(source,output,config):
    if output.exists():raise ValueError('Use a fresh output directory; analysis artifacts are immutable')
    output.mkdir(parents=True)
    fingerprints={}
    def read(p):
        data=p.read_bytes();fingerprints[str(p.relative_to(source))]=sha(data);return data.decode()
    trajectory=list(csv.DictReader(read(source/'trajectory.csv').splitlines()))
    recorded={r['name']:r for r in trajectory if r['phase']=='nise'}
    if len(recorded)!=sum(r['phase']=='nise' for r in trajectory):raise ValueError('Duplicate trajectory rows')
    historical_config=json.loads(read(source/'config.json'))
    summary=json.loads(read(source/'summary.json'))
    all_pdbs={}
    for p in source.rglob('*_model_0.pdb'):
        name=p.parent.name
        if name in all_pdbs:raise ValueError('Ambiguous prediction '+name)
        all_pdbs[name]=p
    cache={}
    def get(name):
        if name not in cache:cache[name]=coordinates(read(all_pdbs[name]))
        return cache[name]
    parents={}
    for p in sorted(source.glob('cycle*/design/T*_n*/prepared.pdb')):
        text=read(p);match=re.search(r'AtomGroup (\S+)_model_0',text.splitlines()[0])
        if not match:raise ValueError('Missing parent provenance '+str(p))
        cycle=int(p.parents[2].name[5:]);t,n=map(int,re.fullmatch(r'T(\d+)_n(\d+)',p.parent.name).groups())
        name=match[1];c=coordinates(text)[0]
        if not np.array_equal(c,get(name)[0]):raise ValueError('Prepared coordinates differ from named parent')
        parents[cycle,t,n]=name
    groups=defaultdict(list);rows=[];mismatches=[]
    pattern=re.compile(r'c(\d+)_t(\d+)_n(\d+)_s(\d+)')
    for name,path in sorted(all_pdbs.items()):
        m=pattern.fullmatch(name)
        if not m:continue
        cycle,t,n,s=map(int,m.groups());parent=parents[cycle,t,n]
        pred=get(name); ref=get(parent)
        ca,lig=consistency(pred,ref)
        conf=json.loads(read(path.parent/f'confidence_{name}_model_0.json'))
        aff=path.parent/f'affinity_{name}.json'
        pbind=json.loads(read(aff)).get('affinity_probability_binary') if aff.exists() else None
        if pbind is not None and (not np.isfinite(pbind) or not 0<=pbind<=1):raise ValueError('Invalid affinity')
        if pred[3] is None or not 0<=pred[3]<=100:raise ValueError('Invalid ligand pLDDT')
        yaml=path.parents[4]/'yaml'/f'{name}.yaml'
        text=read(yaml);seq=re.search(r'\bsequence:\s*([A-Z]+)',text)[1]
        if seq!=pred[4]:raise ValueError('Sequence mismatch '+name)
        if not re.search(r'msa:\s*empty',text):raise ValueError('Unexpected MSA policy '+name)
        passed=ca<2.5 and (cycle<3 or lig<2.5)
        rec=recorded.get(name)
        if bool(rec)!=passed:mismatches.append(dict(name=name,csv=bool(rec),recomputed=passed,ca=ca,lig=lig))
        score=pred[3]/100+pbind if pbind is not None else None
        if rec and score is not None and abs(score-float(rec['score']))>0.000051:raise ValueError('Combined score disagrees '+name)
        if rec and (abs(ca-float(rec['ca_rmsd']))>.00051 or abs(lig-float(rec['ligand_rmsd']))>.00051):
            raise ValueError('RMSD disagrees '+name)
        row=dict(name=name,cycle=cycle,trajectory=t,parent_node=n,sample=s,parent=parent,
            ligand_plddt=pred[3],pbind=pbind,score=score,ca_rmsd=ca,ligand_rmsd=lig,
            geometry_passed=passed,recorded_passing=bool(rec),advanced=parents.get((cycle+1,t,0))==name,
            final_filter_passed=ca<1.5 and lig<1.5 and pred[3]>90 and pbind is not None and pbind>.8,
            sequence=seq,pdb=str(path.relative_to(source)))
        groups[cycle,t].append(row);rows.append(row)
    if len(rows)!=config['expected_folds']:raise ValueError('Unexpected fold count')
    if any(len(rs)!=64 or sorted(r['sample'] for r in rs)!=list(range(64)) for rs in groups.values()):raise ValueError('Not complete 64-proposal batches')
    if mismatches:raise ValueError('Eligibility audit failed: '+str(mismatches[:10]))
    stats=[];seeds={};prior={};cycle_best={}
    for t in range(6):
        name=parents[1,t,0];p=all_pdbs[name]; aff=json.loads(read(p.parent/f'affinity_{name}.json'))
        seeds[t]=dict(name=name,score=get(name)[3]/100+aff['affinity_probability_binary'],ligand_plddt=get(name)[3],pbind=aff['affinity_probability_binary']);prior[t]=seeds[t]['score']
    for (cycle,t),rs in sorted(groups.items()):
        rs.sort(key=lambda r:r['sample'])
        eligible=[r for r in rs if r['geometry_passed'] and r['score'] is not None]
        valid=[r['score'] for r in rs if r['score'] is not None]
        scores=[r['score'] for r in eligible];best=max(eligible,key=lambda r:r['score'])
        advanced=next((r for r in rs if r['advanced']),None)
        cycle_best[cycle,t]=best
        if advanced and advanced['name']!=best['name'] and advanced['score']!=best['score']:
            raise ValueError('Actual next parent is not the best eligible score: '+str((cycle,t)))
        q=np.quantile(scores,[.1,.25,.5,.75,.9,.95])
        row=dict(cycle=cycle,trajectory=t,folds=len(rs),scored=len(valid),passing=len(eligible),missing_affinity=sum(r['score'] is None for r in rs),
            prior_best=prior[t],best_score=best['score'],best_name=best['name'],improvement=best['score']-prior[t],
            best_ligand_plddt=best['ligand_plddt'],best_pbind=best['pbind'],
            q10=q[0],q25=q[1],median=q[2],q75=q[3],q90=q[4],q95=q[5],
            all_q10=float(np.quantile(valid,.1)),all_median=float(np.median(valid)),all_q90=float(np.quantile(valid,.9)),
            gap_to_median=best['score']-q[2],gap_to_second=best['score']-sorted(scores,reverse=True)[1] if len(scores)>1 else None,
            within_001=sum(best['score']-s<=.01 for s in scores),improve_001=sum(s>prior[t]+.01 for s in scores),
            final_filter_count=sum(r['final_filter_passed'] for r in rs),
            advanced_name=advanced['name'] if advanced else '',advanced_score=advanced['score'] if advanced else None,
            advanced_rank_all=1+sum(s>advanced['score']+1e-10 for s in valid) if advanced else None,
            advanced_percentile_all=100*sum(s<=advanced['score']+1e-10 for s in valid)/len(valid) if advanced else None)
        prior[t]=max(prior[t],best['score']);row['best_so_far']=prior[t];stats.append(row)
    # Fixed observed parents: neither hypothetical policy regenerates descendants.
    rng=np.random.default_rng(config['random_seed']);sim=[]
    for st in stats:
        cycle,t=st['cycle'],st['trajectory'];rs=groups[cycle,t]
        if st['missing_affinity']:continue
        values=np.array([r['score'] if r['geometry_passed'] else -np.inf for r in rs])
        orders=np.array([rng.permutation(64) for _ in range(config['permutations_per_cycle'])])
        maxima=np.maximum.accumulate(values[orders],axis=1)
        for delta in config['thresholds']:
            sizes=np.full(len(orders),64)
            for size in (32,16):sizes[maxima[:,size-1]>st['prior_best']+delta]=size
            chosen=maxima[np.arange(len(orders)),sizes-1];loss=st['best_score']-chosen
            prefix=64
            for size in (16,32):
                if np.max(values[:size])>st['prior_best']+delta:prefix=size;break
            sim.append(dict(cycle=cycle,trajectory=t,threshold=delta,replicates=len(orders),
                mean_proposals=float(np.mean(sizes)),p_stop16=float(np.mean(sizes==16)),p_stop32=float(np.mean(sizes==32)),
                p_exact_best=float(np.mean(loss<1e-10)),p_within_001=float(np.mean(loss<=.01)),
                mean_score_loss=float(np.mean(loss[np.isfinite(loss)])),p_no_passing=float(np.mean(~np.isfinite(chosen))),
                p_loss_over_001=float(np.mean(loss>.01)),prefix_proposals=prefix,prefix_score_loss=float(st['best_score']-np.max(values[:prefix]))))
    trajectory_summary=[];patience=[]
    for t in range(6):
        ts=[s for s in stats if s['trajectory']==t];best=max(ts,key=lambda s:s['best_score'])
        trajectory_summary.append(dict(trajectory=t,origin=next(r['origin'] for r in recorded.values() if int(r['trajectory'])==t),
            seed_score=seeds[t]['score'],seed_ligand_plddt=seeds[t]['ligand_plddt'],seed_pbind=seeds[t]['pbind'],last_cycle=max(s['cycle'] for s in ts),peak_cycle=best['cycle'],peak=best['best_score'],
            ligand_plddt=best['best_ligand_plddt'],pbind=best['best_pbind'],
            median_winner_minus_median=float(np.median([s['gap_to_median'] for s in ts])),
            median_near_winners=float(np.median([s['within_001'] for s in ts])),
            significant_cycles=[s['cycle'] for s in ts if s['improvement']>.01],
            small_improving_cycles=[s['cycle'] for s in ts if .0001<s['improvement']<=.01]))
        for delta in config['thresholds']:
            held=seeds[t]['score'];stale=0;stop=ts[-1]['cycle'];peak=held
            for st in ts:
                score=st['best_score'];stale=0 if score>held+delta else stale+1
                held=max(held,score);peak=max(peak,score)
                if stale>=4:stop=st['cycle'];break
            patience.append(dict(trajectory=t,threshold=delta,stop_cycle=stop,retained_peak=peak,
                full_peak=best['best_score'],missed_score=max(0,best['best_score']-peak),
                conditional_on='observed parent path; cycle5 missing affinities excluded from score maxima'))
    table(output/'candidates.csv',rows);table(output/'cycles.csv',stats);table(output/'trajectories.csv',trajectory_summary)
    table(output/'adaptive_subsets.csv',sim);table(output/'patience4.csv',patience)
    aggregates=[]
    for delta in config['thresholds']:
        ss=[r for r in sim if r['threshold']==delta]
        aggregates.append(dict(threshold=delta,cycles=len(ss),mean_proposals=float(np.mean([r['mean_proposals'] for r in ss])),
            proposal_reduction=float(1-np.mean([r['mean_proposals'] for r in ss])/64),
            p_exact_best=float(np.mean([r['p_exact_best'] for r in ss])),p_loss_over_001=float(np.mean([r['p_loss_over_001'] for r in ss])),
            mean_score_loss=float(np.mean([r['mean_score_loss'] for r in ss])),
            prefix_mean_proposals=float(np.mean([r['prefix_proposals'] for r in ss])),
            prefix_exact_best=float(np.mean([r['prefix_score_loss']<1e-10 for r in ss]))))
    write_json(output/'summary.json',dict(trajectories=trajectory_summary,subsets=aggregates,seeds=seeds,
        advanced_count=sum(bool(r['advanced_name']) for r in stats),
        advanced_not_raw_top=sum(r['advanced_rank_all'] is not None and r['advanced_rank_all']>1 for r in stats)))
    # All inputs used are fingerprinted, without copying model weights or modifying raw data.
    (output/'generator.py').write_bytes(Path(__file__).read_bytes())
    write_json(output/'manifest.json',dict(source=str(source),configuration=config,source_files=fingerprints,
        historical_saved_config=historical_config,recorded_summary=summary,
        analysis_script_sha256=sha(Path(__file__).read_bytes()),
        studio_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        hardware='Apple M4 Max / 64 GB, CPU retrospective only; historical runtime not inferred',
        historical_checkpoint_fingerprint='not established from surviving campaign metadata',
        historical_msa='empty in audited input YAMLs',neural_inference=False))
    for relative,fingerprint in fingerprints.items():
        if sha((source/relative).read_bytes())!=fingerprint:raise ValueError('Source changed during audit '+relative)
    write_json(output/'audit.json',dict(status='passed',folds=len(rows),cycles=len(stats),
        trajectory_rows=len(recorded),missing_affinity=sum(r['score'] is None for r in rows),
        geometry_matches_recorded=True,parent_coordinate_matches=len(parents),
        candidate_sequences_match_yaml=True,source_files_verified=len(fingerprints),
        notes=['Saved num_starts=12 was overwritten on resume; original cycle00 has 100 starts.',
               'Missing affinity is never imputed; all six cycle05 groups excluded from subset simulation.']))
    plot(output,stats,sim)
    print(json.dumps(dict(audit=json.loads((output/'audit.json').read_text()),trajectories=trajectory_summary,subsets=aggregates),indent=2))


def plot(output,stats,sim):
    plt.rcParams.update({'font.family':'Arial','font.size':9,'axes.edgecolor':'black','text.color':'black',
        'axes.labelcolor':'black','xtick.color':'black','ytick.color':'black','xtick.direction':'in','ytick.direction':'in',
        'axes.grid':False,'svg.fonttype':'none','savefig.transparent':True})
    fig,axes=plt.subplots(2,3,figsize=(14,8),sharex=True,sharey=True)
    for t,ax in enumerate(axes.flat):
        rs=[r for r in stats if r['trajectory']==t];x=[r['cycle'] for r in rs]
        ax.fill_between(x,[r['all_q10'] for r in rs],[r['all_q90'] for r in rs],color='#cccccc',alpha=.45,label='All scored: 10–90%')
        ax.fill_between(x,[r['q10'] for r in rs],[r['q90'] for r in rs],color='#b6d6e8',alpha=.7,label='Passing candidates: 10–90%')
        ax.plot(x,[r['all_median'] for r in rs],color='#777777',ls=':',label='All scored median')
        ax.plot(x,[r['median'] for r in rs],color='#337ca0',label='Passing median')
        ax.plot(x,[r['best_score'] for r in rs],color='#b85c00',marker='.',label='Cycle winner')
        ax.plot(x,[r['best_so_far'] for r in rs],color='black',ls='--',label='Best so far')
        advanced=[r for r in rs if r['advanced_name']]
        ax.scatter([r['cycle'] for r in advanced],[r['advanced_score'] for r in advanced],s=22,
                   facecolors='none',edgecolors='black',label='Confirmed next parent',zorder=5)
        ax.axvspan(4.7,5.3,color='#dddddd',alpha=.6)
        ax.set_title(f'Trajectory {t} · {len(rs)} cycles');ax.set_xlabel('Optimisation cycle');ax.set_ylabel('Ligand pLDDT/100 + P(bind)')
        ax.spines[['top','right']].set_visible(False)
    handles,labels=axes[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',ncol=3,bbox_to_anchor=(.5,0))
    fig.suptitle('Fluorescein NISE: complete score distributions and actual advanced parents\n85 trajectory-cycles × 64 proposals; shaded cycle 5 has missing affinity values')
    fig.tight_layout(rect=(0,.10,1,.92));fig.savefig(output/'trajectory_distributions.svg',bbox_inches='tight');fig.savefig(output/'trajectory_distributions.png',dpi=170,bbox_inches='tight');plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(14,7),sharex=True,sharey=True)
    for t,ax in enumerate(axes.flat):
        rs=[r for r in stats if r['trajectory']==t];x=[r['cycle'] for r in rs]
        ax.plot(x,[r['best_ligand_plddt']/100 for r in rs],color='#337ca0',marker='.',label='Ligand pLDDT / 100')
        ax.plot(x,[r['best_pbind'] for r in rs],color='#8a428c',marker='.',label='P(bind)')
        ax.set_title(f'Trajectory {t}');ax.set_xlabel('Cycle');ax.set_ylabel('Cycle-winner score components')
        ax.spines[['top','right']].set_visible(False)
    h,l=axes[0,0].get_legend_handles_labels();fig.legend(h,l,loc='lower center',ncol=2)
    fig.suptitle('Both components of each geometry-passing cycle winner')
    fig.tight_layout(rect=(0,.06,1,.94));fig.savefig(output/'score_components.svg',bbox_inches='tight');fig.savefig(output/'score_components.png',dpi=170,bbox_inches='tight');plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(14,7),sharex=True,sharey=True)
    for t,ax in enumerate(axes.flat):
        rs=[r for r in stats if r['trajectory']==t];x=[r['cycle'] for r in rs]
        ax.bar(x,[r['improvement'] for r in rs],facecolor='#83b4c9',edgecolor='black',linewidth=.5)
        ax.axhline(.01,color='#b85c00',ls='--',label='+0.01');ax.axhline(0,color='black',linewidth=.5)
        ax.set_title(f'Trajectory {t}');ax.set_xlabel('Cycle');ax.set_ylabel('Cycle winner − previous best')
        ax.spines[['top','right']].set_visible(False)
    fig.suptitle('Cycle improvements relative to the best previous score (including starting seed)')
    fig.tight_layout(rect=(0,0,1,.94));fig.savefig(output/'cycle_improvements.svg');fig.savefig(output/'cycle_improvements.png',dpi=170);plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();cfg=json.loads(Path(__file__).with_name('config.json').read_text());analyse(a.source.resolve(),a.output.resolve(),cfg)
