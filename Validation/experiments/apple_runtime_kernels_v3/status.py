import json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'Sources/iProteinStudio/Resources/pipeline/mcp'));os.environ['NANOHUNTER_ROOT']=str(Path.home()/'.iproteinstudio')
from server import MCPServer
s=MCPServer('run')
for p in sorted((root/'Validation/output/apple_runtime_kernels_v3').glob('*/submitted.json')):
 j=json.loads(p.read_text());r=s.tool_call('job_status',{'job_id':j['id']});row={k:r.get(k) for k in ('id','status','message')};row['run']=p.parent.name
 units=list(p.parent.glob('*/attempt_*/unit_*/measurement.json'));row['units']=len(units)
 if r.get('status') in ('failed','error'):row['tail']=r.get('pipeline_log_tail',[])[-2:]
 if r.get('status') not in ('completed','failed') or '--all' in sys.argv:print(json.dumps(row))
