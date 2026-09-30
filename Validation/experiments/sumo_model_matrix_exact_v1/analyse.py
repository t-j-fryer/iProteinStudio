"""CPU-only independent audit, crystal alignment and figure/report generation."""
import csv,json,sys,math,gzip
from pathlib import Path
import numpy as np
from biotite.structure.io import pdb,pdbx
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2];OUT=REPO/'Validation/output/sumo_model_matrix_exact_v1'
sys.path.insert(0,str(HERE.parent/'sumo_binder_four_engine_v1'))
from common import AA
from quality import fit
def save(p,d):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
cfg=json.loads((OUT/'frozen/config.json').read_text());ref=json.loads((OUT/'inputs/reference.json').read_text());core=np.array(ref['core_indices']);target=np.array(ref['core_ca']);analysis=OUT/'analysis';analysis.mkdir(exist_ok=True)
rows=[];failures=[];loads={};raw=[]
# A retry is always a new immutable directory; use the newest complete attempt.
for engine in cfg['engines']:
 source=Path(cfg.get('reuse_engine_outputs',{}).get(engine,OUT/engine))
 candidates=sorted([source]+list(OUT.glob(engine+'_retry*')))
 usable=[d for d in candidates if (d/'completed.json').exists()]
 directory=usable[-1] if usable else candidates[-1]
 if (directory/'load.json').exists():loads[engine]=json.loads((directory/'load.json').read_text())
 for p in sorted(directory.glob('*/measurement.json')):
  try:
   m=json.loads(p.read_text());structure=Path(m['structure']);atoms=pdbx.get_structure(pdbx.CIFFile.read(structure),model=1,extra_fields=['b_factor'])
   assert np.isfinite(atoms.coord).all()
   ca=atoms[atoms.atom_name=='CA'];sequence=''.join(AA.get(n,'?') for n in ca.res_name)
   assert sequence==cfg['sequence'] and len(set(ca.chain_id))==1,(sequence,structure)
   # Verify N/CA/C for every96 residues, not merely CA count.
   for chain,resid in zip(ca.chain_id,ca.res_id):assert {'N','CA','C'}.issubset(set(atoms.atom_name[(atoms.chain_id==chain)&(atoms.res_id==resid)]))
   points=ca.coord[core].astype(float);r,t=fit(target,points);aligned=points@r+t
   dr=np.linalg.norm(target[:,None]-target[None,:],axis=-1);dp=np.linalg.norm(points[:,None]-points[None,:],axis=-1);mask=(dr<15)&(dr>0);delta=np.abs(dr-dp)[mask];lddt=float(np.mean([np.mean(delta<c) for c in (.5,1,2,4)]))
   distances=np.linalg.norm(np.diff(ca.coord,axis=0),axis=-1)
   conf_files=[x for x in structure.parent.glob('*.json') if 'confiden' in x.name and 'full_data' not in x.name]
   assert conf_files, ('Missing confidence',structure)
   native=[json.loads(x.read_text()) for x in conf_files]
   ptm=next((float(c['ptm']) for c in native if isinstance(c,dict) and 'ptm' in c),None)
   reported=next((float(c['complex_plddt']) for c in native if isinstance(c,dict) and 'complex_plddt' in c),None)
   if reported is None:reported=next((float(c['plddt']) for c in native if isinstance(c,dict) and isinstance(c.get('plddt'),(float,int))),None)
   if reported is None:reported=next((float(c['avg_plddt']) for c in native if isinstance(c,dict) and 'avg_plddt' in c),None)
   assert ptm is not None and reported is not None, ('Unsupported or absent confidence values',conf_files)
   if reported<=1:reported*=100
   assert 0<=ptm<=1 and 0<=reported<=100
   for value in (ptm,reported):assert value is None or math.isfinite(value)
   confidence_paths=sorted(set(structure.parent.glob('*confiden*.json'))|set(structure.parent.glob('*confiden*.json.gz'))|set(structure.parent.glob('*full_data*.json'))|set(structure.parent.glob('*full_data*.json.gz'))|set(structure.parent.glob('pae*.npz'))|set(structure.parent.glob('plddt*.npz'))|set(structure.parent.glob('pde*.npz')))
   confidence_arrays={}
   for confidence_path in confidence_paths:
    if confidence_path.suffix=='.npz':
     with np.load(confidence_path,allow_pickle=False) as archive: data={k:archive[k] for k in archive.files}
    else:data=json.loads(gzip.decompress(confidence_path.read_bytes()) if confidence_path.suffix=='.gz' else confidence_path.read_text())
    for key,value in data.items():
     if key not in ('pae','pde','plddt','atom_plddts','atom_plddt','token_pair_pae','token_pair_pde'):continue
     array=np.asarray(value,dtype=float)
     assert array.size and np.isfinite(array).all(),('Non-finite confidence',confidence_path,key)
     confidence_arrays[confidence_path.name+':'+key]=list(array.shape)
   assert np.isfinite(ca.b_factor).all(),('Non-finite CIF confidence',structure)
   result={k:m[k] for k in ('engine','msa','budget','steps','recycles','seed','diagnostic','first_model_request','request_seconds','cpu_seconds','model_load_count','pid')}
   result.update(crystal_core_rmsd=float(np.sqrt(np.mean(np.sum((aligned-target)**2,axis=1)))),core_displacements=np.linalg.norm(aligned-target,axis=1).tolist(),core_ca_lddt=lddt,core_ca_plddt=float(ca.b_factor[core].mean()),ptm=ptm,reported_plddt=reported,model_seconds=m['stages'].get('model_total',{}).get('seconds'),preprocessing_seconds=m['stages'].get('preprocessing',{}).get('seconds',0),featurization_seconds=m['stages'].get('featurization',{}).get('seconds',0),decode_seconds=m['stages'].get('decode',{}).get('seconds',0),ca_neighbor_violations=int(((distances<2.5)|(distances>4.5)).sum()),core_ca_neighbor_violations=int(((distances[20:]<2.5)|(distances[20:]>4.5)).sum()),geometry_violations=len(m['geometry']['violations']),core_geometry_violations=sum(int(v['residue_1'])>=21 for v in m['geometry']['violations']),measurement=str(p),structure=str(structure),feature_shapes=m['feature_shapes'],stages=m['stages'])
   result['other_seconds']=result['request_seconds']-sum(result[k] or 0 for k in ('model_seconds','preprocessing_seconds','featurization_seconds','decode_seconds'))
   result['confidence_files']=[str(x) for x in confidence_paths];result['confidence_arrays']=confidence_arrays
   atoms.coord=atoms.coord@r+t;destination=analysis/'aligned'/engine/(p.parent.name+'.pdb');destination.parent.mkdir(parents=True,exist_ok=True);pf=pdb.PDBFile();pf.set_structure(atoms);pf.write(destination);result['aligned_pdb']=str(destination)
   rows.append(result)
  except Exception as e:failures.append(dict(measurement=str(p),error=repr(e)))
