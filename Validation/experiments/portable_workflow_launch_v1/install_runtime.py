"""Exercise the public administrator installer after scientific jobs are idle."""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'Validation/output/portable_workflow_launch_v1'
managed = Path.home()/'.iproteinstudio'
os.environ['NANOHUNTER_ROOT'] = str(managed)
os.environ['IPROTEINSTUDIO_ENABLE_ADMIN_MCP'] = '1'
sys.dont_write_bytecode = True
sys.path.insert(0, str(managed/'mcp'))
from server import MCPServer

server = MCPServer('admin')
plan_path = OUT/'engine-install-plan.json'
job_path = OUT/'engine-install-job.json'
if plan_path.exists():
    plan = json.loads(plan_path.read_text())
else:
    plan = server.tool_call('engine_install_plan', {'components':['rfd3','protenix-constraint']})
    plan_path.write_text(json.dumps(plan, indent=2)+'\n')
if job_path.exists():
    job = server.tool_call('job_status', {'job_id':json.loads(job_path.read_text())['id']})
else:
    job = server.tool_call('job_start', {'plan_id':plan['id'], 'plan_sha256':plan['sha256']})
    job_path.write_text(json.dumps(job, indent=2)+'\n')
(OUT/'engine-install-latest.json').write_text(json.dumps(job, indent=2)+'\n')
print(json.dumps({k:job.get(k) for k in ('id','status','stage','message','error')}))
