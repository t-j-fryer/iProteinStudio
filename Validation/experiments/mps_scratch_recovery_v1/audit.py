"""Independent output fidelity audit, no inference or mutation of raw outputs."""
import argparse,json,sys
from pathlib import Path
here=Path(__file__).resolve().parent;repo=here.parents[2]
sys.path.insert(0,str(here.parent/'portable_runtimes_v1'))
from audit_relocation import extract,compare
p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
limits=json.loads((here.parent/'apple_runtime_throughput_v2/manifest.json').read_text())['acceptance']
reference=repo/'Validation/output/portable_runtimes_v1/relocation_20260920T160128Z/boltz-baseline/unit_00'
baseline=extract(reference,'boltz');cfg=json.loads((a.run/'frozen/run.json').read_text());rows=[]
for req in cfg['blocks']:
 out=Path(req['output']);assert (out/'completed.json').is_file(),str(out)
 for i in range(len(req['cases'])):
  result=compare(baseline,extract(out/f'unit_{i:02d}','boltz'),'boltz',limits)
  rows.append(dict(arm=req['arm'],unit=i,**result))
result=dict(passed=all(r['passed'] for r in rows),prediction_count=len(rows),reference=str(reference),rows=rows,performance_claim=False)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
raise SystemExit(0 if result['passed'] else 1)