normal=[r for r in rows if not r['diagnostic']];summaries=[]
coverage=[]
for engine in cfg['engines']:
 engine_rows=[r for r in rows if r['engine']==engine]
 expected_msas=['none'] if engine=='esmfold2_fast' else ['none','128','full']
 missing=[];integrity_errors=[]
 for msa in expected_msas:
  for budget in ('full','reduced'):
   for seed,diagnostic in [(s,False) for s in cfg['seeds']]+[(42,True)]:
    matches=[r for r in engine_rows if (r['msa'],r['budget'],r['seed'],r['diagnostic'])==(msa,budget,seed,diagnostic)]
    if not matches:missing.append([msa,budget,seed,diagnostic])
    elif len(matches)!=1:integrity_errors.append('Duplicate '+str([msa,budget,seed,diagnostic]))
    else:
     row=matches[0]
     if row['steps']!=cfg['engines'][engine][budget] or row['recycles']!=cfg['engines'][engine]['recycles']:integrity_errors.append('Settings mismatch '+row['measurement'])
     if row['model_load_count']!=1:integrity_errors.append('Model reloaded '+row['measurement'])
     if engine=='openfold3' and 'seed_'+str(seed) not in Path(row['structure']).parts:integrity_errors.append('Output seed mismatch '+row['structure'])
 if len({r['pid'] for r in engine_rows})>1:integrity_errors.append('More than one worker PID')
 coverage.append(dict(engine=engine,audited=len(engine_rows),expected=len(expected_msas)*12,missing=missing,integrity_errors=integrity_errors))
