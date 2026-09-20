"""Standalone scientific figure; each mark is one unchanged full prediction."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from crystal_compare import OUT
plt.rcParams.update({'font.family':'Arial','font.size':10,'svg.fonttype':'none','axes.edgecolor':'black','text.color':'black','xtick.direction':'in','ytick.direction':'in'})
old=json.loads((OUT/'crystal_comparison.json').read_text())['rows']
new=json.loads((OUT/'msa_comparison.json').read_text())
engines=['protenix','constraint','intellifold-flash','intellifold-full'];labels=['Protenix v2','Protenix Constraint','IntelliFold Flash','IntelliFold Full']
fig,ax=plt.subplots(figsize=(9,4.7));colors=['#436a9f','#ce7029']
for i,engine in enumerate(engines):
 runs=[v for k,v in new.items() if k.startswith(engine+'_msa_') and v.get('complete')]
 assert len(runs)==1,f'Missing unique complete MSA pair for {engine}'
 for j,arm in enumerate(['baseline','candidate']):
  a=[r for r in old if r['engine']==engine and r['arm']==arm and r['input']=='sumo' and '_smoke_' in r['run']];assert len(a)==1
  b=[r for r in runs[0]['rows'] if r['arm']==arm];assert len(b)==1
  y=i+(-.13 if j==0 else .13);x=[a[0]['core_ca_rmsd'],b[0]['core_ca_rmsd']]
  ax.plot(x,[y,y],color=colors[j],alpha=.3,lw=1)
  for k,value in enumerate(x):
   ax.scatter(value,y,s=66,marker='o' if k==0 else 'D',facecolors='white' if k==0 else colors[j],edgecolors=colors[j],linewidths=1.4,zorder=3,label=(('Original runtime' if j==0 else 'Torch 2.14')+(' · no MSA' if k==0 else ' · MSA')) if i==0 else None)
  ax.annotate(f'{x[1]:.2f}',(min(x),y),xytext=(-8,0),textcoords='offset points',ha='right',va='center',fontsize=9)
ax.set_yticks(range(4),labels);ax.invert_yaxis();ax.set_xlim(0,10);ax.set_xlabel('SUMO core CA RMSD to crystal (Å; lower is better)');ax.spines[['top','right']].set_visible(False);ax.grid(False)
ax.legend(loc='upper center',bbox_to_anchor=(.5,1.23),ncol=2,frameon=False,fontsize=9)
fig.text(.02,.018,'Each mark: one seed-42 prediction. Same sequence, checkpoint and full model settings. MSA pairs use the same cached alignment.\nReference: yeast Smt3, 3QHT chain A, query residues 21–96; flexible N-terminus excluded. One Mac/protein/seed; no experimental binding claim.',fontsize=8)
fig.subplots_adjust(left=.22,right=.98,bottom=.2,top=.76)
fig.savefig(OUT/'MSA_CRYSTAL_COMPARISON.svg',transparent=True);fig.savefig(OUT/'MSA_CRYSTAL_COMPARISON.png',dpi=160);plt.close(fig)
