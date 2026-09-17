#!/usr/bin/env python3
"""Retrospective overview figures for the completed Bgx desktop campaigns."""
from __future__ import annotations
import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import sys
import warnings

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.backends.backend_pdf import PdfPages

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'Validation/output/bgx_completed_overviews_v1'
RUNTIME = Path(os.environ.get('NANOHUNTER_ROOT', Path.home()/'.iproteinstudio'))
sys.path.insert(0, str(ROOT/'Validation/experiments/binder_helix_strength_all_engines_v7'))
import audit as reference_audit
sys.path.insert(0, str(ROOT/'Validation/experiments/helix_strength_full_analysis_v1'))
from campaign_timing import phase_span

ENGINES = ['boltz','intellifold','intellifold_full','protenix_v2','protenix_mini','protenix_constraint_v0_5','openfold3']
LABELS = ['Boltz-2','IntelliFold Flash','IntelliFold full','Protenix v2','Protenix Mini','Protenix Constraint','OpenFold3']
SCAFFOLDS = ['7xl0_vobarilizumab','7eow_caplacizumab','8coh_gefurulimab','8z8v_ozoralizumab_alb8','gontivimab','isecarosmab','sonelokimab','3eak_nbbcii10_fgla']
SCAFFOLD_LABELS = ['Vobarilizumab','Caplacizumab','Gefurulimab','Ozoralizumab ALB8','Gontivimab','Isecarosmab','Sonelokimab','NbBCII10-FGLA']
COLORS = ['#657386','#087F83']
SS_COLORS = ['#476DA3','#28A59D','#CDD4DD']
SCAFFOLD_COLORS = ['#476DA3','#087F83','#986A9D','#C27E37','#4B8B56','#AD5360','#68728B','#927A50']


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''): h.update(block)
    return h.hexdigest()


def write_json(path,data):
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')


def write_csv(path,rows):
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def trajectory_means(rows):
    grouped=defaultdict(list)
    for row in rows: grouped[(row['campaign'],row['run'])].append(row)
    result=[]
    for (campaign,run),cycles in grouped.items():
        if sorted(r['cycle'] for r in cycles)!=[1,2,3,4,5]:
            raise ValueError('Expected exactly cycles 01–05 for '+campaign)
        first=cycles[0]
        entry={k:first[k] for k in ['campaign','kind','engine','condition','run','length']}
        for metric in ['plddt','iptm','helix','sheet','coil']:
            values=[r[metric] for r in cycles]
            entry['mean_'+metric]=None if values[0] is None else statistics.mean(values)
        result.append(entry)
    return result


def pooled_seconds(timings):
    return sum(t['recorded_span_seconds'] for t in timings)/sum(t['optimized_designs'] for t in timings)


def ci(values):
    a=np.asarray(values,dtype=float)
    rng=np.random.default_rng(907026)
    draws=a[rng.integers(0,len(a),size=(10000,len(a)))].mean(axis=1)
    return float(a.mean()),*np.quantile(draws,[.025,.975]).tolist()


