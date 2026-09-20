"""Audit final managed prediction outputs without editing their raw files."""
import gzip,json,sys,hashlib
from pathlib import Path
import gemmi,numpy as np
from crystal_compare import OUT,reference,aligned,extract
REPO=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO/'Sources/iProteinStudio/Resources/pipeline/scripts'))
import validate_prediction_geometry as geometry
seq=json.loads((REPO/'Validation/experiments/apple_runtime_throughput_v1/manifest.json').read_text())['cases'][1]['sequence']
reports=[]
for record in json.loads((OUT/'installed_smoke_jobs.json').read_text()):
 root=Path(record['job']['output_root'])
 cfg=json.loads((root/'prediction_config.json').read_text());chain=cfg['jobs'][0]['chains'][0]
 assert chain['sequence']==seq and chain['msa'] not in ('auto','empty')
 msa_sha=hashlib.sha256(Path(chain['msa']).read_bytes()).hexdigest()
 assert msa_sha=='c5c2ee22f8430f0144c602338fdb250d6ce69e1f851753bf8a8ce5046702f0ff'
 assert cfg['msa']['allow_server'] is False and cfg['diffusion_samples']==1 and cfg['num_seeds']==1
 if record['engine']=='boltz':assert cfg['use_potentials'] is True
 cifs={p.resolve() for p in root.rglob('*.cif') if 'processed' not in p.parts};assert len(cifs)==1,(root,cifs)
 cif=next(iter(cifs));st=gemmi.read_structure(str(cif));assert len(st)==1
 sequence='';ca=[];coords=[]
 for chain in st[0]:
  for res in chain:
   for atom in res:
    coords.append([atom.pos.x,atom.pos.y,atom.pos.z])
    if atom.name=='CA':sequence+=gemmi.find_tabulated_residue(res.name).one_letter_code;ca.append(coords[-1])
 assert sequence==seq and np.isfinite(coords).all()
 g=geometry.inspect_geometry(cif);assert not g['errors']
 matrices={};scalars={}
 for p in root.rglob('*'):
  if not p.is_file() or 'processed' in p.parts:continue
  if p.suffix=='.npz' and p.name.startswith(('pae_','pde_')):
   with np.load(p) as z:
    for k in z.files:matrices[k]=z[k]
  if 'confidence' in p.name and p.name.endswith(('.json','.json.gz')):
   with (gzip.open(p,'rt') if p.suffix=='.gz' else p.open()) as f:d=json.load(f)
   if not isinstance(d,dict):continue
   for k in ('pae','pde','token_pair_pae','token_pair_pde'):
    if k in d and np.asarray(d[k]).ndim>=2:matrices[k]=np.asarray(d[k])
   for k in ('ptm','pTM','plddt','complex_plddt','mean_plddt'):
    if isinstance(d.get(k),(int,float)):scalars[k]=d[k]
 assert matrices and scalars,(root,matrices.keys(),scalars)
 for k,v in matrices.items():assert v.shape[-2:]==(len(seq),len(seq)) and np.isfinite(v).all(),(k,v.shape)
 assert all(np.isfinite(v) for v in scalars.values())
 ref,core,receipt=reference('sumo',seq);rmsd=aligned(np.array([ref[i] for i in core]),np.array(ca)[core])[0]
 comparison=None
 if record['engine']=='intellifold':
  engine='intellifold-flash' if record['model']=='v2-flash' else 'intellifold-full'
  frozen=next(OUT.glob(engine+'_msa_20*'));prior=Path(json.loads((frozen/'progress.json').read_text())['candidate']);control=extract(prior/'unit_00',engine)
  errors={k:dict(mae=float(np.abs(v-matrices[k]).mean()),p95=float(np.percentile(np.abs(v-matrices[k]),95))) for k,v in control['matrices'].items()}
  confidence_delta={k:abs(v-scalars[k]) for k,v in control['confidence'].items() if k in scalars}
  delta=aligned(control['ca'][core],np.array(ca)[core])[0]
  assert delta<.5 and all(v<.02 for v in confidence_delta.values()) and all(v['mae']<.5 and v['p95']<2 for v in errors.values())
  comparison=dict(core_ca_rmsd=delta,confidence_delta=confidence_delta,matrices=errors,context='Installed CLI with production threads and Flash padding versus frozen resident2.14; settings retained, not a timing pair.')
 reports.append(dict(engine=record['engine'],model=record['model'],output=str(root),structure=str(cif),comparison_to_isolated=comparison,sequence_exact=True,msa_sha256=msa_sha,finite_coordinates=True,geometry_violations=len(g['violations']),core_crystal_rmsd=rmsd,confidence=scalars,matrices={k:list(v.shape) for k,v in matrices.items()}))
(OUT/'INSTALLED_OUTPUT_AUDIT.json').write_text(json.dumps(reports,indent=2)+'\n');print(json.dumps(reports,indent=2))
