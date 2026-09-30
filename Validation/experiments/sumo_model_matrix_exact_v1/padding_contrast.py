"""Compare exact-sized outputs with preserved padded runs, seed by seed."""
import json,sys
from pathlib import Path
import numpy as np
from biotite.structure.io import pdbx
from quality import align
OUT=Path(__file__).resolve().parents[2]/'output/sumo_model_matrix_exact_v1';OLD=OUT.parent/'sumo_model_matrix_v1'
new=json.loads((OUT/'analysis/results.json').read_text());pairs=[]
for r in new['rows']:
 if r['diagnostic'] or r['engine'] not in ('intellifold_full','intellifold_flash'):continue
 p=OLD/r['engine']/Path(r['measurement']).parent.name/'measurement.json'
 if not p.exists():continue
 old=json.loads(p.read_text());a=pdbx.get_structure(pdbx.CIFFile.read(old['structure']),model=1);b=pdbx.get_structure(pdbx.CIFFile.read(r['structure']),model=1)
 a=a[a.atom_name=='CA'];b=b[b.atom_name=='CA'];assert np.array_equal(a.res_name,b.res_name)
 pair={k:r[k] for k in ('engine','msa','budget','seed')}
 pair.update(warm=not old['first_model_request'] and not r['first_model_request'],old_request_seconds=old['request_seconds'],new_request_seconds=r['request_seconds'],old_model_seconds=old['stages']['model_total']['seconds'],new_model_seconds=r['model_seconds'],core_ca_change_rmsd=align(a.coord[20:],b.coord[20:]),whole_ca_change_rmsd=align(a.coord,b.coord),old_measurement=str(p),new_measurement=r['measurement'])
 pairs.append(pair)
summary=[]
for engine,msa,budget in sorted({(r['engine'],r['msa'],r['budget']) for r in pairs}):
 rows=[r for r in pairs if (r['engine'],r['msa'],r['budget'])==(engine,msa,budget)];warm=[r for r in rows if r['warm']]
 summary.append(dict(engine=engine,msa=msa,budget=budget,paired_n=len(rows),warm_paired_n=len(warm),old_request_median=float(np.median([r['old_request_seconds'] for r in warm])) if warm else None,new_request_median=float(np.median([r['new_request_seconds'] for r in warm])) if warm else None,max_core_change_rmsd=max(r['core_ca_change_rmsd'] for r in rows)))
(OUT/'analysis/padding_contrasts.json').write_text(json.dumps(dict(pairs=pairs,summaries=summary,limitation='Controls are preserved earlier runs, not randomized contemporaneous pairs; padded Full was cancelled, so some conditions lack controls.'),indent=2)+'\n')
print('Padding comparisons:',len(pairs))
