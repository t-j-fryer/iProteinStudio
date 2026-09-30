"""Derive MLX ESM native iteration counts from the pinned sampler coefficients."""
import json
from pathlib import Path
OUT=Path(__file__).resolve().parents[2]/'output/sumo_model_matrix_v1'
# The managed model configs are also preserved by the benchmark plan's asset view.
plan=json.loads((OUT/'plan.json').read_text());view=Path(plan['prepared_runtime_view']['path']);result={}
for tag,steps in [('ESMFold2',[100,13]),('ESMFold2-Fast',[50,6])]:
 c=json.loads((view/'models/esmfold2'/tag/'config.json').read_text())['structure_head'];p=c['inference_p'];hi=c['inference_s_max'];lo=c['inference_s_min'];sigma=c['diffusion_module']['sigma_data'];result[tag]={}
 for n in steps:
  schedule=[sigma*(hi**(1/p)+(k/(n-1))*(lo**(1/p)-hi**(1/p)))**p for k in range(n)]+[0.0]
  filtered=[256.0]+[s for s in schedule if s<=256.0]
  result[tag][str(n)]=dict(requested=n,derived_native_iterations=len(filtered)-1,sigmas=filtered,note='Source-derived schedule; not a GPU performance measurement')
(OUT/'analysis/esm_native_schedules.json').write_text(json.dumps(result,indent=2)+'\n')
