#!/usr/bin/env python3
"""Recheck frozen v3 results and export a complete monomer control figure set."""
import base64
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import statistics
import sys
import warnings
import zipfile
import campaign_timing

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / 'Validation/output/helix_strength_all_engines_v3'
OUT = STUDY / 'analysis/full_analysis_v1'
ENGINES = ['boltz','intellifold_flash','intellifold_full','protenix_v2','protenix_mini','protenix_constraint','openfold3']
LABELS = ['Boltz-2','IntelliFold Flash','IntelliFold full','Protenix v2','Protenix Mini','Protenix Constraint','OpenFold3']
SUFFIX = ['0','0p5','1']
STRENGTH = ['0','0.5','1']
METRICS = ['helix','sheet','coil','plddt']
SC = ['#476DA3','#28A59D','#CDD4DD']
COLORS = ['#657386','#D69A36','#087F83']
rng = random.Random(906026)
BOOT = np.array([rng.choices(range(10),k=10) for _ in range(10000)])
CACHE = {}


def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def check(ok, message):
    if not ok: raise RuntimeError(message)
def write_json(p, value): p.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def bounds(x):
    x=np.asarray(x,dtype=float)
    check(x.shape==(10,), 'Bootstrap unit must be ten trajectories')
    draws=np.sort(x[BOOT].mean(axis=1))
    return [float(draws[249]),float(draws[9749])]
def ci(x): return [float(np.mean(x)),*bounds(x)]


def load():
    manifest=read(STUDY/'manifest.json');digest=sha(STUDY/'manifest.json')
    stage=read(STUDY/'stage_receipt.json')
    check(sha(STUDY/'stage_receipt.json')==manifest['stage_receipt_sha256'],'Stage identity changed')
    experiment=ROOT/'Validation/experiments/helix_strength_all_engines_v3'
    for name,checksum in manifest['experiment_code'].items():
        check(sha(experiment/name)==checksum,'Frozen experiment changed: '+name)
    for name,record in stage['files'].items():
        check(sha(STUDY/'source'/name)==record['after_sha256'],'Frozen source changed: '+name)
    sys.path.insert(0,str(STUDY/'source/scripts'))
    from initialization_assessment import assess_structure
    from validate_prediction_geometry import inspect_geometry
    rows=[];trajectories=[];audit_checksums={};count=0;fallback=0
    for engine in ENGINES:
        for suffix in SUFFIX:
            arm=engine+'_h'+suffix
            for phase in ['pilot','remaining']:
                path=STUDY/'audits'/phase/(arm+'.json');a=read(path)
                check(a['manifest_sha256']==digest and a['operational_passed'],'Unfinished or wrong audit '+arm)
                audit_checksums[str(path.relative_to(STUDY))]=sha(path)
                for relative,checksum in a['raw_sha256'].items():
                    p=STUDY/relative;st=p.stat();key=(str(p.resolve()),st.st_size,st.st_mtime_ns)
                    if key not in CACHE:
                        CACHE[key]=sha(p)
                        check(p.stat().st_mtime_ns==st.st_mtime_ns,'File changed during verification')
                    check(CACHE[key]==checksum,'Raw output changed: '+relative);count+=1
                for row in a['structures']:
                    p=STUDY/row['structure']
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore',UserWarning)
                        actual=assess_structure(p,row['sequence'],dict(max_attempts=1,min_uncertain_coil_length=16,confidence_threshold=50))
                    check(actual['psea']==row['psea'],'P-SEA replay changed')
                    check(np.allclose(actual['confidence'],row['per_residue_confidence'],rtol=0,atol=1e-9),'Confidence replay changed')
                    check(all(abs(actual['fractions'][m]-row[m])<1e-12 for m in METRICS[:3]),'Fraction replay changed')
                    g=inspect_geometry(p)
                    check(not g['errors'] and g['violations']==row['geometry_violations'],'Geometry replay changed')
                    check(len(row['sequence'])==len(row['psea'])==len(row['per_residue_confidence'])==90,'Length differs')
                    check(abs(sum(row[m] for m in METRICS[:3])-1)<1e-9,'Fractions do not sum to one')
                rows.extend(a['structures']);trajectories.extend(a['trajectories'])
                fallback+=len(a['svd_fallback_log_lines'])
            print('Verified',arm,flush=True)
    check(len(rows)==1260 and len(trajectories)==210,'Study cardinality differs')
    check(len({(r['arm'],r['trajectory'],r['cycle']) for r in rows})==1260,'Duplicate structure identities')
    for t in trajectories:
        rr=sorted([r for r in rows if r['arm']==t['arm'] and r['trajectory']==t['trajectory']],key=lambda r:r['cycle'])
        check(t['outcome']=='completed' and [r['cycle'] for r in rr]==list(range(6)),'Trajectory incomplete')
        for m in METRICS:
            check(abs(np.mean([r[m] for r in rr[1:]])-t['mean_'+m])<1e-9,'Trajectory mean differs')
    integrity={'manifest_sha256':digest,'audit_sha256':audit_checksums,'raw_path_checks':count,'unique_file_checks':len(CACHE),
               'reassessed_structures':len(rows),'completed_trajectories':len(trajectories),'optimization_cycles':1050,
               'svd_fallback_log_lines':fallback,'hardware':stage['hardware'],'analysis_script_sha256':sha(Path(__file__)),
               'verified_at':datetime.now(timezone.utc).isoformat(),'scope':'All v3 outputs; superseded v1/v2 excluded. Retrospective checks use frozen code and outputs, not the current live runtime.'}
    return rows,trajectories,integrity