save(analysis/'coverage.json',dict(engines=coverage,complete=all(not c['missing'] and not c['integrity_errors'] for c in coverage) and not failures))
for engine in cfg['engines']:
 for msa in ('none','128','full'):
  for budget in ('full','reduced'):
   group=[r for r in normal if (r['engine'],r['msa'],r['budget'])==(engine,msa,budget)]
   if not group:continue
   warm=[r for r in group if not r['first_model_request']]
   s=dict(engine=engine,msa=msa,budget=budget,n=len(group),warm_n=len(warm),steps=group[0]['steps'],geometry_flagged=sum(r['geometry_violations']>0 or r['ca_neighbor_violations']>0 for r in group),core_geometry_flagged=sum(r['core_geometry_violations']>0 or r['core_ca_neighbor_violations']>0 for r in group))
   for metric in ('request_seconds','model_seconds','preprocessing_seconds','featurization_seconds','other_seconds','crystal_core_rmsd','core_ca_lddt','core_ca_plddt','reported_plddt'):
    values=[r[metric] for r in group if r[metric] is not None]
    if values:s[metric]=dict(median=float(np.median(values)),min=float(min(values)),max=float(max(values)))
   for metric in ('request_seconds','model_seconds'):
    values=[r[metric] for r in warm if r[metric] is not None]
    if values:s['warm_'+metric]=float(np.median(values))
   summaries.append(s)
