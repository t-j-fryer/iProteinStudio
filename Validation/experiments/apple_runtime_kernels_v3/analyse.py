"""Independent CPU output audit and prespecified practical equivalence gates."""
import argparse,gzip,json,sys
from pathlib import Path
import numpy as np
import gemmi
from coordinator import verify_complete
from worker import atomic,sha
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2];OUT=REPO/'Validation/output/apple_runtime_kernels_v3'
POLICY_PATH=HERE/'analysis_policy.json'
POLICY=json.loads(POLICY_PATH.read_text())
sys.path.insert(0,str(REPO/'Sources/iProteinStudio/Resources/pipeline/scripts'))
import validate_prediction_geometry as geometry

def document(p):
 with (gzip.open(p,'rt') if p.suffix=='.gz' else p.open()) as f:return json.load(f)
def aligned(x,y):
 x=x-x.mean(0);y=y-y.mean(0);u,_,vt=np.linalg.svd(y.T@x);d=np.eye(3);d[-1,-1]=np.linalg.det(u@vt);delta=np.linalg.norm(y@(u@d@vt)-x,axis=1)
 return float(np.sqrt(np.mean(delta**2))),float(np.percentile(delta,95))
def extract(unit,engine):
 m=document(unit/'measurement.json');result=dict(measurement=m)
 if engine=='nesso':
  import struct
  p=next((unit/'prediction/esm').glob('*.safetensors'));raw=p.read_bytes();n=struct.unpack('<Q',raw[:8])[0];h=json.loads(raw[8:8+n]);info=h['embeddings'];assert info['dtype']=='F32';lo,hi=info['data_offsets'];assert hi-lo==int(np.prod(info['shape']))*4
  result['embedding']=np.frombuffer(raw[8+n+lo:8+n+hi],dtype='<f4').reshape(info['shape']);result['scores']=document(unit/'prediction/affinity.json')['scores']
  assert np.isfinite(result['embedding']).all() and result['embedding'].shape==(1,len(m['sequence'])+2,1280)
  return result
 if engine=='antifold':
  result['logits']=np.load(unit/'logits.npy');assert result['logits'].shape==(len(m['sequence']),20) and np.isfinite(result['logits']).all();return result
 if engine=='rfd3':
  z=np.load(unit/'prediction.npz');result.update(ca=z['ca'],coordinates=z['coordinates'],sequence_indices=z['sequence_indices'])
  assert result['coordinates'].shape==(14*len(m['sequence']),3) and np.isfinite(result['coordinates']).all()
  result['breaks']={int(i) for i,d in enumerate(np.linalg.norm(np.diff(result['ca'],axis=0),axis=1)) if d<2.8 or d>4.5}
  return result
 structures={p.resolve() for p in (unit/'prediction').rglob('*.cif') if 'processed' not in p.parts}
 assert len(structures)==1,f'Expected one unique prediction, found {len(structures)}'
 seq='';ids=[];coords=[];ca=[];ca_plddt=[]
 if engine=='openfold':
  # OpenFold omits occupancy; Gemmi's Structure reader returns zero models.
  # Read the raw atom-site loop explicitly, without modifying the saved CIF.
  cols,rows=geometry.cif_atom_rows(next(iter(structures)));lookup={k.removeprefix('_atom_site.'):i for i,k in enumerate(cols)}
  for row in rows:
   def field(key):return row[lookup[key]]
   assert field('pdbx_PDB_model_num')=='1' and field('label_alt_id') in ('.','?')
   name=field('label_atom_id');res=field('label_comp_id')
   ids.append((field('label_asym_id'),field('label_seq_id'),res,name))
   v=[float(field('Cartn_'+k)) for k in 'xyz'];coords.append(v)
   if name=='CA':seq+=gemmi.find_tabulated_residue(res).one_letter_code;ca.append(v);ca_plddt.append(float(field('B_iso_or_equiv')))
 else:
  st=gemmi.read_structure(str(next(iter(structures))));assert len(st)==1,'Expected exactly one structural model'
  for chain in st[0]:
   for residue in chain:
    if residue.find_atom('CA','*'):seq+=gemmi.find_tabulated_residue(residue.name).one_letter_code
    for atom in residue:
     ids.append((chain.name,str(residue.seqid),residue.name,atom.name));v=[atom.pos.x,atom.pos.y,atom.pos.z];coords.append(v)
     if atom.name=='CA':ca.append(v);ca_plddt.append(atom.b_iso)
 assert seq==m['sequence'],(seq,m['sequence'])
 assert np.isfinite(coords).all() and len(ca)==len(seq)
 result.update(ca=np.asarray(ca),ca_plddt=np.asarray(ca_plddt),ids=ids)
 g=geometry.inspect_geometry(next(iter(structures)));assert not g['errors'];result['breaks']={json.dumps({k:v.get(k) for k in ('model','chain','residue_1','residue_2','atoms')},sort_keys=True) for v in g['violations']}
 matrices={};conf={};files={p.resolve() for p in (unit/'prediction').rglob('*') if p.is_file() and ('confidence' in p.name or 'full_data' in p.name)}
 for p in files:
  if p.name.endswith(('.json','.json.gz')):
   d=document(p)
   if not isinstance(d,dict):continue
   for source,k in (('pae','pae'),('pde','pde'),('token_pair_pae','pae'),('token_pair_pde','pde')):
    if source in d:
     arr=np.asarray(d[source],dtype=float)
     if arr.ndim>=2:matrices[k]=arr
   for k in ('plddt','complex_plddt','ptm','pTM','avg_plddt','mean_plddt'):
    if k in d and isinstance(d[k],(int,float)):
     v=float(d[k]);conf[k]=v/100 if 'plddt' in k.lower() and v>1 else v

 if engine=='boltz':
  for p in (unit/'prediction').rglob('pae_*_model_0.npz'):matrices['pae']=np.load(p)['pae']
 result.update(matrices=matrices,confidence=conf)
 assert matrices,'Missing full pair-error matrix'
 assert conf,'Missing scalar confidence'
 for k,v in matrices.items():assert np.isfinite(v).all() and v.shape[-2:]==(len(seq),len(seq)),(k,v.shape)
 for v in conf.values():assert np.isfinite(v)
 return result