def extract():
    manifest=json.loads((HERE/'manifest.json').read_text())
    rows=[];timings=[];sources={};configs=[]
    def record(path):
        sources[str(path)]=sha(path)
    record(HERE/'manifest.json')
    for index,item in enumerate(manifest['campaigns']):
        campaign=RUNTIME/'projects/untitled_design'/item['name']
        meta_path=campaign/'studio_run.json';meta=json.loads(meta_path.read_text());record(meta_path)
        assert meta['state']=='completed',campaign
        req=meta['request']; n=meta['requestedTrajectories']; cycles=meta['optimizationCycles']
        assert cycles==5 and n==item['trajectories']
        summary=campaign/'summary_all_runs.csv';record(summary)
        data=list(csv.DictReader(summary.open()))
        assert len(data)==n*6 and {(int(r['run']),int(r['cycle'])) for r in data}=={(r,c) for r in range(1,n+1) for c in range(6)},campaign
        target=req['targetSequence']
        args=meta['arguments'];snapshot=Path(meta['pipelineSnapshot'])
        # Fingerprint the actual frozen launch code and all captured campaign settings.
        record(snapshot/'nanohunter_run.sh')
        for path in sorted((snapshot/'scripts').rglob('*.py')):record(path)
        template=Path(args[args.index('--template-yaml')+1]);record(template)
        msa=campaign/'msa_cache/target_B.a3m'; assert msa.is_file(),msa;record(msa)
        for file in ['campaign_config.txt','throughput_profile.json','predictor_calibration.json']:
            if (campaign/file).is_file():record(campaign/file)
        for path in sorted(campaign.glob('msa_cache/*.a3m')):record(path)
        configs.append({'campaign':item['name'],'arguments':args,'request':req,'snapshot_runner_sha256':sha(snapshot/'nanohunter_run.sh'),'target_msa_sha256':sha(msa)})
        timers=[]
        for run in range(1,n+1):
            path=campaign/f'run_{run:03d}/timing_run.csv';record(path)
            timer=list(csv.DictReader(path.open()));assert len(timer)==1;timers+=timer
        span=phase_span(timers)
        timings.append({'campaign':item['name'],'kind':item['kind'],'engine':item['engine'],'condition':item['condition'],'trajectories':n,'optimized_designs':n*5,'recorded_span_seconds':span,'seconds_per_design':span/(n*5)})
        for raw in data:
            run,cycle=int(raw['run']),int(raw['cycle'])
            if cycle==0:continue
            normalized=campaign/f'run_{run:03d}/cycle_{cycle:02d}/pred_min/model_0.cif'
            path=Path(raw['structure_path']); assert sha(normalized)==sha(path),(normalized,path)
            record(normalized)
            confidence=normalized.with_name('confidence.json');record(confidence)
            score=float(json.loads(confidence.read_text())['iptm'])
            assert np.isfinite(score) and 0<=score<=1 and abs(score-float(raw['iptm']))<1e-6
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',UserWarning)
                binder=reference_audit._chain_sequence_and_sse(normalized,'A',raw['binder_sequence'],assign_sse=item['kind']=='minibinder')
                reference_audit._chain_sequence_and_sse(normalized,'B',target)
            ca=np.asarray(binder['confidence']); assert np.isfinite(ca).all() and np.min(ca)>=0 and np.max(ca)<=100
            rows.append({'campaign':item['name'],'kind':item['kind'],'engine':item['engine'],'condition':item['condition'],'run':run,'cycle':cycle,'length':len(raw['binder_sequence']),'plddt':float(ca.mean()),'iptm':score,'helix':binder.get('helix'),'sheet':binder.get('sheet'),'coil':binder.get('coil'),'structure':str(normalized)})
        print(f"Audited {index+1}/70: {item['name']}",flush=True)
    assert len(rows)==5250
    trajectories=trajectory_means(rows);assert len(trajectories)==1050
    write_csv(OUT/'structures.csv',rows);write_csv(OUT/'trajectories.csv',trajectories);write_csv(OUT/'timing.csv',timings)
    record(Path(reference_audit.__file__))
    record(ROOT/'Validation/experiments/helix_strength_full_analysis_v1/campaign_timing.py')
    record(Path(__file__))
    write_json(OUT/'source_sha256.json',sources)
    write_json(OUT/'campaign_provenance.json',configs)
    write_json(OUT/'data.json',{'trajectories':trajectories,'timings':timings})
    write_json(OUT/'integrity.json',{'created_at':datetime.now(timezone.utc).isoformat(),'campaigns':70,'optimized_structures_audited':len(rows),'trajectories':len(trajectories),'source_files_hashed':len(sources),'coordinate_finite_sequence_and_chain_checks':True,'summary_cardinality':True,'normalized_native_bytes_match':True,'cycle00_excluded':True,'biotite_version':__import__('biotite').__version__,'numpy_version':np.__version__,'matplotlib_version':matplotlib.__version__})
    return trajectories,timings


