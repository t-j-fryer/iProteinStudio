"""Audit small release cases; not a scientific-quality or speed benchmark."""
import csv,hashlib,json
from pathlib import Path
import gemmi,numpy as np
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'Validation/output/rfd3_motif_release_v1';managed=Path.home()/'.iproteinstudio'
result={}
for name in ['motif','partial']:
 d=OUT/name;j=json.loads((d/'job.json').read_text());s=json.loads((managed/'agent/jobs'/j['id']/'state.json').read_text());assert s['status']=='completed',s
 r=Path(j['output_root']);rows=list(csv.DictReader((r/'analysis/design_metrics.csv').open()));assert len(rows)==1
 paths=list((r/'rfd3/backbones').glob('*.pdb'));assert len(paths)==1
 structures=[]
 for p in paths+list((r/'predictions').rglob('*model_0.cif')):
  st=gemmi.read_structure(str(p));atoms=[a for c in st[0] for res in c for a in res];coords=np.array([[a.pos.x,a.pos.y,a.pos.z] for a in atoms]);assert len(atoms)>0 and np.isfinite(coords).all()
  ca=[(c.name,res.seqid.num,a.pos) for c in st[0] for res in c for a in res if a.name=='CA']
  clashes=sum(1 for i,(c,n,p1) in enumerate(ca) for c2,n2,p2 in ca[i+1:] if not(c==c2 and abs(n-n2)<=1) and p1.dist(p2)<2.0)
  structures.append(dict(path=str(p.relative_to(r)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),atoms=len(atoms),nonadjacent_ca_pairs_below_2A=clashes))
 assert len(structures)==3
 f=np.load(next((r/'rfd3/fixtures').glob('*.npz')))
 mask=f['feats/is_motif_atom_unindexed'].astype(bool)&f['feats/is_motif_atom_with_fixed_coord'].astype(bool)
 if name=='motif': assert int(mask.sum())==9
 result[name]=dict(job=j['id'],status=s['status'],runtime_manifest=json.loads((OUT/'rfd3-candidate-receipt.json').read_text())['manifest_sha256'],structures=structures,unindexed_fixed_atoms=int(mask.sum()),sequence_length=len(rows[0]['sequence']),is_hit=rows[0]['is_hit'],failed_filters=rows[0]['failed_filters'],motif_insertion_rmsd=rows[0].get('motif_insertion_rmsd'),motif_max_drift=rows[0].get('motif_max_drift'))
report=dict(passed=True,cases=result,scope='Two execution/geometry smoke cases; no statistical quality, speedup, or binding claim',ca_clash_definition='CA pairs below 2 Angstrom, excluding adjacent residues of the same chain')
(OUT/'output-audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
