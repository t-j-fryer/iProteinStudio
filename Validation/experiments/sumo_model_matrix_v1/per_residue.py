"""Core displacement profiles after the same fixed crystal alignment."""
import json
from pathlib import Path
import numpy as np
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT=Path(__file__).resolve().parents[2]/'output/sumo_model_matrix_v1'
d=json.loads((OUT/'analysis/results.json').read_text());engines=list(json.loads((OUT/'frozen/config.json').read_text())['engines'])
plt.rcParams.update({'font.family':'Arial','svg.fonttype':'none','xtick.direction':'in','ytick.direction':'in','text.color':'black'})
fig,axes=plt.subplots(3,3,figsize=(14,10),layout='constrained')
for ax,e in zip(axes.flat,engines):
 seen=False
 for msa,color in [('none','#555555'),('128','#0072B2'),('full','#D55E00')]:
  for budget,style in [('full','-'),('reduced','--')]:
   group=[r for r in d['rows'] if (r['engine'],r['msa'],r['budget'],r['diagnostic'])==(e,msa,budget,False) and 'core_displacements' in r]
   if len(group)!=5:continue
   seen=True;a=np.array([r['core_displacements'] for r in group]);y=np.median(a,axis=0)
   ax.plot(np.arange(21,97),y,color=color,ls=style,lw=1,label=msa+' / '+budget)
 ax.set_title(e.replace('_',' '),fontsize=11);ax.set_xlabel('SUMO residue');ax.set_ylabel('Median CA displacement (Å)');ax.spines[['top','right']].set_visible(False)
 if seen:ax.legend(fontsize=6,ncol=2,frameon=False)
 else:ax.text(.5,.5,'Pending',transform=ax.transAxes,ha='center')
fig.suptitle('Crystal-core displacement after fitting residues21–96\nMedian over five seeds; flexible N-terminal residues1–20 excluded',fontsize=13)
fig.savefig(OUT/'PER_RESIDUE.svg',transparent=True);plt.close(fig)