def compare(a,b,engine,limits):
 metrics={};fail=[];ma=a['measurement'];mb=b['measurement']
 assert (ma['name'],ma['sequence'],ma['seed'],ma['warmup'])==(mb['name'],mb['sequence'],mb['seed'],mb['warmup'])
 def gate(name,value,limit):
  metrics[name]=float(value)
  if not np.isfinite(value) or value>limit:fail.append(name)
 if engine=='nesso':
  x,y=a['embedding'],b['embedding'];gate('esm_relative_l2',np.linalg.norm(y-x)/np.linalg.norm(x),limits['esm_relative_l2_max'])
  assert a['scores'].keys()==b['scores'].keys()
  for k,v in a['scores'].items():
   if v is None or b['scores'][k] is None:fail.append('missing score '+k);continue
   gate('score_delta_'+k,abs(v-b['scores'][k]),limits['nesso_scalar_absolute_max'])
 elif engine=='antifold':
  gate('logit_max_absolute',np.abs(a['logits']-b['logits']).max(),limits['logit_absolute_max'])
 else:
  if engine!='rfd3':assert a['ids']==b['ids'],'Atom identity mismatch'
  x,y=a['ca'],b['ca'];whole_r,whole_p=aligned(x,y);core_available=True
  if ma['name']=='sumo' and engine!='rfd3':
   rule=POLICY['sumo_core'];mask=a['ca_plddt']>=rule['baseline_ca_plddt_min']
   mask[:rule.get('exclude_n_terminal_residues',0)]=False
   metrics.update(whole_ca_rmsd=whole_r,whole_ca_displacement_p95=whole_p,sumo_core_residues=int(mask.sum()),sumo_core_indices_1based=(np.flatnonzero(mask)+1).tolist())
   if mask.sum()<rule['minimum_residues']:
    fail.append('insufficient high-confidence SUMO core');core_available=False
   else:
    x,y=x[mask],y[mask]
    gate('sumo_core_plddt_mean_delta',abs(a['ca_plddt'][mask].mean()-b['ca_plddt'][mask].mean())/100,limits['normalized_confidence_max'])
  if core_available:
   r,p=aligned(x,y);gate('ca_rmsd',r,limits['ca_rmsd_max']);gate('ca_displacement_p95',p,limits['ca_displacement_p95_max'])
  if b['breaks']-a['breaks']:fail.append('new backbone breaks')
  metrics['baseline_breaks']=len(a['breaks']);metrics['candidate_breaks']=len(b['breaks'])
  if engine=='rfd3':
   metrics['sequence_index_changes']=int(np.count_nonzero(a['sequence_indices']!=b['sequence_indices']))
   # Studio exports backbone geometry, then uses MPNN; this unused head is diagnostic only.
  else:
   assert a['matrices'].keys()==b['matrices'].keys()
   for k,x in a['matrices'].items():
    delta=np.abs(x-b['matrices'][k]);gate(k+'_mae',delta.mean(),limits['pair_error_mae_max']);gate(k+'_p95',np.percentile(delta,95),limits['pair_error_p95_max'])
   assert a['confidence'].keys()==b['confidence'].keys()
   for k,v in a['confidence'].items():gate('delta_'+k,abs(v-b['confidence'][k]),limits['normalized_confidence_max'])
 return dict(name=ma['name'],warmup=ma['warmup'],passed=not fail,failures=fail,metrics=metrics,baseline_seconds=ma['seconds'],candidate_seconds=mb['seconds'],ratio=ma['seconds']/mb['seconds'])

