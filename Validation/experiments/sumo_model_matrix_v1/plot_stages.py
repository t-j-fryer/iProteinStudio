"""Diagnostic stage plots; nested components are intentionally separate bars."""
import json,os
from pathlib import Path
import numpy as np
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT=Path(__file__).resolve().parents[2]/'output/sumo_model_matrix_v1'
d=json.loads((OUT/'analysis/results.json').read_text());engines=list(d['loads'])
plt.rcParams.update({'font.family':'Arial','svg.fonttype':'none','axes.labelcolor':'black','text.color':'black','xtick.direction':'in','ytick.direction':'in'})
fig,axes=plt.subplots(3,3,figsize=(15,11),layout='constrained')
for ax in axes.flat:ax.set_visible(False)
for ax,e in zip(axes.flat,engines):
 group=[r for r in d['rows'] if r['engine']==e and r['diagnostic'] and r['budget']=='full' and r['msa']==('none' if e=='esmfold2_fast' else 'full')]
 if not group:continue
 ax.set_visible(True);r=group[0];stages=r['stages'];names=[k for k in stages if k!='model_total'];times=[stages[k]['seconds'] for k in names]
 ax.barh(range(len(names)),times,color='#86b8cd',edgecolor='black');ax.set_yticks(range(len(names)),[n.replace('_',' ') for n in names],fontsize=8);ax.invert_yaxis();ax.set_xlabel('Synchronized diagnostic wall time (s)');ax.set_title(e.replace('_',' ')+'\nModel total '+f"{r['model_seconds']:.2f}s",fontsize=10)
 ax.spines[['top','right']].set_visible(False)
fig.suptitle('Native diffusion budget, full MSA where supported · one seed42 diagnostic per engine\nStages can overlap/nest (e.g. ESM embedding within trunk); do not sum these bars',fontsize=13)
fig.savefig(OUT/'STAGES.svg',transparent=True);plt.close(fig)
fig,ax=plt.subplots(figsize=(10,5),layout='constrained');values=[d['loads'][e]['seconds'] for e in engines]
ax.barh(range(len(engines)),values,color='#86b8cd',edgecolor='black');ax.set_yticks(range(len(engines)),[e.replace('_',' ') for e in engines]);ax.invert_yaxis();ax.set_xlabel('Session initialization and weight loading (s)');ax.spines[['top','right']].set_visible(False);ax.set_title('One resident worker per model · one measured initialization\nLazy device transfer/compilation can occur in the first request')
fig.savefig(OUT/'LOADING.svg',transparent=True);plt.close(fig)
# Keep the additional structural-detail figure in each automatic report refresh.
import runpy
runpy.run_path(str(Path(__file__).with_name('per_residue.py')),run_name='__main__')
runpy.run_path(str(Path(__file__).with_name('distributions.py')),run_name='__main__')
runpy.run_path(str(Path(__file__).with_name('diagnostic_parity.py')),run_name='__main__')
