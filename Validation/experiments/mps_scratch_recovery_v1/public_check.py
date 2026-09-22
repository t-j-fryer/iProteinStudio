"""Exercise the installed public prediction-plan/job-start path."""
import json,sys
from pathlib import Path
from datetime import datetime,timezone
repo=Path(__file__).resolve().parents[3];root=Path.home()/'.iproteinstudio'
sys.path.insert(0,str(root/'mcp'))
from server import MCPServer
s=MCPServer('run');guide=s.tool_call('workflow_guide',{'workflow':'prediction'});detected=s.tool_call('system_detect',{})
assert detected['engines']['boltz']['state']=='ok'
request=json.loads((repo/'Validation/output/portable_runtimes_v1/installed-public-prediction.json').read_text())['request']
out=repo/'Validation/output/mps_scratch_recovery_v1'/('public_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True)
plan=s.tool_call('prediction_plan',request);(out/'plan.json').write_text(json.dumps(plan,indent=2));(out/'guide.json').write_text(json.dumps(guide,indent=2))
job=s.tool_call('job_start',dict(plan_id=plan['id'],plan_sha256=plan['sha256']));(out/'submitted.json').write_text(json.dumps(job,indent=2));print(json.dumps(dict(output=str(out),job=job)),flush=True)