save(analysis/'results.json',dict(rows=rows,summaries=summaries,loads=loads,audit_failures=failures,reference=ref,normal_count=len(normal),diagnostic_count=len(rows)-len(normal)))
if rows:
 keys=[k for k in rows[0] if k not in ('feature_shapes','stages','core_displacements','confidence_files','confidence_arrays')]
 with (analysis/'measurements.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(rows)
lines=['# Resident SUMO model benchmark','','Status: '+str(len(normal))+'/250 normal predictions audited; '+str(len(rows)-len(normal))+'/50 diagnostic replays. Audit failures: '+str(len(failures))+'.','','Five seeds42–46 per cell; one sample; native recycles. Each engine loads once and receives sequential requests. First request flagged separately. Profile replays are excluded from throughput medians. Fixed96-aa yeast SUMO; crystal3QHT chainA query21–96 core; no template. Single target, not a general model accuracy ranking.','','| Engine | MSA | Steps | n | Warm n | Warm request median(s) | Warm model median(s) | Core RMSD median[min,max](Å) | Core CA-lDDT | Geometry flagged: whole/core |','|---|---|---:|---:|---:|---:|---:|---|---:|---:|']
for s in summaries:
 q=s['crystal_core_rmsd'];lines.append(f"| {s['engine']} | {s['msa']} | {s['steps']} | {s['n']} | {s['warm_n']} | {s.get('warm_request_seconds',float('nan')):.2f} | {s.get('warm_model_seconds',float('nan')):.2f} | {q['median']:.3f} [{q['min']:.3f},{q['max']:.3f}] | {s['core_ca_lddt']['median']:.3f} | {s['geometry_flagged']}/{s['n']} / {s['core_geometry_flagged']}/{s['n']} |")
lines+=['','## Loading','','| Engine | Model/session initialization(s) | Imports plus setup(s) |','|---|---:|---:|']
for e,l in loads.items():lines.append(f"| {e} | {l['seconds']:.2f} | {l['imports_and_setup_seconds']:.2f} |")
lines+=['','MSA full means the cached8060 rows supplied to each engine, followed by its native processing/cap;128 uses the same frozen subset for every engine. Fast has no MSA capability. Model-input shapes are retained per request. Reduced steps:200→25,100→13,50→6,5→1; integer rounding prevents exact one-eighth for the last three.','', 'Detailed normal-call preprocessing, featurization, model, decoding and residual times are in measurements.csv. Per-stage CPU and synchronized wall times are in results.json. Diagnostic stages are nested, not additive; barriers perturb execution. CPU process-time/wall-time is a host-thread-use indicator, not GPU utilization. Model-loading timings include adapter initialization and asset verification; lazy device transfer/compilation can occur in the flagged first request. Imports/setup are separately reported.','', 'Crystal-core fit excludes the mobile N terminus. CA-lDDT uses core pairs within15Å and thresholds0.5/1/2/4Å. Native confidence scales are not calibrated across models. Structures are under analysis/aligned/. No diffusion/MSA/recycle settings promoted; exact-token sizing deployed after separate CLI acceptance. Biotin remains paused.']
lines+=['','Exact-token revision: IntelliFold uses native exact sizing. Unchanged Boltz and ESM results are referenced from the original matrix; see frozen/config.json for raw-source paths. The cancelled padded IntelliFold runs remain in sumo_model_matrix_v1.','','## Reading the comparison','','These are scientific-budget comparisons, not equivalent-output optimizations. Five independent seeds characterize variability; identical seed integers do not imply the same random trajectory between different models. Warm timing excludes only the first-ever request to each model, leaving four warm timing observations in that first condition and five elsewhere. Conditions run in a fixed order; thermal/order effects have not been randomized.','','Full/reduced labels are requested native settings. ESMFold2 truncates its denoising schedule internally: the pinned configurations yield 68/10 iterations for Full requests of 100/13, and 34/5 for Fast requests of 50/6; see analysis/esm_native_schedules.json. Geometry flags are advisories retained in the dataset, separated into whole-chain and core counts. A comparable core RMSD does not excuse malformed backbone geometry.','','Figures: [overview](OVERVIEW.svg), [all seed distributions](DISTRIBUTIONS.svg), [stage profiles](STAGES.svg), [loading](LOADING.svg), and [core residue errors](PER_RESIDUE.svg). Machine-readable [coverage audit](analysis/coverage.json), [runtime versions](analysis/runtime_versions.json), [diffusion contrasts](analysis/paired_contrasts.json), [padding contrasts](analysis/padding_contrasts.json), and [profiling replay parity](analysis/diagnostic_parity.json).']
(OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
if summaries:
 import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
 plt.rcParams.update({'font.family':'Arial','svg.fonttype':'none','text.color':'black','axes.labelcolor':'black','xtick.direction':'in','ytick.direction':'in'})
 engines=list(cfg['engines']);cells=[(m,b) for m in ('none','128','full') for b in ('full','reduced')]
 fig,axes=plt.subplots(1,3,figsize=(17,6.4),layout='constrained')
 for ax,metric,title in zip(axes,['warm_request_seconds','warm_model_seconds','crystal_core_rmsd'],['Resident request median (s)','Model computation median (s)','Crystal-core CA RMSD (Å)']):
  values=np.full((len(engines),len(cells)),np.nan)
  for s in summaries:
   value=s.get(metric);value=value['median'] if isinstance(value,dict) else value
   if value is not None:values[engines.index(s['engine']),cells.index((s['msa'],s['budget']))]=value
  ax.imshow(values,cmap='YlGnBu',aspect='auto',vmin=0 if metric=='crystal_core_rmsd' else None,vmax=5 if metric=='crystal_core_rmsd' else None);ax.set_title(title+(' · colour capped at 5 Å' if metric=='crystal_core_rmsd' else ''));ax.set_xticks(range(6),[m+'\n'+b for m,b in cells]);ax.set_yticks(range(len(engines)),[e.replace('_',' ') for e in engines]);ax.tick_params(length=0)
  for i in range(len(engines)):
   for j in range(6):
    v=values[i,j];ax.text(j,i,('N/A' if engines[i]=='esmfold2_fast' and cells[j][0]!='none' else '—') if np.isnan(v) else f'{v:.2f}',ha='center',va='center',color='black',fontsize=9,bbox=dict(facecolor='white',alpha=.75,edgecolor='none',pad=1))
 fig.suptitle(f'SUMO monomer · {len(normal)}/250 predictions audited · native versus reduced diffusion budget\nUp to 5 seeds per condition; first model request excluded from warm timing; counts in report',fontsize=13)
 fig.savefig(OUT/'OVERVIEW.svg',transparent=True);fig.savefig(OUT/'OVERVIEW.png',dpi=130);plt.close(fig)
print(json.dumps(dict(normal=len(normal),diagnostic=len(rows)-len(normal),audit_failures=failures,complete_engines=[e for e in cfg['engines'] if sum(r['engine']==e for r in normal)==(10 if e=='esmfold2_fast' else 30)])))

import hashlib
files={}
for row in rows:
 for value in (row["measurement"],row["structure"],*row['confidence_files']):
  q=Path(value);files[value]=hashlib.sha256(q.read_bytes()).hexdigest()
save(analysis/"output_hashes.json",files)

for q in [Path(__file__), HERE/'quality.py', HERE.parent/"sumo_binder_four_engine_v1/common.py", OUT/"inputs/reference.json", OUT/"inputs/3QHT.cif"]:
 files[str(q)]=hashlib.sha256(q.read_bytes()).hexdigest()
save(analysis/"output_hashes.json",files)
