"""Export compact, sequence-free acceptance evidence after all cases terminate."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
out=ROOT/'Validation/output/portable_workflow_launch_v1'
target=ROOT/'lab_book/artifacts/0199-workflow-launches'
rows=json.loads((out/'current-summary.json').read_text())
current=[r for r in rows if not r['superseded']]
assert len(current)==23
assert all(r['status'] not in ('queued','running') and r['audit_passed'] for r in current)
cases=[]
for row in current:
    plan=json.loads((out/row['case']/'plan.json').read_text())
    evidence={k:row[k] for k in ('case','job_id','status','scientific_rejection','audit_passed','structure_count')}
    evidence.update(plan_sha256=plan['sha256'],code_snapshot_sha256=plan.get('code_snapshot',{}).get('sha256'),
                    runtimes={k:v['manifest_sha256'] for k,v in plan.get('runtime_bindings',{}).items()})
    cases.append(evidence)
payload={'scope':'Integration launch acceptance on M4 Max 64 GiB / macOS 26.6.1; not design-quality or speed qualification',
         'cases':cases,
         'preserved_attempt_count':len(rows),
         'runtime_export_comparison':json.loads((out/'rfd3-export-comparison.json').read_text()),
         'biotin_existing_completion_receipts':10403,
         'not_tested':['fresh Mac without developer tools','other Apple chips','large inputs','long memory soak','all scientific input combinations']}
target.mkdir(parents=True,exist_ok=True)
(target/'launch-evidence.json').write_text(json.dumps(payload,indent=2)+'\n')
print('Exported',len(current),'audited case summaries')
