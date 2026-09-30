"""Independently audit native CLI acceptance outputs; no GPU imports."""
import json,gzip,hashlib
from pathlib import Path
import numpy as np
from biotite.structure.io import pdbx
from Bio.SeqUtils import seq1
OUT=Path(__file__).resolve().parents[2]/'output/intellifold_exact_cli_v1'
assert (OUT/'completed.json').exists(),'CLI job not complete'
sequence=json.loads((OUT.parent/'sumo_model_matrix_v1/frozen/config.json').read_text())['sequence']
rows=[]
for model in ('full','flash'):
 assert json.loads((OUT/(model+'_receipt.json')).read_text())['returncode']==0
 structures=list((OUT/model).rglob('*.cif'));assert len(structures)==3,(model,len(structures))
 for p in structures:
  a=pdbx.get_structure(pdbx.CIFFile.read(p),model=1);ca=a[a.atom_name=='CA'];n={'sumo96':96,'sumo97':97,'two_chains':103}[p.parent.name]
  assert len(ca)==n and np.isfinite(a.coord).all()
  actual={c:''.join(seq1(x) for x in ca.res_name[ca.chain_id==c]) for c in set(ca.chain_id)}
  expected={'A':sequence+'G'} if p.parent.name=='sumo97' else {'A':sequence}
  if p.parent.name=='two_chains':expected['B']='GSGSGSG'
  assert actual==expected,(actual,expected)
  for c,r in zip(ca.chain_id,ca.res_id):assert {'N','CA','C'}.issubset(set(a.atom_name[(a.chain_id==c)&(a.res_id==r)]))
  q=list(p.parent.glob('*summary_confidences.json'));assert len(q)==1;d=json.loads(q[0].read_text());assert np.isfinite(d['ptm']) and np.isfinite(d['plddt'])
  detail=next(p.parent.glob('*_confidences.json.gz'));full=json.loads(gzip.decompress(detail.read_bytes()));pae=np.asarray(full['pae']);assert pae.shape==(n,n) and np.isfinite(pae).all();assert np.isfinite(full['atom_plddts']).all()
  rows.append(dict(model=model,input=p.parent.name,tokens=n,chains=len(set(ca.chain_id)),structure=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),ptm=d['ptm'],plddt=d['plddt']))
(OUT/'audit.json').write_text(json.dumps(dict(passed=True,rows=rows),indent=2)+'\n');print(json.dumps(dict(audited=len(rows),passed=True)))