def style():
    plt.rcParams.update({'font.family':'Arial','font.size':10,'axes.titlesize':11,'axes.titleweight':'bold',
        'axes.labelsize':10,'axes.labelcolor':'black','text.color':'black','axes.edgecolor':'black',
        'xtick.color':'black','ytick.color':'black','xtick.direction':'in','ytick.direction':'in',
        'axes.grid':False,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none',
        'pdf.fonttype':42,'savefig.facecolor':'white'})


def title(fig,number,headline,sub):
    fig.text(.04,.98,number,fontsize=10,fontweight='bold',va='top',color='black')
    fig.text(.04,.955,headline,fontsize=20,fontweight='bold',va='top')
    fig.text(.04,.902,sub,fontsize=10,va='top')


def footer(fig,text): fig.text(.04,.025,text,fontsize=9,va='bottom',linespacing=1.5)

def save(fig,name,pdf):
    fig.savefig(OUT/(name+'.svg'),transparent=True)
    fig.savefig(OUT/(name+'.png'),dpi=220)
    fig.savefig(OUT/(name+'.pdf'))
    pdf.savefig(fig)
    plt.close(fig)


def figures(rows,tt,timing):
    style()
    data={(e,s):sorted([t for t in tt if t['arm']==e+'_h'+s],key=lambda t:t['trajectory']) for e in ENGINES for s in SUFFIX}
    def vals(e,s,m,prefix='mean_'):return np.array([t[prefix+m] for t in data[e,s]])
    contrasts={}
    for e in ENGINES:
        for lower,upper in [('0','0p5'),('0','1'),('0p5','1')]:
            contrasts[e+':'+lower+'->'+upper]={m:{'mean_difference':ci(vals(e,upper,m)-vals(e,lower,m))[0],
                'bootstrap_95_ci':bounds(vals(e,upper,m)-vals(e,lower,m)),'n_pairs':10} for m in METRICS}
    write_json(OUT/'paired_contrasts.json',contrasts)
    with PdfPages(OUT/'FIGURES.pdf') as pdf:
        fig=plt.figure(figsize=(15,12))
        gs=fig.add_gridspec(1,3,left=.19,right=.97,bottom=.15,top=.82,width_ratios=[1.4,1,1],wspace=.25)
        left,right,time_ax=[fig.add_subplot(gs[0,k]) for k in range(3)]
        title(fig,'01 / COMPLETE BENCHMARK','Initialization control changes the resulting fold','90-aa monomers  •  seven engines  •  strengths 0, 0.5 and 1  •  all 210 trajectories completed')
        ticks=[];ticklabels=[]
        for ei,e in enumerate(ENGINES):
            center=ei*4+1
            left.text(-.10,center,LABELS[ei],transform=left.get_yaxis_transform(),ha='right',va='center',fontweight='bold',fontsize=10)
            for si,s in enumerate(SUFFIX):
                y=ei*4+si;means=[vals(e,s,m).mean()*100 for m in METRICS[:3]];start=0
                for value,color in zip(means,SC):
                    left.barh(y,value,left=start,height=.73,color=color,edgecolor='black',linewidth=.55)
                    if value>=10:left.text(start+value/2,y,f'{value:.0f}',ha='center',va='center',fontsize=9,color='black')
                    start+=value
                x=vals(e,s,'plddt');jitter=np.linspace(-.20,.20,10)
                right.scatter(x,y+jitter,s=14,color=COLORS[si],alpha=.45,zorder=2)
                mean,lo,hi=ci(x);right.plot([lo,hi],[y,y],color='black',lw=1.25,zorder=3)
                right.scatter([mean],[y],marker='D',s=25,facecolor='white',edgecolor='black',zorder=4)
                seconds=timing['arms'][e+'_h'+s]['seconds_per_design']
                time_ax.barh(y,seconds,height=.73,color=COLORS[si],edgecolor='black',linewidth=.55)
                time_ax.annotate(f'{seconds:.1f}',(seconds,y),xytext=(4,0),textcoords='offset points',va='center',fontsize=9)
                ticks.append(y);ticklabels.append(STRENGTH[si])
        for ax in [left,right]:ax.set_ylim(27,-1);ax.set_xlim(0,100);ax.set_xticks([0,25,50,75,100])
        time_ax.set_ylim(27,-1);time_ax.set_xlim(0,max(v['seconds_per_design'] for v in timing['arms'].values())*1.25)
        time_ax.set_yticks([]);time_ax.set_title('Time per design',loc='left',pad=16);time_ax.set_xlabel('Seconds / optimized design')
        left.set_yticks(ticks,ticklabels);right.set_yticks([])
        left.set_title('Secondary structure',loc='left',pad=16);right.set_title('Predicted confidence',loc='left',pad=16)
        left.set_xlabel('Residues (%)');right.set_xlabel('Mean Cα pLDDT (0–100)')
        fig.legend(handles=[Patch(facecolor=c,edgecolor='black',label=l) for c,l in zip(SC,['Helix','Sheet','Coil'])],loc='upper left',bbox_to_anchor=(.19,.873),ncol=3,frameon=False,columnspacing=1)
        footer(fig,'Bars and diamonds: mean of ten trajectory means over cycles 01–05; cycle 00 excluded. Numbers in bars are percentages.\nConfidence dots: individual trajectories; black intervals: 95% bootstrap CIs. Strength labels are at left.\nTime: summed recorded phase spans / 50 optimized outputs per condition (10 trajectories × 5 cycles), including initialization and MPNN.\nOverlapping timers counted once; one aggregate from pilot + remaining phases, no timing CI. Apple M4 Max, 64 GB.\nNative settings and confidence scales differ by engine; descriptive costs, not a controlled speed or accuracy ranking.')
        save(fig,'01_overview',pdf)

        fig,axes=plt.subplots(1,4,figsize=(13,7.3),sharey=True)
        fig.subplots_adjust(left=.18,right=.98,top=.77,bottom=.21,wspace=.28)
        title(fig,'02 / PAIRED EFFECTS','How much does each strength change the outcome?','Change relative to strength 0  •  matched trajectory seeds within each engine')
        for mi,(m,ax) in enumerate(zip(METRICS,axes)):
            scale=1 if m=='plddt' else 100
            ax.axvline(0,color='#8F959C',lw=.9,zorder=0)
            for ei,e in enumerate(ENGINES):
                for si,s in enumerate(['0p5','1']):
                    value=contrasts[e+':0->'+s][m];mean=value['mean_difference']*scale;lo,hi=np.array(value['bootstrap_95_ci'])*scale;y=ei+[-.13,.13][si]
                    ax.plot([lo,hi],[y,y],color=COLORS[si+1],lw=1.8)
                    ax.scatter([mean],[y],s=34,color=COLORS[si+1],edgecolor='black',linewidth=.5,zorder=3)
            ax.set_title({'helix':'Helix','sheet':'Sheet','coil':'Coil','plddt':'Confidence'}[m],loc='left',pad=14)
            ax.set_xlabel('Δ pLDDT' if m=='plddt' else 'Δ percentage points')
            ax.set_xlim((-40,15) if m=='plddt' else (-70,50));ax.set_ylim(6.6,-.6)
        axes[0].set_yticks(range(7),LABELS)
        fig.legend(handles=[Line2D([],[],marker='o',color=COLORS[i],label=f'Strength {STRENGTH[i]} vs 0') for i in [1,2]],loc='upper left',bbox_to_anchor=(.18,.87),ncol=2,frameon=False)
        footer(fig,'Points: mean paired differences in trajectory means, cycles 01–05. Lines: 95% paired bootstrap CIs; n=10 pairs.\n10,000 resamples, seed 906026. Intervals are exploratory and unadjusted for multiple comparisons.\nA reduction in helix can be accompanied by both more sheet and more coil; coil assignment does not establish disorder.')
        save(fig,'02_paired_effects',pdf)

        fig,axes=plt.subplots(7,3,figsize=(12,15),sharex=True)
        fig.subplots_adjust(left=.18,right=.96,top=.84,bottom=.08,hspace=.38,wspace=.23)
        title(fig,'03 / OPTIMIZATION DYNAMICS','The initialization signal persists through cycling','Each trace follows the same ten trajectories  •  initialization-only sequence bias  •  ordinary MPNN thereafter')
        for ei,e in enumerate(ENGINES):
            for mi,m in enumerate(['helix','sheet','plddt']):
                ax=axes[ei,mi];scale=1 if m=='plddt' else 100
                ax.axvspan(-.2,.35,facecolor='#E9EDF1',zorder=0)
                for si,s in enumerate(SUFFIX):
                    values=[]
                    for cy in range(6):
                        x=sorted([r for r in rows if r['arm']==e+'_h'+s and r['cycle']==cy],key=lambda r:r['trajectory'])
                        values.append(ci([r[m]*scale for r in x]))
                    v=np.array(values);ax.plot(range(6),v[:,0],color=COLORS[si],marker='o',ms=3,lw=1.6)
                    ax.fill_between(range(6),v[:,1],v[:,2],color=COLORS[si],alpha=.09,lw=0)
                ax.set_ylim(0,100);ax.set_yticks([0,50,100]);ax.set_xlim(-.2,5.2);ax.set_xticks(range(6))
                if ei==0:ax.set_title({'helix':'Helix (%)','sheet':'Sheet (%)','plddt':'Cα pLDDT'}[m],loc='left',pad=12)
                if mi==0:ax.set_ylabel(LABELS[ei],rotation=0,ha='right',va='center',labelpad=18,fontweight='bold')
                if ei==6:ax.set_xlabel('Cycle (0 = initialization)')
        fig.legend(handles=[Line2D([],[],color=COLORS[i],marker='o',label=f'Strength {STRENGTH[i]}') for i in range(3)],loc='upper left',bbox_to_anchor=(.18,.875),ncol=3,frameon=False)
        footer(fig,'Means and pointwise 95% bootstrap CIs across n=10 trajectories per condition. Cycle00 is shaded and shown only as initialization.\nCycles are repeated observations, not independent replicates. Ribbon intervals are exploratory and unadjusted.')
        save(fig,'03_cycle_dynamics',pdf)

        fig,axes=plt.subplots(2,4,figsize=(13,8.5),sharex=True,sharey=True)
        fig.subplots_adjust(left=.07,right=.97,top=.80,bottom=.14,hspace=.40,wspace=.18)
        title(fig,'04 / FINAL-CYCLE OUTCOMES','What survives to cycle 05?','Each point is one completed trajectory  •  sheet content versus predicted confidence')
        for ei,e in enumerate(ENGINES):
            ax=axes.flat[ei]
            for si,s in enumerate(SUFFIX):
                x=vals(e,s,'sheet','final_')*100;y=vals(e,s,'plddt','final_')
                ax.scatter(x,y,s=29,color=COLORS[si],alpha=.65,edgecolor='black',linewidth=.35)
                ax.scatter([x.mean()],[y.mean()],s=90,color=COLORS[si],marker='D',edgecolor='black',linewidth=1.1)
            ax.set_title(LABELS[ei],loc='left');ax.set_xlim(-3,83);ax.set_ylim(0,103);ax.set_xticks([0,20,40,60,80]);ax.set_yticks([0,25,50,75,100])
            if ei//4==1:ax.set_xlabel('Sheet residues (%)')
            if ei%4==0:ax.set_ylabel('Cα pLDDT')
        axes.flat[-1].axis('off')
        axes.flat[-1].legend(handles=[Line2D([],[],linestyle='',marker='o',color=COLORS[i],label=f'Strength {STRENGTH[i]}') for i in range(3)]+[Line2D([],[],linestyle='',marker='D',markerfacecolor='white',markeredgecolor='black',label='Condition mean')],loc='center',frameon=False,labelspacing=1.4)
        footer(fig,'n=10 trajectories per strength per engine. This final-cycle endpoint is separate from the primary five-cycle mean.\nComparisons are descriptive within each engine; confidence is not a common calibrated measure of experimental folding.')
        save(fig,'04_final_outcomes',pdf)

        flagged=sorted({(r['arm'],r['trajectory']) for r in rows if r['geometry_violation_count']})
        fig,(left,right)=plt.subplots(1,2,figsize=(12,6.8),gridspec_kw={'width_ratios':[1.3,1]})
        fig.subplots_adjust(left=.26,right=.96,top=.77,bottom=.24,wspace=.28)
        title(fig,'05 / GEOMETRY DIAGNOSTICS','Recorded violations resolved before the final cycle','All 1,260 predicted structures rechecked  •  violations retained in the analysis  •  no geometric exclusions')
        matrix=np.array([[next(r['geometry_violation_count'] for r in rows if (r['arm'],r['trajectory'])==key and r['cycle']==cy) for cy in range(6)] for key in flagged])
        from matplotlib.colors import ListedColormap,BoundaryNorm
        cmap=ListedColormap(['#EFF2F5','#F7DDB9','#E8B875','#D88C3B','#AD6021'])
        left.imshow(matrix,cmap=cmap,norm=BoundaryNorm(np.arange(-.5,5.5),cmap.N),aspect='auto')
        for i in range(len(flagged)):
            for j in range(6):left.text(j,i,str(matrix[i,j]),ha='center',va='center',fontsize=13)
        left.set_xticks(range(6));left.set_xlabel('Cycle (0 = initialization)')
        labels=[]
        for arm,t in flagged:
            engine,s=arm.rsplit('_h',1);labels.append(f'{LABELS[ENGINES.index(engine)]} · {s.replace("p", ".")}\nTrajectory {t:02d}')
        left.set_yticks(range(len(flagged)),labels);left.set_title('Every trajectory with a violation',loc='left',pad=15)
        right.axis('off')
        right.text(.05,.87,'4 / 1,260',fontsize=28,fontweight='bold',transform=right.transAxes)
        right.text(.05,.74,'structures with ≥1 distance violation',fontsize=11,transform=right.transAxes)
        right.text(.05,.50,'0 / 210',fontsize=28,fontweight='bold',transform=right.transAxes)
        right.text(.05,.37,'final structures with a flagged violation',fontsize=11,transform=right.transAxes)
        footer(fig,'Cells count flagged atom-pair distances in the four affected trajectories; the other 206 trajectories had none.\nDiagnostics use C–N >2.2 Å and Cα–Cα >4.5 Å. Nine distance violations occurred in four structures; none persisted to cycle 05.\nThis is a limited geometry screen, not comprehensive stereochemical validation or proof that recovery is guaranteed.')
        save(fig,'05_geometry_recovery',pdf)
    return contrasts


