#!/usr/bin/env python3
"""Standalone scientific overview of audited, bounded screening results."""
import argparse
import json
import os
from pathlib import Path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('output',type=Path);a=ap.parse_args();out=a.output.resolve()
    os.environ['MPLCONFIGDIR']=str(out/'matplotlib_cache')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    data=json.loads((out/'measurements.json').read_text());records=[r for r in data['records'] if not r['warmup']]
    plt.rcParams.update({'font.family':'Arial','font.size':10,'axes.edgecolor':'black','axes.labelcolor':'black','text.color':'black','xtick.direction':'in','ytick.direction':'in','svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,2,figsize=(13,8));colors={'ubiquitin':'#497b9f','sumo':'#c77d3b'}
    ax=axes[0,0]
    runs=sorted({r['run'] for r in records if r['run'].startswith(('smoke_','repeat_'))})
    for i,name in enumerate(colors):
        for j,run in enumerate(runs):
            pair=[next((r for r in records if r['run']==run and r['name']==name and r['torch']==v),None) for v in ('2.13.0','2.14.0')]
            if not all(pair):continue
            xs=np.array([i*3,i*3+1])+(j-1)*.1
            ax.plot(xs,[r['seconds'] for r in pair],'-o',color=colors[name],alpha=.75,lw=1,ms=5)
    ax.set_xticks([0,1,3,4],['2.13','2.14','2.13','2.14']);ax.set_ylabel('Seconds per prediction call');ax.set_title('A  Runtime upgrade: paired process blocks',loc='left',weight='bold')
    ax.text(.25,-.21,'Ubiquitin',transform=ax.transAxes,ha='center',color='black');ax.text(.78,-.21,'SUMO',transform=ax.transAxes,ha='center',color='black')
    ax=axes[0,1]
    for name,color in colors.items():
        points=sorted((r['threads'],r['seconds']) for r in records if r['run'].startswith('threads_') and r['name']==name)
        if points:ax.plot(*zip(*points),'-o',label=name,color=color,lw=1.3)
    ax.set_xticks([1,4,8,12]);ax.set_xlabel('CPU intra-op thread budget');ax.set_ylabel('Seconds per prediction call');ax.set_title('B  CPU threads: one block per budget',loc='left',weight='bold');ax.legend(frameon=False)
    ax=axes[1,0]
    stage_colors={'diffusion_sample':'#497b9f','pairformer_module':'#91b1c5','preprocessing':'#c77d3b','other':'#cccccc'}
    for i,name in enumerate(colors):
        rows=[r for r in records if r['run'].startswith('profile_') and r['block']=='profile' and r['name']==name]
        if not rows:continue
        r=rows[0];m=json.loads(Path(r['path']).read_text());st=m['profile']['stages'];values={k:st[k]['seconds'] for k in ('diffusion_sample','pairformer_module','preprocessing')};values['other']=r['seconds']-sum(values.values());left=0
        for key,value in values.items():
            pct=100*value/r['seconds'];ax.barh(i,pct,left=left,color=stage_colors[key],edgecolor='black',linewidth=.5,label=key.replace('_',' ') if i==0 else None)
            if pct>15:ax.text(left+pct/2,i,f'{pct:.0f}%',ha='center',va='center',color='white' if key=='diffusion_sample' else 'black')
            left+=pct
    ax.set_yticks([0,1],['Ubiquitin','SUMO']);ax.set_xlim(0,100);ax.set_xlabel('Share of synchronized diagnostic call (%)');ax.set_title('C  Where the time goes',loc='left',weight='bold');ax.legend(frameon=False,fontsize=8,loc='upper center',bbox_to_anchor=(.5,-.23),ncol=2)
    ax=axes[1,1]
    comparisons=[c for c in data['comparisons'] if any(k in c['path'] for k in ('schedule_','precision_'))]
    if comparisons:
        for i,c in enumerate(comparisons):
            pairs=[p for p in c['pairs'] if not p['warmup']]
            ratio=sum(p['seconds_baseline'] for p in pairs)/sum(p['seconds_candidate'] for p in pairs)
            name='Schedule host reads' if 'schedule_' in c['path'] else 'Diffusion BF16'
            ax.barh(i,ratio,color='#769b82' if c['passed'] else '#c27474',edgecolor='black',height=.5)
            ax.text(max(ratio+.03,1.04),i,f'{ratio:.2f}×; '+('accuracy pass' if c['passed'] else 'accuracy fail'),va='center',fontsize=9)
            ax.set_yticks(range(len(comparisons)),['Schedule host reads' if 'schedule_' in x['path'] else 'Diffusion BF16' for x in comparisons])
        ax.set_ylim(-.6,len(comparisons)-.4)
        ax.axvline(1,color='black',lw=.8,ls='--');ax.set_xlim(0,max(1.6,max(p.get('speed_ratio',1) for c in comparisons for p in c['pairs'])+.5))
    else:ax.text(.5,.5,'Pending',ha='center',transform=ax.transAxes)
    ax.set_xlabel('Control time / candidate time (higher is faster)');ax.set_title('D  Implementation experiments',loc='left',weight='bold')
    fig.suptitle('Boltz-2 on M4 Max: initial throughput and accuracy screen',fontsize=16,weight='bold',y=.98)
    fig.text(.5,.015,'64 GB · macOS 26.6.1 · 200 steps · 3 recycles · guidance retained · one output/sample\nTwo small monomers; one warmup per process. Limited repeats, variable timings. No defaults promoted or design success established.',ha='center',fontsize=9)
    fig.subplots_adjust(top=.89,bottom=.20,left=.08,right=.97,hspace=.68,wspace=.4)
    fig.savefig(out/'OVERVIEW.svg',transparent=True);fig.savefig(out/'OVERVIEW.png',dpi=150)


if __name__=='__main__':main()
