"""Resume the exact production plan only after verifying preserved checkpoints."""
import datetime,hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];out=ROOT/'Validation/output/portable_workflow_launch_v1';managed=Path.home()/'.iproteinstudio'
os.environ['NANOHUNTER_ROOT']=str(managed);sys.path.insert(0,str(managed/'mcp'))
from server import MCPServer
server=MCPServer('run');job_id='job-221c7d6db092';before=server.tool_call('job_status',{'job_id':job_id})
assert before['status']=='cancelled',before['status']
assert before['plan_id']=='plan-221c7d6db0924d4b'
assert before['plan_sha256']=='221c7d6db0924d4b26c662e3fd386bac3daaec211e3dc5d9c4a41426ef8e115a'
root=Path(before['output_root']);saved=json.loads((out/'biotin-stopped-checkpoints.json').read_text())['receipts']
changed=[name for name,h in saved.items() if not (root/name).is_file() or hashlib.sha256((root/name).read_bytes()).hexdigest()!=h]
assert not changed,changed
log=managed/'agent/jobs'/job_id/'pipeline.log'
receipt={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'unchanged_prior_receipts':len(saved),'pipeline_log_bytes_before':log.stat().st_size,'before':before}
receipt['resume']=server.tool_call('job_resume',{'job_id':job_id})
(out/'biotin-resumed.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:receipt['resume'].get(k) for k in ('id','status','plan_id','message')}),flush=True)
