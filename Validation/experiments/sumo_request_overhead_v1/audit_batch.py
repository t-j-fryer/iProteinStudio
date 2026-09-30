"""Audit directory-style results; report amortized throughput separately."""
import json,sys,statistics,hashlib
from pathlib import Path
import numpy as np
from biotite.structure.io import pdbx
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent;OUT=HERE.parents[1]/'output/sumo_request_overhead_v1_retry01';FOLLOW=OUT.parent/'sumo_request_overhead_v1_followup'
sys.path.insert(0,str(HERE.parent/'sumo_model_matrix_exact_v1'))
from quality import fit
sys.path.insert(0,str(HERE.parents[2]/'Sources/iProteinStudio/Resources/pipeline/scripts'))
from validate_prediction_geometry import inspect_geometry
cfg=json.loads((OUT/'frozen/config.json').read_text());data=json.loads((OUT/'analysis/results.json').read_text())
base={r['seed']:r for r in data['rows'] if r['engine']=='openfold3' and r['variant']=='baseline' and not r['diagnostic'] and not r['first_model_request']}
def read(path):
 a=pdbx.get_structure(pdbx.CIFFile.read(path),model=1,extra_fields=['b_factor']);assert np.isfinite(a.coord).all() and np.isfinite(a.b_factor).all()
 conf={}
 for p in path.parent.glob('*confiden*.json'):
  for k,v in json.loads(p.read_text()).items():
   if k in ('ptm','avg_plddt','plddt','pae','pde'):
    conf[k]=np.asarray(v,dtype=float);assert np.isfinite(conf[k]).all()
 assert 'ptm' in conf and 'avg_plddt' in conf
 return a,conf
rows=[];errors=[]
for variant in ('batch0','batch2'):
 p=FOLLOW/('openfold3__'+variant)/'batch_measurement.json'
 if not p.exists():continue
 m=json.loads(p.read_text());pairs=[]
 try:
  assert m['seeds']==[42,43,44,45,46] and len(m['structures'])==5
  for source in m['structures']:
   path=Path(source);seed=int(path.parent.name.split('_')[-1]);a,c=read(path);b,bc=read(Path(base[seed]['structure']))
   assert np.array_equal(a.atom_name,b.atom_name) and np.array_equal(a.res_name,b.res_name) and np.array_equal(a.res_id,b.res_id)
   geometry=inspect_geometry(path);assert not geometry['errors'] and not geometry['violations'],geometry
   ca=a.coord[a.atom_name=='CA'][20:].astype(float);bca=b.coord[b.atom_name=='CA'][20:].astype(float);r,t=fit(bca,ca)
   pairs.append(dict(seed=seed,structure=source,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),core_rmsd_to_baseline=float(np.sqrt(np.mean(np.sum((ca@r+t-bca)**2,axis=1)))),coordinate_exact=bool(np.array_equal(a.coord,b.coord)),confidence_max_differences={k:float(np.abs(c[k]-bc[k]).max()) for k in c},confidence_exact=set(c)==set(bc) and all(np.array_equal(c[k],bc[k]) for k in c)))
  rows.append(dict(variant=variant,total_seconds=m['request_seconds'],amortized_seconds=m['amortized_seconds'],model_seconds_per_prediction=m['stages']['model_total']['seconds']/5,pairs=pairs,feature_shapes=m['feature_shapes']))
 except Exception as e:errors.append(dict(path=str(p),error=repr(e)))
result=dict(rows=rows,errors=errors,unit='One five-seed directory-style request per variant; not five repeated request timings')
(OUT/'analysis/batch_results.json').write_text(json.dumps(result,indent=2)+'\n')
if rows:
 plt.rcParams.update({'font.family':'Arial','svg.fonttype':'none','xtick.direction':'in','ytick.direction':'in'})
 fig,ax=plt.subplots(figsize=(8,4),layout='constrained');labels=[];values=[]
 singles=[r for r in data['rows'] if r['engine']=='openfold3' and r['variant']=='w0_keep' and not r['diagnostic'] and not r['first_model_request']]
 if len(singles)==5:labels.append('Separate requests\n0 workers, model on MPS');values.append(sum(r['request_seconds'] for r in singles)/5)
 for row in rows:labels.append(row['variant']+'\nfive-seed directory request');values.append(row['amortized_seconds'])
 ax.bar(labels,values,color='#82b4cd',edgecolor='black');ax.set_ylabel('Total measured time / 5 predictions (s)');ax.spines[['top','right']].set_visible(False);ax.set_title('OpenFold bounded CPU prefetch\nSUMO96, MSA128, 25 diffusion steps; one five-seed group per condition')
 fig.savefig(OUT/'BATCH_THROUGHPUT.svg',transparent=True);plt.close(fig)
print(json.dumps(result,indent=2))
