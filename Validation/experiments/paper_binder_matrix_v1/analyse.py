"""Independent finite-confidence/hash audit and matched complex comparisons."""
import json,gzip,sys,csv,statistics,hashlib
from pathlib import Path
import numpy as np
from biotite.structure.io import pdbx
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]/'output/paper_binder_matrix_v1'
sys.path.insert(0,str(HERE.parent/'sumo_model_matrix_exact_v1'))
from quality import fit
def confidence(path):
 result={}
 keys={'pae','pde','plddt','atom_plddts','atom_plddt','token_pair_pae','token_pair_pde','ptm','iptm','avg_plddt','complex_plddt','confidence_score','ipsae_min'}
 for f in path.parent.iterdir():
  if any(x in f.name for x in ('confidence','full_data')) and (f.name.endswith('.json') or f.name.endswith('.json.gz')):
   values=json.loads(gzip.decompress(f.read_bytes()) if f.suffix=='.gz' else f.read_text())
   for key,value in values.items():
    if key in keys and value is not None:
     arr=np.asarray(value,dtype=float);assert np.isfinite(arr).all(),(f,key);result[key]=arr
  elif f.suffix=='.npz' and any(x in f.name for x in ('pae','plddt','pde')):
   with np.load(f,allow_pickle=False) as data:
    for key in data.files:
     arr=np.asarray(data[key],dtype=float);assert np.isfinite(arr).all(),(f,key);result[f.stem.split('_')[0]+':'+key]=arr
 assert 'ptm' in result and any('plddt' in k for k in result),(path,list(result))
 return result
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 phase=sys.argv[1] if len(sys.argv)>1 else 'benchmark';out=ROOT/phase;report=out/'analysis';report.mkdir(exist_ok=True)
 cfg=json.loads((out/'frozen/config.json').read_text());rows=[];errors=[];structures={}
 for f in sorted(out.glob('*__*/**/measurement.json')):
  try:
   m=json.loads(f.read_text());unit=f.parent;complete=json.loads((unit/'complete.json').read_text());assert all(sha(p)==h for p,h in complete['files'].items())
   a=pdbx.get_structure(pdbx.CIFFile.read(m['structure']),model=1);assert np.isfinite(a.coord).all()
   c=confidence(Path(m['structure']));structures[m['structure']]=(a,c)
   m['measurement']=str(f);m['model_seconds']=m['stages']['model_total']['seconds'];m['outside_seconds']=m['request_seconds']-m['model_seconds']
   m['scalar_confidence']={k:float(v) for k,v in c.items() if v.size==1}
   m['geometry_count']=len(m['geometry']['violations']);rows.append(m)
  except Exception as e:errors.append(dict(path=str(f),error=repr(e)))
 normal=[r for r in rows if not r['warmup'] and not r['diagnostic']]
 lookup={(r['engine'],r['variant'],r['design_name'],r['seed']):r for r in normal};pairs=[]
 if cfg.get('control_phase'):
  for f in (ROOT/cfg['control_phase']).glob('*__baseline/*/measurement.json'):
   m=json.loads(f.read_text())
   if m['warmup'] or m['diagnostic']:continue
   receipt=json.loads(f.with_name('complete.json').read_text());assert all(sha(p)==h for p,h in receipt['files'].items())
   a=pdbx.get_structure(pdbx.CIFFile.read(m['structure']),model=1);assert np.isfinite(a.coord).all()
   structures[m['structure']]=(a,confidence(Path(m['structure'])))
   m['geometry_count']=len(m['geometry']['violations'])
   lookup[(m['engine'],'baseline',m['design_name'],m['seed'])]=m
 for r in normal:
  control='resident' if phase=='positions' else 'baseline'
  if r['variant']==control:continue
  b=lookup.get((r['engine'],control,r['design_name'],r['seed']))
  if not b:continue
  a,c=structures[r['structure']];ba,bc=structures[b['structure']]
  assert np.array_equal(a.atom_name,ba.atom_name) and np.array_equal(a.chain_id,ba.chain_id) and np.array_equal(a.res_id,ba.res_id)
  backbone=np.isin(a.atom_name,['N','CA','C']);x=a.coord[backbone].astype(float);y=ba.coord[backbone].astype(float);rot,t=fit(y,x);rmsd=float(np.sqrt(np.mean(np.sum((x@rot+t-y)**2,axis=1))))
  target=(a.chain_id=='B')&(a.atom_name=='CA');targetids=np.flatnonzero(target)[20:] # benchmark SUMO flexibleN20 excluded
  rot,t=fit(ba.coord[targetids].astype(float),a.coord[targetids].astype(float));binder=(a.chain_id=='A')&(a.atom_name=='CA')
  target_core_rmsd=float(np.sqrt(np.mean(np.sum((a.coord[targetids]@rot+t-ba.coord[targetids])**2,axis=1))))
  binder_rmsd=float(np.sqrt(np.mean(np.sum((a.coord[binder]@rot+t-ba.coord[binder])**2,axis=1))))
  samekeys=set(c)==set(bc) and all(c[k].shape==bc[k].shape for k in c)
  diffs={k:dict(max=float(np.abs(c[k]-bc[k]).max()),mean=float(np.abs(c[k]-bc[k]).mean())) for k in c if k in bc and c[k].shape==bc[k].shape and c[k].size}
  confok=samekeys
  for k,v in diffs.items():
   if 'pae' in k or 'pde' in k:confok=confok and v['mean']<=.1
   else:confok=confok and v['max']<=(1 if 'plddt' in k and max(float(c[k].max()),float(bc[k].max()))>1.1 else .01)
  pairs.append(dict(engine=r['engine'],variant=r['variant'],design_name=r['design_name'],seed=r['seed'],baseline_seconds=b['request_seconds'],request_seconds=r['request_seconds'],paired_saving_seconds=b['request_seconds']-r['request_seconds'],coordinate_exact=bool(np.array_equal(a.coord,ba.coord)),confidence_exact=samekeys and all(np.array_equal(c[k],bc[k]) for k in c),complex_backbone_rmsd=rmsd,binder_rmsd_after_target_core=binder_rmsd,confidence_differences=diffs,geometry_change=r['geometry_count']-b['geometry_count'],pass_gate=rmsd<=.1 and binder_rmsd<=.2 and confok and r['geometry_count']<=b['geometry_count']))
  pairs[-1]['target_core_ca_rmsd']=target_core_rmsd
 summaries=[]
 for engine,variant in cfg['arms']:
  rr=[r for r in normal if r['engine']==engine and r['variant']==variant];pp=[p for p in pairs if p['engine']==engine and p['variant']==variant]
  if not rr:continue
  summaries.append(dict(engine=engine,variant=variant,n=len(rr),**{k:statistics.median(r[k] for r in rr) for k in ('request_seconds','model_seconds','outside_seconds')},paired_n=len(pp),paired_median_saving=statistics.median(p['paired_saving_seconds'] for p in pp) if pp else None,all_exact=all(p['coordinate_exact'] and p['confidence_exact'] for p in pp) if pp else None,gate=all(p['pass_gate'] for p in pp) if len(pp)==5 else None))
 expected={(e,v,row['design_name'],42+i) for e,v in cfg['arms'] for i,row in enumerate(cfg['selected_rows'])}
 observed={(r['engine'],r['variant'],r['design_name'],r['seed']) for r in normal}
 coverage=dict(expected=len(expected),observed=len(observed),missing=sorted(expected-observed),unexpected=sorted(observed-expected))
 if len(normal)!=len(observed):errors.append(dict(error='Duplicate engine/variant/design/seed outputs'))
 data=dict(normal_count=len(normal),audit_errors=errors,coverage=coverage,rows=rows,pairs=pairs,summaries=summaries)
 (report/'results.json').write_text(json.dumps(data,indent=2)+'\n')
 with (report/'timings.csv').open('w') as f:
  fields=['engine','variant','design_name','target_key','seed','request_seconds','model_seconds','outside_seconds','audit_seconds','geometry_count'];w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(normal)
 with (report/'stages.csv').open('w') as f:
  w=csv.writer(f);w.writerow(['engine','variant','design_name','seed','stage','calls','seconds','cpu_seconds','nested_not_additive'])
  for r in normal:
   for stage,s in r['stages'].items():w.writerow([r['engine'],r['variant'],r['design_name'],r['seed'],stage,s['calls'],s['seconds'],s['cpu_seconds'],True])
 lines=['# Shared-target optimization screen','',f'{len(normal)}/{len(expected)} normal predictions audited; {len(errors)} audit errors. {len(cfg["selected_rows"])} distinct SUMO binder(s), paired sequence/seed across variants. All outer GPU stage timers synchronized; dispatch timers are CPU only. Nested stage times are not additive. Warmup/cProfile excluded.','', '|Engine|Variant|n|Request s|Model s|Outside s|Paired saving s|Exact|Gate|','|---|---|---:|---:|---:|---:|---:|---|---|']
 for s in summaries:lines.append(f"|{s['engine']}|{s['variant']}|{s['n']}|{s['request_seconds']:.3f}|{s['model_seconds']:.3f}|{s['outside_seconds']:.3f}|{s['paired_median_saving']}|{s['all_exact']}|{s['gate']}|")
 (out/'REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps(dict(normal=len(normal),errors=errors,summaries=summaries),indent=2))
 if cfg.get('control_phase'):
  with (out/'REPORT.md').open('a') as f:f.write('\n'+cfg['control_purpose']+'\n')
 if summaries:
  import matplotlib;matplotlib.use('Agg')
  import matplotlib.pyplot as plt
  plt.rcParams.update({'font.family':'Arial','svg.fonttype':'none','xtick.direction':'in','ytick.direction':'in','text.color':'black','axes.labelcolor':'black'})
  engines=list(dict.fromkeys(e for e,v in cfg['arms']));height=(len(engines)+1)//2
  fig,axes=plt.subplots(height,2,figsize=(12,3.8*height),squeeze=False,layout='constrained')
  for ax,engine in zip(axes.flat,engines):
   ss=[s for s in summaries if s['engine']==engine]
   if not ss:ax.text(.5,.5,'Awaiting results',ha='center',va='center',transform=ax.transAxes)
   for i,s in enumerate(ss):
    ax.bar(i,s['request_seconds'],color='#82b4cd',edgecolor='black');ax.bar(i,s['model_seconds'],color='#e8ac75',edgecolor='black')
    values=[r['request_seconds'] for r in normal if r['engine']==engine and r['variant']==s['variant']];ax.scatter(np.linspace(i-.12,i+.12,len(values)),values,c='black',s=12,zorder=3)
   ax.set_xticks(range(len(ss)),[s['variant']+('\nfailed output gate' if s['gate'] is False else '') for s in ss],rotation=20);ax.set_title(engine.replace('_',' '));ax.set_ylabel('Seconds per request');ax.spines[['top','right']].set_visible(False)
  for ax in list(axes.flat)[len(engines):]:ax.set_visible(False)
  fig.suptitle(f"Different binders against SUMO96: shared-target optimization\nBars: independent request/model medians; dots: {len(cfg['selected_rows'])} distinct binder(s)/seed(s) per completed arm\nTarget MSA ≤128 and reduced steps; ESMFold2 Fast: no MSA, full 50 steps")
  from matplotlib.patches import Patch
  fig.legend(handles=[Patch(facecolor='#82b4cd',edgecolor='black',label='Resident request'),Patch(facecolor='#e8ac75',edgecolor='black',label='Model computation')],loc='outside lower center',ncol=2)
  fig.savefig(out/'OVERVIEW.svg',transparent=True);fig.savefig(out/'OVERVIEW.png',dpi=120);plt.close(fig)
if __name__=='__main__':main()