def style():
    plt.rcParams.update({'font.family':'Arial','font.size':10,'axes.titlesize':11,'axes.titleweight':'bold','axes.labelsize':10,'axes.labelcolor':'black','text.color':'black','axes.edgecolor':'black','xtick.color':'black','ytick.color':'black','xtick.direction':'in','ytick.direction':'in','axes.grid':False,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none','pdf.fonttype':42,'savefig.facecolor':'white'})


def dotplot(axis,values,y,color):
    jitter=np.linspace(-.19,.19,len(values))
    axis.scatter(values,y+jitter,s=13,color=color,alpha=.40,zorder=2)
    mean,low,high=ci(values)
    axis.plot([low,high],[y,y],color='black',lw=1.25,zorder=3)
    axis.scatter([mean],[y],marker='D',s=25,facecolor='white',edgecolor='black',zorder=4)


def plots(trajectories,timing):
    style(); summaries=[]
    for kind,conditions in [('minibinder',['0','1']),('nanobody',SCAFFOLDS)]:
        for engine in ENGINES:
            for condition in conditions:
                group=[t for t in trajectories if t['kind']==kind and t['engine']==engine and t['condition']==condition]
                entry={'kind':kind,'engine':engine,'condition':condition,'n_trajectories':len(group),
                       'mean_binder_length_aa':statistics.mean(t['length'] for t in group)}
                for metric in ['plddt','iptm']+(['helix','sheet','coil'] if kind=='minibinder' else []):
                    mean,low,high=ci([t['mean_'+metric] for t in group]);entry.update({metric:mean,metric+'_ci_low':low,metric+'_ci_high':high})
                summaries.append(entry)
    write_json(OUT/'summary.json',summaries)
    lengths={(s['engine'],s['condition']):s['mean_binder_length_aa']
             for s in summaries if s['kind']=='minibinder'}
    write_csv(OUT/'minibinder_campaign_lengths.csv',[
        {k:s[k] for k in ['engine','condition','n_trajectories','mean_binder_length_aa']}
        for s in summaries if s['kind']=='minibinder'])
    def values(kind,engine,condition,metric):
        return [t['mean_'+metric] for t in trajectories if (t['kind'],t['engine'],t['condition'])==(kind,engine,condition)]
    def times(kind,engine,condition=None):
        return pooled_seconds([t for t in timing if t['kind']==kind and t['engine']==engine and (condition is None or t['condition']==condition)])
    def save(fig,name,pdf):
        fig.savefig(OUT/(name+'.svg'),transparent=True)
        fig.savefig(OUT/(name+'.png'),dpi=180)
        fig.savefig(OUT/(name+'.pdf'))
        pdf.savefig(fig);plt.close(fig)
    with PdfPages(OUT/'OVERVIEWS.pdf') as pdf:
        fig=plt.figure(figsize=(17,12));grid=fig.add_gridspec(1,4,left=.17,right=.97,bottom=.17,top=.81,width_ratios=[1.45,1,1,1],wspace=.25)
        ss,conf,iptm,time=[fig.add_subplot(grid[0,i]) for i in range(4)]
        fig.text(.04,.978,'01 / MINIBINDER OVERVIEW',fontsize=10,fontweight='bold',va='top')
        fig.text(.04,.952,'Completed minibinder designs across seven engines',fontsize=20,fontweight='bold',va='top')
        fig.text(.04,.90,'α-Cobratoxin  •  700 trajectories  •  50 per engine and condition  •  five optimization cycles',fontsize=11)
        fig.text(.55,.86,'Helix kill: 0 = 65–150 aa; 1 = 65–120 aa',fontsize=10)
        ticks=[];labels=[]
        for e,engine in enumerate(ENGINES):
            center=e*3+.5
            ss.text(-.10,center,LABELS[e],transform=ss.get_yaxis_transform(),ha='right',va='center',fontweight='bold',fontsize=10)
            for c,condition in enumerate(['0','1']):
                y=e*3+c;start=0
                for metric,color in zip(['helix','sheet','coil'],SS_COLORS):
                    mean=np.mean(values('minibinder',engine,condition,metric))*100
                    ss.barh(y,mean,left=start,height=.72,color=color,edgecolor='black',linewidth=.55)
                    if mean>=10:ss.text(start+mean/2,y,f'{mean:.0f}',ha='center',va='center',fontsize=9)
                    start+=mean
                dotplot(conf,values('minibinder',engine,condition,'plddt'),y,COLORS[c])
                dotplot(iptm,values('minibinder',engine,condition,'iptm'),y,COLORS[c])
                seconds=times('minibinder',engine,condition)
                time.barh(y,seconds,height=.72,color=COLORS[c],edgecolor='black',linewidth=.55)
                length=lengths[engine,condition]
                time.annotate(f'{seconds:.1f} s\n{length:.1f} aa',(seconds,y),xytext=(4,0),textcoords='offset points',va='center',fontsize=8.5,linespacing=1.1)
                ticks.append(y);labels.append(condition)
        for ax in [ss,conf,iptm,time]:ax.set_ylim(20,-1)
        for ax in [ss,conf]:ax.set_xlim(0,100);ax.set_xticks([0,25,50,75,100])
        iptm.set_xlim(0,1);iptm.set_xticks([0,.25,.5,.75,1]);iptm.axvline(.7,color='#A1443A',ls='--',lw=1)
        ss.set_yticks(ticks,labels)
        for ax in [conf,iptm,time]:ax.set_yticks([])
        time.set_xlim(0,max(times('minibinder',e,c) for e in ENGINES for c in ['0','1'])*1.36)
        for ax,title,xlabel in [(ss,'Secondary structure','Binder residues (%)'),(conf,'Binder confidence','Mean binder Cα pLDDT'),(iptm,'Interface confidence','Mean iPTM'),(time,'Time per design','Seconds / optimized design')]:
            ax.set_title(title,loc='left',pad=16);ax.set_xlabel(xlabel)
        fig.legend(handles=[Patch(facecolor=c,edgecolor='black',label=l) for c,l in zip(SS_COLORS,['Helix','Sheet','Coil'])],loc='upper left',bbox_to_anchor=(.17,.887),ncol=3,frameon=False)
        fig.text(.04,.025,'Bars and diamonds: means of 50 trajectory means over cycles 01–05; cycle 00 excluded. Dots: trajectories; black intervals: 95% bootstrap CIs.\n'
                 'Secondary structure: Biotite P-SEA on binder coordinates. Dashed iPTM line: saved 0.7 threshold; scores are not experimental binding evidence.\n'
                 'Time: recorded campaign span / 250 optimized outputs, including initialization and MPNN; overlapping timers counted once, no timing CI.\n'
                 'Timing labels: seconds per design and actual mean binder length (aa), averaged over the 50 trajectories in each campaign.\n'
                 'Historical Apple M4 Max / 64 GB runs; queueing and setup before the first trajectory timer excluded; pauses within the span remain included.\n'
                 'Length ranges and seeds differ between helix-kill conditions. Native engine settings differ: descriptive comparisons, not controlled speed or helix-effect tests.',fontsize=9,va='bottom',linespacing=1.5)
        save(fig,'01_minibinders_overview',pdf)

        fig=plt.figure(figsize=(17,21));bottom=.105;top=.89
        grid=fig.add_gridspec(1,3,left=.31,right=.96,bottom=bottom,top=top,width_ratios=[1,1,.9],wspace=.30)
        conf,iptm,time=[fig.add_subplot(grid[0,i]) for i in range(3)]
        fig.text(.04,.982,'02 / NANOBODY OVERVIEW',fontsize=10,fontweight='bold',va='top')
        fig.text(.04,.963,'Eight nanobody scaffolds across seven engines',fontsize=20,fontweight='bold',va='top')
        fig.text(.04,.937,'α-Cobratoxin  •  AbMPNN redesign of CDR1–3  •  350 trajectories  •  five optimization cycles',fontsize=11)
        fig.text(.31,.919,'Scaffold rows; timing pooled across all eight scaffolds per engine',fontsize=10)
        ticks=[];ticklabels=[]
        for e,engine in enumerate(ENGINES):
            center=e*10+3.5
            fig.text(.035,bottom+(top-bottom)*(68-center)/69,LABELS[e],ha='left',va='center',fontweight='bold',fontsize=11)
            for c,condition in enumerate(SCAFFOLDS):
                y=e*10+c;n=len(values('nanobody',engine,condition,'plddt'))
                dotplot(conf,values('nanobody',engine,condition,'plddt'),y,SCAFFOLD_COLORS[c])
                dotplot(iptm,values('nanobody',engine,condition,'iptm'),y,SCAFFOLD_COLORS[c])
                ticks.append(y);ticklabels.append(f'{SCAFFOLD_LABELS[c]}  (n={n})')
            seconds=times('nanobody',engine)
            time.barh(center,seconds,height=2.0,color='#657386',edgecolor='black',linewidth=.65)
            time.annotate(f'{seconds:.1f}',(seconds,center),xytext=(5,0),textcoords='offset points',va='center',fontsize=10)
        for ax in [conf,iptm,time]:ax.set_ylim(68,-1)
        conf.set_xlim(0,100);conf.set_xticks([0,25,50,75,100]);conf.set_yticks(ticks,ticklabels,fontsize=9)
        iptm.set_xlim(0,1);iptm.set_xticks([0,.25,.5,.75,1]);iptm.axvline(.7,color='#A1443A',ls='--',lw=1)
        for ax in [iptm,time]:ax.set_yticks([])
        time.set_xlim(0,max(times('nanobody',e) for e in ENGINES)*1.27)
        for ax,title,xlabel in [(conf,'Binder confidence','Mean binder Cα pLDDT'),(iptm,'Interface confidence','Mean iPTM'),(time,'Time per design','Seconds / optimized design')]:
            ax.set_title(title,loc='left',pad=16);ax.set_xlabel(xlabel)
        fig.text(.04,.023,'Diamonds: means of trajectory means over cycles 01–05; cycle 00 excluded. Dots: trajectories; black intervals: 95% bootstrap CIs.\n'
                 'n=7 per engine for Vobarilizumab and Caplacizumab; n=6 for each other scaffold. Confidence covers the full binder chain, including framework.\n'
                 'Time: sum of the eight scaffold campaign spans / 250 optimized outputs per engine (50 trajectories × 5 cycles); one pooled bar per engine.\n'
                 'Includes initialization and MPNN; overlapping timers counted once. Weights follow completed output counts; inter-campaign queue waits excluded.\n'
                 'Historical Apple M4 Max / 64 GB costs; no timing CI. Native settings and scaffold lengths differ, so this is not a controlled speed comparison.\n'
                 'Dashed iPTM line: saved 0.7 threshold. Predictor scores are not experimental binding evidence. No secondary-structure endpoint is shown.',fontsize=9,va='bottom',linespacing=1.6)
        save(fig,'02_nanobodies_overview',pdf)
    pooled=[{'engine':e,'seconds_per_design':times('nanobody',e),'optimized_designs':250,'scaffolds':8} for e in ENGINES]
    write_csv(OUT/'nanobody_pooled_timing.csv',pooled)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plot-only',action='store_true');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if args.plot_only:
        data=json.loads((OUT/'data.json').read_text());trajectories,timing=data['trajectories'],data['timings']
    else:trajectories,timing=extract()
    plots(trajectories,timing)
    (OUT/'GALLERY.html').write_text('<!doctype html><meta charset="utf-8"><title>Bgx completed designs</title><style>body{font:16px Arial;margin:32px}img{max-width:100%;height:auto}a{color:#087f83}</style><h1>Completed Bgx designs</h1>'+''.join(f'<h2>{label}</h2><p><a href="{name}.svg">SVG</a> · <a href="{name}.pdf">PDF</a> · <a href="{name}.png">PNG</a></p><img src="{name}.svg" alt="{label}">' for name,label in [('01_minibinders_overview','Minibinders'),('02_nanobodies_overview','Nanobodies')]))
    write_json(OUT/'artifact_sha256.json',{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='artifact_sha256.json'})
    print('Figures written to',OUT,flush=True)

if __name__=='__main__':main()
