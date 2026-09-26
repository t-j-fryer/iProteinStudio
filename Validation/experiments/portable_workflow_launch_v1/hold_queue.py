"""Temporarily hold only this acceptance campaign's queued jobs for safe staging."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];out=ROOT/'Validation/output/portable_workflow_launch_v1';managed=Path.home()/'.iproteinstudio'
os.environ['NANOHUNTER_ROOT']=str(managed);sys.path.insert(0,str(managed/'mcp'))
from server import MCPServer
server=MCPServer('run');records=[]
for p in sorted(out.glob('*/job.json')):
    j=json.loads(p.read_text());s=server.tool_call('job_status',{'job_id':j['id']})
    if s['status']=='queued':
        result=server.tool_call('job_cancel',{'job_id':j['id']});records.append({'case':p.parent.name,'id':j['id'],'before':s,'cancel':result})
(out/'queue-hold.json').write_text(json.dumps(records,indent=2)+'\n');print(json.dumps([{'case':r['case'],'id':r['id']} for r in records]),flush=True)
