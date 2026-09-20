"""Post hoc localization of coordinate changes; never changes acceptance gates."""
import json
from pathlib import Path
import gemmi
import numpy as np
from analyse import aligned
from worker import atomic
OUT=Path(__file__).resolve().parents[2]/'output/apple_runtime_throughput_v2'

def main():
 rows=[]
 for p in sorted(OUT.glob('intellifold-*_smoke_*/analysis.json')):
  audit=json.loads(p.read_text())
  if not audit['complete'] or audit['errors']:continue
  for index,pair in enumerate(audit['pairs']):
   if pair['warmup']:continue
   arrays=[]
   for arm in ('baseline','candidate'):
    files={x.resolve() for x in (p.parent/arm/'attempt_001'/f'unit_{index:02d}'/'prediction').rglob('*.cif')}
    assert len(files)==1
    st=gemmi.read_structure(str(next(iter(files))))
    atoms=[res.find_atom('CA','*') for chain in st[0] for res in chain]
    arrays.append((np.asarray([[a.pos.x,a.pos.y,a.pos.z] for a in atoms]),np.asarray([a.b_iso for a in atoms])))
   (x,c),(y,d)=arrays;mask=(c>=70)&(d>=70)
   rows.append(dict(run=p.parent.name,case=pair['name'],all_ca_rmsd=aligned(x,y)[0],joint_plddt70_residues=int(mask.sum()),total_residues=len(x),joint_plddt70_ca_rmsd=aligned(x[mask],y[mask])[0] if mask.sum()>3 else None,original_gate_passed=pair['passed']))
 atomic(OUT/'coordinate_diagnostics.json',dict(purpose='Post hoc localization only. Joint pLDDT >=70 selection was not prespecified and cannot replace the original all-residue acceptance gate.',rows=rows))
if __name__=='__main__':main()
