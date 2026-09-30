"""Independent CPU output audit and same-seed comparison of overhead variants."""
import gzip,hashlib,json,sys,statistics
from pathlib import Path
import numpy as np
from biotite.structure.io import pdbx
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent;OUT=HERE.parents[1]/'output/sumo_request_overhead_v1_retry01';BASE=HERE.parents[1]/'output/sumo_model_matrix_exact_v1'
sys.path.insert(0,str(HERE.parent/'sumo_model_matrix_exact_v1'))
from quality import fit
sys.path.insert(0,str(HERE.parent/'sumo_binder_four_engine_v1'))
from common import AA
cfg=json.loads((OUT/'frozen/config.json').read_text());ref=json.loads((BASE/'inputs/reference.json').read_text());core=np.array(ref['core_indices']);target=np.array(ref['core_ca'])
analysis=OUT/'analysis';analysis.mkdir(exist_ok=True)
FOLLOW=OUT.parent/'sumo_request_overhead_v1_followup'
DEEP=OUT.parent/'sumo_request_overhead_v1_deep'
ARRAYS=OUT.parent/'sumo_request_overhead_v1_arrays'
CONFIRM=OUT.parent/'sumo_request_overhead_v1_confirmation'
FINAL=OUT.parent/'sumo_request_overhead_v1_final'
for extra in (FOLLOW,DEEP,ARRAYS,CONFIRM,FINAL):
 if (extra/'frozen/config.json').exists():
  for arm in json.loads((extra/'frozen/config.json').read_text())['arms']:
   if arm not in cfg['arms'] and not arm[1].startswith('batch'):cfg['arms'].append(arm)
