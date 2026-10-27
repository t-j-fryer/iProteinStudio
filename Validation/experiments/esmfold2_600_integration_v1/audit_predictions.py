"""Read-only audit of managed 600M prediction outputs and per-sample metrics."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import biotite.structure as bst
from biotite.structure.io import pdbx
RESIDUES=dict(zip('ALA CYS ASP GLU PHE GLY HIS ILE LYS LEU MET ASN PRO GLN ARG SER THR VAL TRP TYR'.split(),'ACDEFGHIKLMNPQRSTVWY'))
def seq1(value):return RESIDUES[value]
p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
plan=json.loads(a.plan.read_text());cfg=plan['normalized_request']['config'];root=Path(plan['normalized_request']['output']);records=[]
for job in cfg['jobs']:
 leaves=list((root/'esmfold2-600-mlx').glob('bucket_*/chunk_*/'+job['name']));assert len(leaves)==1
 leaf=leaves[0];receipt=json.loads((leaf/'complete.json').read_text())
 for f,h in receipt['files'].items():assert hashlib.sha256((leaf/f).read_bytes()).hexdigest()==h,f
 models=list(leaf.glob('*_model_*.cif'));assert len(models)==cfg['num_seeds']*cfg['diffusion_samples'],len(models)
 for model in models:
  st=pdbx.get_structure(pdbx.CIFFile.read(model),model=1);assert np.isfinite(st.coord).all()
  assert set(st.chain_id)=={c['id'] for c in job['chains']}
  for c in job['chains']:
   chain=st[st.chain_id==c['id']]
   if c['kind']=='protein':assert ''.join(seq1(str(chain.res_name[i])) for i in bst.get_residue_starts(chain))==c['sequence']
   else:assert len(chain)==3 # ethanol smoke: three heavy atoms
  conf=json.loads((leaf/('confidence_'+model.stem+'.json')).read_text());assert conf['engine']=='esmfold2-600-mlx'
  for key in ('complex_plddt','ptm','iptm','confidence_score'):assert np.isfinite(conf[key]) and 0<=conf[key]<=1,(key,conf[key])
  assert conf['msa_policy']=='sequence-only';assert not any('affinity' in k for k in conf)
  assert conf['confidence_score']==conf['ptm' if len(job['chains'])==1 else 'iptm']
  if len([c for c in job['chains'] if c['kind']=='protein'])>1:assert np.isfinite(conf['ipsae_min'])
  if any(c['kind']=='ligand' for c in job['chains']):assert 0<=conf['ligand_plddt']<=100
  assert set(conf['chain_plddt'])=={c['id'] for c in job['chains']}
  for prefix in ('pae_','plddt_'):
   with np.load(leaf/(prefix+model.stem+'.npz')) as data:
    assert all(np.isfinite(data[k]).all() for k in data)
  records.append(dict(job=job['name'],model=model.name,confidence=conf))
summary=json.loads((root/'run_summary.json').read_text());assert summary['failures']==0
files={str(f.relative_to(root)):dict(sha256=hashlib.sha256(f.read_bytes()).hexdigest(),mtime_ns=f.stat().st_mtime_ns) for f in root.rglob('*') if f.is_file()}
result=dict(passed=True,plan_id=plan['id'],plan_sha256=plan['sha256'],code_snapshot=plan['code_snapshot']['sha256'],models=len(records),records=records,files=files,output=str(root))
a.output.write_text(json.dumps(result,indent=2)+'\n');print('Audited',len(records),'complete structures with exact chains, finite metrics, model identity and receipts.')
