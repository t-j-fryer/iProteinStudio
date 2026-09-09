#!/usr/bin/env python3
"""Finish a complete declared campaign with paired contrasts and exportable figures."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(Path(__file__).resolve().parent))
import campaign as c
import audit


def finish():
    report=c.read(c.OUTPUT/'analysis/report.json')
    c.require(report['complete'], 'Campaign report is incomplete')
    # Recheck recorded raw output hashes before calculating additional contrasts.
    records=[r for name in c.CONFIG['arms'] for phase in ('pilot','remaining')
             for r in audit.audit(phase,name)['trajectories']]
    c.require(len(records)==210,'Expected all 210 declared outcomes')
    data={name:{r['trajectory']:r for r in records if r['arm']==name and r['outcome']=='completed'}
          for name in c.CONFIG['arms']}
    contrasts={}
    engines=list(dict.fromkeys(name.rsplit('_h',1)[0] for name in c.CONFIG['arms']))
    for engine in engines:
        for lower,upper in [('0','0p5'),('0','1'),('0p5','1')]:
            key=f'{engine}: {lower.replace("p", ".")} to {upper.replace("p", ".")}'
            contrasts[key]={m:audit.paired(data[engine+'_h'+lower],data[engine+'_h'+upper],m) for m in audit.METRICS}
    output=c.OUTPUT/'analysis/complete_review';output.mkdir(exist_ok=True)
    c.atomic(output/'paired_contrasts.json',{'contrasts':contrasts,'manifest_sha256':c.sha(c.OUTPUT/'manifest.json'),
        'statistical_unit':'trajectory; mean of cycles01–05, cycle00 excluded',
        'uncertainty':'10,000 paired bootstrap samples, seed906026; no multiplicity adjustment'})
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'Arial','font.size':9,'axes.edgecolor':'black','text.color':'black',
                        'xtick.direction':'in','ytick.direction':'in','axes.grid':False})
    fig,axes=plt.subplots(len(engines),2,figsize=(9,13),gridspec_kw={'width_ratios':[1.6,1]},layout='constrained')
    colors=['#4477AA','#EEAA33','#BBBBBB']
    for index,engine in enumerate(engines):
        left,right=axes[index]; names=[engine+'_h'+v for v in ['0','0p5','1']]
        bottom=[0.,0.,0.]
        for metric,color in zip(['helix','sheet','coil'],colors):
            means=[statistics.mean(r['mean_'+metric] for r in data[n].values())*100 if data[n] else 0 for n in names]
            left.bar(range(3),means,bottom=bottom,color=color,edgecolor='black',linewidth=.6,label=metric.capitalize())
            bottom=[a+b for a,b in zip(bottom,means)]
        for position,name in enumerate(names):
            left.text(position,102,f'n={len(data[name])}/10',ha='center',fontsize=8)
            values=[r['mean_plddt'] for r in data[name].values()]
            if values:
                rng=random.Random(906026)
                draws=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(10000))
                mean=statistics.mean(values)
                right.errorbar(position,mean,yerr=[[mean-draws[249]],[draws[9749]-mean]],fmt='o',color='black',capsize=3)
                right.scatter([position]*len(values),values,s=10,color='#4477AA',alpha=.45)
        for ax in (left,right):ax.set_xticks(range(3),['0','0.5','1']);ax.set_xlabel('Initialization helix-kill strength');ax.set_ylim(0,110)
        left.set_ylabel(engine.replace('_',' ')+'\nResidues (%)');right.set_ylabel('CA pLDDT')
    axes[0,0].legend(loc='lower left',bbox_to_anchor=(0,1.1),ncol=3,frameon=False)
    fig.suptitle('90-aa monomers · initialization-only helix control\nTrajectory means over five optimization cycles; cycle00 excluded',fontsize=12)
    fig.savefig(output/'all_engines.svg',transparent=True);fig.savefig(output/'all_engines.png',dpi=200);plt.close(fig)
    lines=['# Complete paired helix-strength comparisons','','All three pairwise strength contrasts within each engine. H/S/C differences are percentage points; pLDDT differences use the 0–100 scale.','',
           '| Engine / contrast | Metric | Paired n | Difference | Bootstrap 95% interval |','|---|---|---:|---:|---:|']
    for name,metrics in contrasts.items():
        for metric,value in metrics.items():
            if value['n_pairs']:
                scale=1 if metric=='plddt' else 100;lo,hi=value['bootstrap_95_ci']
                lines.append(f"| {name} | {metric} | {value['n_pairs']} | {scale*value['mean_difference']:.2f} | [{scale*lo:.2f}, {scale*hi:.2f}] |")
    lines += ['', 'Intervals are exploratory and unadjusted for multiple comparisons. Plot dots represent completed trajectories; confidence error bars are marginal bootstrap intervals. Failures retain their declared seeds and are excluded from conditional structural means. Native engine defaults and OpenFold input substitutions are recorded in the manifest; this is not a speed benchmark or experimental folding validation.']
    (output/'REPORT.md').write_text('\n'.join(lines)+'\n')
    return {'complete':True,'directory':str(output),'report_sha256':c.sha(output/'REPORT.md')}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--wait',action='store_true');a=p.parse_args()
    if a.wait:
        while not (c.OUTPUT/'analysis/report.json').exists():
            log=c.OUTPUT/'controller.log'
            if log.exists():
                lines=log.read_text().splitlines()
                if lines:
                    try:last=json.loads(lines[-1])
                    except ValueError:last={}
                    if last.get('status')=='blocked':
                        c.atomic(c.OUTPUT/'analysis_status.json',{'complete':False,'controller_error':last,'time':c.now()})
                        raise SystemExit('Campaign controller stopped; outputs retained and review awaits recovery.')
            time.sleep(30)
    result=finish();c.atomic(c.OUTPUT/'analysis_status.json',result);print(json.dumps(result))