cfg['arms'].append(['intellifold_full','baseline_interleaved'])
rows=[];errors=[];structures={};hashes={}
for folder in [p for root in (OUT,FOLLOW,DEEP,ARRAYS,CONFIRM,FINAL) if root.exists() for p in sorted(root.iterdir())]:
 if not folder.is_dir() or '__' not in folder.name:continue
 for receipt in sorted(folder.glob('*/measurement.json')):
  try:
   m=json.loads(receipt.read_text());path=Path(m['structure']);a=pdbx.get_structure(pdbx.CIFFile.read(path),model=1,extra_fields=['b_factor']);ca=a[a.atom_name=='CA']
   assert ''.join(AA.get(x,'?') for x in ca.res_name)==cfg['sequence'];assert np.isfinite(a.coord).all() and np.isfinite(a.b_factor).all()
   for resid in ca.res_id:assert {'N','CA','C'}.issubset(set(a.atom_name[a.res_id==resid]))
   conf={}
   for f in path.parent.iterdir():
    if ('confiden' in f.name or 'full_data' in f.name) and (f.name.endswith('.json') or f.name.endswith('.json.gz')):
     values=json.loads(gzip.decompress(f.read_bytes()) if f.suffix=='.gz' else f.read_text())
     for key,value in values.items():
      if key in ('pae','pde','plddt','atom_plddts','atom_plddt','token_pair_pae','token_pair_pde','ptm','iptm','avg_plddt','complex_plddt','confidence_score') and value is not None:
       arr=np.asarray(value,dtype=float);assert np.isfinite(arr).all();conf[key]=arr
     hashes[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
    elif f.suffix=='.npz' and ('pae' in f.name or 'plddt' in f.name or 'pde' in f.name):
     with np.load(f,allow_pickle=False) as data:
      for k in data.files:
       arr=np.asarray(data[k],dtype=float);assert np.isfinite(arr).all();conf[f.stem+':'+k]=arr
     hashes[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
   assert 'ptm' in conf and any(k in conf for k in ('complex_plddt','plddt','avg_plddt')),(path,list(conf))
   pts=ca.coord[core].astype(float);rot,trans=fit(target,pts);rmsd=float(np.sqrt(np.mean(np.sum((pts@rot+trans-target)**2,axis=1))))
   dr=np.linalg.norm(target[:,None]-target[None,:],axis=-1);dp=np.linalg.norm(pts[:,None]-pts[None,:],axis=-1);mask=(dr<15)&(dr>0);delta=np.abs(dr-dp)[mask];lddt=float(np.mean([np.mean(delta<c) for c in (.5,1,2,4)]))
   r={k:m[k] for k in ('engine','variant','seed','diagnostic','first_model_request','request_seconds','stages','mps_bytes','rss_peak_bytes','model_device_after')}
   r.update(model_seconds=m['stages']['model_total']['seconds'],crystal_core_rmsd=rmsd,core_lddt=lddt,geometry_violations=len(m['geometry']['violations']),structure=str(path),measurement=str(receipt),feature_shapes=m['feature_shapes'])
   r['outside_seconds']=r['request_seconds']-r['model_seconds'];rows.append(r);structures[str(path)]=(a,ca,conf);hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();hashes[str(receipt)]=hashlib.sha256(receipt.read_bytes()).hexdigest()
  except Exception as e:errors.append(dict(path=str(receipt),error=repr(e)))
normal=[r for r in rows if not r['diagnostic'] and not r['first_model_request']]
lookup={(r['engine'],r['variant'],r['seed']):r for r in normal}
pairs=[]
for r in normal:
 if r['variant']=='baseline':continue
 b=lookup.get((r['engine'],'baseline_interleaved' if r['variant']=='ccd_interleaved' else 'baseline',r['seed']))
 if b is None:continue
 a,ca,c=structures[r['structure']];ba,bca,bc=structures[b['structure']]
 assert np.array_equal(a.atom_name,ba.atom_name) and np.array_equal(a.res_id,ba.res_id)
 point=ca.coord[core].astype(float);rot,trans=fit(bca.coord[core].astype(float),point)
 delta_conf={k:float(np.max(np.abs(c[k]-bc[k]))) for k in c.keys()&bc.keys() if c[k].shape==bc[k].shape and c[k].size}
 pairs.append(dict(engine=r['engine'],variant=r['variant'],seed=r['seed'],speedup=b['request_seconds']/r['request_seconds'],coordinate_exact=bool(np.array_equal(a.coord,ba.coord)),max_atom_delta=float(np.abs(a.coord-ba.coord).max()),core_rmsd_to_baseline=float(np.sqrt(np.mean(np.sum((point@rot+trans-bca.coord[core])**2,axis=1)))),confidence_keys_equal=set(c)==set(bc),confidence_max_differences=delta_conf,confidence_exact=set(c)==set(bc) and all(np.array_equal(c[k],bc[k]) for k in c)))
 confidence_ok=set(c)==set(bc) and all(c[k].shape==bc[k].shape for k in c)
 for k,diff in delta_conf.items():
  threshold=.01 if 'pae' in k or 'pde' in k else (.001*(100 if max(float(c[k].max()),float(bc[k].max()))>1.1 else 1) if 'plddt' in k else .0001)
  confidence_ok=confidence_ok and diff<=threshold
 pairs[-1]['numerical_screen_pass']=pairs[-1]['core_rmsd_to_baseline']<=.01 and confidence_ok and r['geometry_violations']<=b['geometry_violations']
summary=[]
for engine,variant in cfg['arms']:
 group=[r for r in normal if r['engine']==engine and r['variant']==variant]
 if not group:continue
 p=[r for r in pairs if r['engine']==engine and r['variant']==variant]
 summary.append(dict(engine=engine,variant=variant,n=len(group),**{k:statistics.median(r[k] for r in group) for k in ('request_seconds','model_seconds','outside_seconds','crystal_core_rmsd','core_lddt')},geometry_flagged=sum(r['geometry_violations']>0 for r in group),paired_n=len(p),all_coordinate_exact=all(r['coordinate_exact'] for r in p) if p else None,all_confidence_exact=all(r['confidence_exact'] for r in p) if p else None,max_core_rmsd_to_baseline=max((r['core_rmsd_to_baseline'] for r in p),default=None)))
 summary[-1]['numerical_screen_pass']=all(r['numerical_screen_pass'] for r in p) if len(p)==5 else None
payload=dict(rows=rows,pairs=pairs,summaries=summary,audit_errors=errors,normal_count=len(normal))
(analysis/'results.json').write_text(json.dumps(payload,indent=2)+'\n');(analysis/'hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
plt.rcParams.update({'font.family':'Arial','svg.fonttype':'none','xtick.direction':'in','ytick.direction':'in','text.color':'black','axes.labelcolor':'black'})
fig,axes=plt.subplots(2,2,figsize=(14,9),layout='constrained')
for ax,engine in zip(axes.flat,dict.fromkeys(e for e,v in cfg['arms'])):
 ss=[s for s in summary if s['engine']==engine]
 order=['baseline','w1','w2','w0','w0_keep','w0_keep_arrays','w0_keep_features','keep','keep_prepared','ccd','ccd_prepared','baseline_recheck','w0_keep_features_keyed','baseline_interleaved','ccd_interleaved']
 ss.sort(key=lambda s:order.index(s['variant']))
 for i,s in enumerate(ss):
  ax.bar(i,s['request_seconds'],color='#82b4cd',edgecolor='black');ax.bar(i,s['model_seconds'],color='#e8ac75',edgecolor='black')
  vals=[r['request_seconds'] for r in normal if r['engine']==engine and r['variant']==s['variant']];ax.scatter(np.linspace(i-.12,i+.12,len(vals)),vals,s=12,c='black',zorder=3)
 labels={'baseline':'Control','w1':'1 worker','w2':'2 workers','w0':'0 workers','w0_keep':'0 workers\n+ MPS','w0_keep_arrays':'0 + MPS\n+ arrays','w0_keep_features':'Cache attempt\n(no hits)','keep':'Keep MPS','keep_prepared':'MPS + parsed\ninput cache','ccd':'CCD cache','ccd_prepared':'CCD + parsed\ninput cache','baseline_recheck':'Control\nrepeat','w0_keep_features_keyed':'0 + MPS\n+ reused features','baseline_interleaved':'Paired\ncontrol','ccd_interleaved':'Paired\nCCD cache'}
 ax.set_xticks(range(len(ss)),[labels[s['variant']] for s in ss],rotation=20,fontsize=8);ax.set_title(engine.replace('_',' '));ax.set_ylabel('Seconds per resident request');ax.spines[['top','right']].set_visible(False)
fig.suptitle('SUMO96 / 128-row MSA / 25 diffusion steps / 5 warm seeds per arm\nBlue: full request median; orange: inference median; dots: individual requests. Medians independent.')
fig.savefig(OUT/'OVERVIEW.svg',transparent=True);fig.savefig(OUT/'OVERVIEW.png',dpi=130);plt.close(fig)
lines=['# Resident request optimization results','',f'{len(normal)} normal outputs audited; {len(errors)} audit errors. Warmup and cProfile requests excluded.','', '|Engine|Variant|n|Request s|Model s|Outside s|Core RMSD Å|Exact coordinates/confidence|','|---|---|---:|---:|---:|---:|---:|---|']
for s in summary:lines.append(f"|{s['engine']}|{s['variant']}|{s['n']}|{s['request_seconds']:.3f}|{s['model_seconds']:.3f}|{s['outside_seconds']:.3f}|{s['crystal_core_rmsd']:.3f}|{s['all_coordinate_exact']}/{s['all_confidence_exact']}|")
lines+=['','One target/M4 Max64GB; isolated sequential arms. Native recycles retained. All setup/loading/caching cold costs are reported in per-arm load/warmup receipts, not hidden in warm medians. Experimental hooks; no app settings promoted. Baseline outputs must remain scientifically comparable; diagnostic cProfile timings are excluded.']
(OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(dict(normal=len(normal),errors=errors,summaries=summary),indent=2))
