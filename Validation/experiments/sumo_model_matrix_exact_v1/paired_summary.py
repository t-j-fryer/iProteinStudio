"""Pair seed-matched full/reduced measurements; no equivalence significance claim."""
import json
from pathlib import Path
import numpy as np
OUT=Path(__file__).resolve().parents[2]/'output/sumo_model_matrix_exact_v1'
d=json.loads((OUT/'analysis/results.json').read_text());rows=[r for r in d['rows'] if not r['diagnostic']];groups=[]
for engine in dict.fromkeys(r['engine'] for r in rows):
 for msa in ('none','128','full'):
  full={r['seed']:r for r in rows if (r['engine'],r['msa'],r['budget'])==(engine,msa,'full')};reduced={r['seed']:r for r in rows if (r['engine'],r['msa'],r['budget'])==(engine,msa,'reduced')}
  seeds=sorted(full.keys()&reduced.keys())
  if len(seeds)!=5:continue
  warm=[s for s in seeds if not full[s]['first_model_request'] and not reduced[s]['first_model_request']]
  groups.append(dict(engine=engine,msa=msa,seeds=seeds,warm_pair_count=len(warm),median_paired_model_speed_ratio=float(np.median([full[s]['model_seconds']/reduced[s]['model_seconds'] for s in warm])),median_paired_request_speed_ratio=float(np.median([full[s]['request_seconds']/reduced[s]['request_seconds'] for s in warm])),median_core_rmsd_change=float(np.median([reduced[s]['crystal_core_rmsd']-full[s]['crystal_core_rmsd'] for s in seeds])),median_core_lddt_change=float(np.median([reduced[s]['core_ca_lddt']-full[s]['core_ca_lddt'] for s in seeds])),reduced_whole_geometry_flagged=sum(reduced[s]['ca_neighbor_violations']>0 or reduced[s]['geometry_violations']>0 for s in seeds),reduced_core_geometry_flagged=sum(reduced[s]['core_ca_neighbor_violations']>0 or reduced[s]['core_geometry_violations']>0 for s in seeds)))
(OUT/'analysis/paired_contrasts.json').write_text(json.dumps(groups,indent=2)+'\n')
print(json.dumps(groups,indent=2))