def analyse(run):
 cfg=document(run/'frozen/run.json');engine=cfg['blocks'][0]['engine'];progress=document(run/'progress.json');audits={};errors=[]
 for block,path in progress.items():
  p=Path(path);verify_complete(p,p.parent/(p.name+'.request.json'))
  if cfg['blocks'][0].get('diagnostic') in ('kernel','norm_kernel'):continue
  try:audits[block]=[extract(Path(x).parent,engine) for x in document(p/'result.json')['rows']]
  except Exception as e:errors.append(dict(block=block,error=repr(e)))
 if cfg['blocks'][0].get('diagnostic')=='rng' and len(progress)==2:
  za,zb=[np.load(Path(progress[k])/'random_draws.npz') for k in ('baseline','candidate')]
  draws={k:dict(exact=bool(np.array_equal(za[k],zb[k])),max_absolute=float(np.max(np.abs(za[k]-zb[k]))),mean_absolute=float(np.mean(np.abs(za[k]-zb[k])))) for k in za.files}
  atomic(run/'generator_comparison.json',dict(draws=draws,all_exact=all(x['exact'] for x in draws.values())))
 pairs=[]
 left='baseline' if 'baseline' in audits else 'reference'
 right='candidate' if 'candidate' in audits else 'variant'
 if 'threads4' in audits and 'threads1' in audits:left,right='threads4','threads1'
 if left in audits and right in audits:
  declarations={b['id']:b for b in cfg['blocks']}
  for key in ('engine','seed','threads','torch_version','cases'):
   assert declarations[left][key]==declarations[right][key],('Paired protocol mismatch',key)
  limits=document(run/'frozen/manifest.json')['acceptance']
  pairs=[compare(a,b,engine,limits) for a,b in zip(audits[left],audits[right],strict=True)]
 tape=[]
 if cfg['blocks'][0].get('random_tape') and left in audits and right in audits:
  paths=[document(Path(progress[k])/'result.json')['rows'] for k in (left,right)]
  for pa,pb in zip(*paths,strict=True):
   pa,pb=Path(pa).parent/'random_tape.npz',Path(pb).parent/'random_tape.npz'
   with np.load(pa) as za,np.load(pb) as zb:
    exact=za.files==zb.files and all(np.array_equal(za[k],zb[k]) for k in za.files)
    tape.append(dict(draw_count=len(za.files),identical_draws=exact))
    if not exact:errors.append(dict(error='Random replay arrays differ',baseline=str(pa),candidate=str(pb)))
 if cfg['blocks'][0].get('diagnostic') in ('kernel','norm_kernel'):
  for block,path in progress.items():
   kernel=document(Path(path)/'kernel.json')
   if not kernel['passed']:errors.append(dict(block=block,error='kernel numerical gate failed'))
 result=dict(engine=engine,run=str(run),complete=(run/'completed.json').exists(),errors=errors,blocks_audited=list(audits),pairs=pairs,passed=not errors and bool(pairs) and all(x['passed'] for x in pairs))
 if cfg['blocks'][0].get('diagnostic') in ('kernel','norm_kernel'):result['passed']=not errors and bool(progress)
 if tape:result['random_tape_audit']=tape
 result['analysis_policy']=dict(**POLICY,sha256=sha(POLICY_PATH))
 result['analysis_code_sha256']=sha(__file__)
 previous=run/'analysis.json';original=run/'analysis_original_whole_chain.json'
 if previous.exists():
  prior=document(previous).get('analysis_policy')
  if prior and prior.get('sha256')!=result['analysis_policy']['sha256']:
   archived=run/('analysis_'+prior['revision']+'.json')
   if not archived.exists():archived.write_text(previous.read_text())
 if previous.exists() and not original.exists() and not document(previous).get('analysis_policy'):
  original.write_text(previous.read_text())
 atomic(run/'analysis.json',result);return result
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('runs',nargs='*');a=ap.parse_args()
 for run in ([Path(x) for x in a.runs] if a.runs else sorted(OUT.glob('*_20*'))):
  if (run/'progress.json').exists():
   try:
    r=analyse(run);print(json.dumps(r))
   except Exception as e:print(json.dumps(dict(run=str(run),error=repr(e))))