def report(rows,tt,integrity,contrasts,timing):
    lines=['# Initialization-only helix control: complete seven-engine benchmark','',
           '**All 210 trajectories completed all five optimization cycles.** All 1,260 predicted structures (including 210 initializations) were reassessed from coordinates; 1,050 optimization cycles enter the primary endpoint. Previous v1/v2 runs are preserved but excluded from this analysis.','',
           '## Main findings','',
           '- Strength 1 reduced mean helicity in every engine. The paired exploratory 95% interval excludes zero in six of seven engines; OpenFold3 remains uncertain. Helicity reductions range from 11.9 to 41.2 percentage points.',
           '- The structural change persists into cycle 05 despite using ordinary MPNN after initialization. Some helix regrowth occurs, particularly with Protenix Mini; initialization controls the starting basin, not an exact final fold.',
           '- Increased sheet accompanies reduced helix in most conditions, but coil also increases. Strongest-control sheet gains have intervals above zero in IntelliFold Flash, IntelliFold full and Protenix Constraint; the other engines have wider intervals crossing zero.',
           '- Protenix Mini at strength 1 has a large confidence cost: mean pLDDT 83.4 → 57.3; paired change −26.0 [−30.1, −22.0]. At cycle 05 it remains 62.8 versus 88.0 for baseline. Here much of the helix reduction becomes coil (21.5% → 52.1% averaged over cycles).',
           '- Protenix Constraint has a substantial response already at 0.5: helix 41.4% → 17.0%, sheet 21.8% → 38.1%, mean confidence 86.0 → 85.3. Increasing to 1 gives little additional mean sheet gain (37.8%); the incremental contrasts remain uncertain.',
           '- IntelliFold full at 1 moves helix 54.4% → 22.2% and sheet 17.5% → 41.4%. Mean confidence changes87.6 → 84.9, while final confidence is 92.1 versus 91.1. Protenix v2 likewise retains high final confidence at 1 (93.6 versus 92.0). These are descriptive within-engine outcomes, not experimental validation.',
           '- OpenFold3 is non-monotonic in the sample means: 0.5 has less helix and more sheet than 1, with similar confidence to baseline. Wide paired intervals do not establish an optimal dose.',
           '- Four structures in four trajectories contain nine recorded distance violations. All affected trajectories completed and all 210 final structures had zero flagged violations. The formerly rejected Boltz baseline trajectory 8 has its original cycle 00 violation and none in cycles 01–05.','',
           '## Primary endpoint: mean across cycles 01–05','',
           'Each row averages ten trajectory means. Cycle00 is excluded. H/S/C are Biotite P-SEA assignments on coordinates; coil assignment does not establish disorder.','',
           '| Engine | Strength | n | Helix % | Sheet % | Coil % | Cα pLDDT |','|---|---:|---:|---:|---:|---:|---:|']
    for e,label in zip(ENGINES,LABELS):
        for s,st in zip(SUFFIX,STRENGTH):
            data=[t for t in tt if t['arm']==e+'_h'+s];v=[np.mean([t['mean_'+m] for t in data])*(1 if m=='plddt' else 100) for m in METRICS]
            lines.append(f'| {label} | {st} | 10 | '+' | '.join(f'{x:.1f}' for x in v)+' |')
    lines += ['', '## Final-cycle endpoint','','| Engine | Strength | Helix % | Sheet % | Coil % | Cα pLDDT |','|---|---:|---:|---:|---:|---:|']
    for e,label in zip(ENGINES,LABELS):
        for s,st in zip(SUFFIX,STRENGTH):
            data=[t for t in tt if t['arm']==e+'_h'+s];v=[np.mean([t['final_'+m] for t in data])*(1 if m=='plddt' else 100) for m in METRICS]
            lines.append(f'| {label} | {st} | '+' | '.join(f'{x:.1f}' for x in v)+' |')
    lines += ['', '## Interpretation','','This run supports initialization-only helix-kill as a simple way to shift predicted secondary structure while leaving subsequent optimization unchanged. It does not support one universally best strength. Dose response and the balance of sheet, coil and confidence depend on the engine. This campaign compares helix-kill strengths only; it cannot independently prove superiority to all of the retired controls.',
              '', '## Pairing, uncertainty and limits','',
              'Ten paired trajectory indices per engine/contrast; primary units are trajectory means across cycles 01–05. Cycles and residues are not independent replicates. Three pairwise contrasts per engine, four metrics; complete results and paired 95% bootstrap intervals appear in paired_contrasts.json. Bootstrap: 10,000 resamples, seed 906026. All intervals are exploratory, unadjusted for multiplicity. Intervals crossing zero are not proof of no effect.',
              '', 'Common design: 90 aa monomer, 50% masked initialization, SolubleMPNN, empty MSA, one predicted sample, prediction seed 42, paired initialization/MPNN seeds, temperatures 0.3 then 0.1. All engines use the declared native settings. OpenFold preserves a different X-token substitution policy; comparisons across engines are descriptive. Confidence scales are not assumed calibrated across engines. Engine/checkpoint fingerprints and hardware are preserved in the original stage receipt. No runtime/speed default is promoted.',
              '', 'No geometry-based exclusions. Only the recorded C–N and Cα–Cα continuity screen is assessed; zero warnings does not imply complete stereochemical correctness. No experimental folding, stability, binding or biological-function tests were performed.',
              '', '## Files','', 'Open **GALLERY.html** for a standalone visual report. **FIGURES.pdf** combines five figure pages. Each figure is also supplied as an editable SVG, a PDF and a 220-dpi PNG. summary.csv, structures.csv, trajectories.csv, geometry_events.csv and paired_contrasts.json contain the full analysis data. integrity.json records raw-output verification and source hashes.']
    lines += campaign_timing.report_section(timing)
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
    captions=[('01_overview','Complete benchmark','Primary endpoint: ten trajectory means per condition, cycles 01–05. Confidence dots show individual trajectories; intervals are bootstrap 95% CIs. Time bars are recorded phase spans divided by 50 optimized outputs, including initialization; overlapping timers count once. Descriptive costs on Apple M4 Max, not a controlled speed comparison.'),('02_paired_effects','Paired strength effects','Mean paired differences with 95% CIs, n=10 pairs. All intervals are exploratory and unadjusted for multiplicity.'),('03_cycle_dynamics','Dynamics through optimization','Cycle00 is explicitly shown as initialization; it is excluded from primary endpoints. Ribbons are pointwise 95% CIs across trajectories.'),('04_final_outcomes','Final-cycle distribution','Every final structure is shown. Diamonds are condition means. Compare confidence descriptively within engines.'),('05_geometry_recovery','Geometry violations and recovery','All observed violations are retained. Counts use the declared bond-distance screen; no final structure has a flagged violation.')]
    cards=[]
    for name,heading,caption in captions:
        encoded=base64.b64encode((OUT/(name+'.svg')).read_bytes()).decode()
        cards.append(f'<section><h2>{heading}</h2><p>{caption}</p><img alt="{heading}" src="data:image/svg+xml;base64,{encoded}"></section>')
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Helix control — complete benchmark</title><style>body{margin:0;background:#eef1f4;color:#111;font:16px/1.65 Arial,sans-serif}main{max-width:1200px;margin:48px auto;padding:0 24px}header{padding:30px 0}h1{font-size:42px;line-height:1.15;max-width:800px}h2{font-size:25px}small{letter-spacing:.12em}section{background:white;margin:32px 0;padding:28px;border:1px solid #d8dee5;border-radius:12px}img{display:block;width:100%;height:auto}p{max-width:900px}.stats{display:flex;gap:30px;flex-wrap:wrap}.stats b{font-size:30px;display:block}.note{border-left:4px solid #087f83;padding-left:20px}</style><main><header><small>IPROTEINSTUDIO / COMPLETE BENCHMARK / 07 SEPTEMBER 2026</small><h1>Secondary structure control starts at initialization.</h1><p>Seven prediction engines. Three helix-kill strengths. Ordinary MPNN optimization after initialization.</p><div class="stats"><div><b>210 / 210</b>completed trajectories</div><div><b>1,050</b>optimization cycles</div><div><b>0 / 210</b>final geometry warnings</div></div><p class="note">Strong control reduces mean helicity in every engine, but the confidence cost and dose response depend on the engine. Protenix Mini shows a large confidence penalty at strength 1. Protenix Constraint responds strongly already at 0.5. These are computational outcomes with n=10 per condition, not experimental folding results.</p></header>'''+''.join(cards)+'''<footer><p>All 1,260 structures reassessed from coordinates; original output hashes rechecked. Cycle00 excluded from primary endpoint. Paired bootstrap intervals use 10,000 resamples and are unadjusted for multiplicity. Full numerical tables and caveats are in REPORT.md.</p></footer></main></html>'''
    (OUT/'GALLERY.html').write_text(html)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rows,tt,integrity=load()
    timing=campaign_timing.summarize(STUDY,ENGINES,SUFFIX);campaign_timing.export(OUT,timing)
    integrity['timing_helper_sha256']=sha(Path(campaign_timing.__file__))
    integrity['timing_source_sha256']=timing['source_sha256']
    write_json(OUT/'integrity.json',integrity)
    check(sum(bool(r['geometry_violation_count']) for r in rows)==4,'Update geometry summary before rendering')
    check(sum(r['geometry_violation_count'] for r in rows)==9,'Update distance violation total')
    for name,data in [('structures',rows),('trajectories',tt),('geometry_events',[r for r in rows if r['geometry_violation_count']])]:
        fields=sorted(set().union(*(r.keys() for r in data)))
        with (OUT/(name+'.csv')).open('w') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in r.items()} for r in data)
    summary=[]
    for e,label in zip(ENGINES,LABELS):
        for s,st in zip(SUFFIX,STRENGTH):
            d=[t for t in tt if t['arm']==e+'_h'+s]
            summary.append({'engine':label,'strength':st,'n':10,'seconds_per_design':timing['arms'][e+'_h'+s]['seconds_per_design'],**{prefix+m:float(np.mean([t[prefix+m] for t in d])) for prefix in ['mean_','final_'] for m in METRICS}})
    with (OUT/'summary.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
    contrasts=figures(rows,tt,timing);report(rows,tt,integrity,contrasts,timing)
    write_json(OUT/'artifact_sha256.json',{p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name not in ['artifact_sha256.json','helix_control_complete.zip']})
    with zipfile.ZipFile(OUT/'helix_control_complete.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for p in OUT.iterdir():
            if p.is_file() and p.suffix!='.zip':archive.write(p,p.name)
    print(json.dumps({'complete':True,'output':str(OUT),'trajectories':210,'optimized_cycles':1050}),flush=True)

if __name__=='__main__':main()
