"""Show all seed-level measurements rather than only summary heatmaps."""
import json
from pathlib import Path
import numpy as np
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT=Path(__file__).resolve().parents[2]/'output/sumo_model_matrix_exact_v1'
d=json.loads((OUT/'analysis/results.json').read_text());engines=list(json.loads((OUT/'frozen/config.json').read_text())['engines']);cells=[(m,b) for m in ('none','128','full') for b in ('full','reduced')]
plt.rcParams.update({'font.family':'Arial','svg.fonttype':'none','xtick.direction':'in','ytick.direction':'in','text.color':'black'})
fig,axes=plt.subplots(len(engines),2,figsize=(13,22),layout='constrained');colors={'none':'#777777','128':'#0072B2','full':'#D55E00'}
for pair,e in zip(axes,engines):
 for ax,metric,label in zip(pair,['request_seconds','crystal_core_rmsd'],['Resident request (s)','Crystal-core CA RMSD (Å)']):
  for j,(msa,budget) in enumerate(cells):
   group=sorted([r for r in d['rows'] if (r['engine'],r['msa'],r['budget'],r['diagnostic'])==(e,msa,budget,False)],key=lambda r:r['seed'])
   for r in group:
    cold=r['first_model_request'] and metric=='request_seconds'
    ax.scatter(j+(r['seed']-44)*.06,r[metric],s=22,facecolors='none' if cold else colors[msa],edgecolors=colors[msa],linewidths=1,zorder=3)
   values=[r[metric] for r in group if metric!='request_seconds' or not r['first_model_request']]
   if values:ax.scatter(j,np.median(values),marker='D',s=32,c='black',zorder=4)
  ax.set_title(e.replace('_',' '),fontsize=10);ax.set_ylabel(label);ax.set_xlim(-.5,5.5);ax.set_xticks(range(6),[m+'\n'+b for m,b in cells],fontsize=8);ax.spines[['top','right']].set_visible(False)
fig.suptitle('SUMO: individual seeds42–46 · black diamonds are medians\nOpen timing point = first model request (excluded from warm median); diagnostics excluded',fontsize=13)
fig.savefig(OUT/'DISTRIBUTIONS.svg',transparent=True);plt.close(fig)
