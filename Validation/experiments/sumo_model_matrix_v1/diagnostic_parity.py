"""Check whether added timing barriers changed the seed42 saved coordinates."""
import json
from pathlib import Path
import numpy as np
from biotite.structure.io import pdbx
OUT=Path(__file__).resolve().parents[2]/'output/sumo_model_matrix_v1';d=json.loads((OUT/'analysis/results.json').read_text());result=[]
for diagnostic in [r for r in d['rows'] if r['diagnostic']]:
 matches=[r for r in d['rows'] if not r['diagnostic'] and all(r[k]==diagnostic[k] for k in ('engine','msa','budget','seed'))]
 if len(matches)!=1:continue
 a=pdbx.get_structure(pdbx.CIFFile.read(matches[0]['structure']),model=1);b=pdbx.get_structure(pdbx.CIFFile.read(diagnostic['structure']),model=1)
 identity=all(np.array_equal(getattr(a,k),getattr(b,k)) for k in ('chain_id','res_id','res_name','atom_name'))
 r={k:diagnostic[k] for k in ('engine','msa','budget','seed')};r['atom_identity_equal']=identity
 if identity:r.update(exact_saved_coordinates=bool(np.array_equal(a.coord,b.coord)),maximum_coordinate_difference=float(np.max(np.abs(a.coord-b.coord))),coordinate_rms_difference=float(np.sqrt(np.mean(np.sum((a.coord-b.coord)**2,axis=1)))))
 result.append(r)
(OUT/'analysis/diagnostic_parity.json').write_text(json.dumps(result,indent=2)+'\n')
print('Profile coordinate repeats:',len(result),'exact:',sum(r.get('exact_saved_coordinates',False) for r in result))
