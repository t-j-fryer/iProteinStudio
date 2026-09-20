"""One deliberate cancellation/resume of this experiment's cache soak only."""
import json,os,sys,time
from pathlib import Path
from worker import atomic,sha
repo=Path(__file__).resolve().parents[3]
out=repo/'Validation/output/apple_runtime_kernels_v3'
run=next(out.glob('nesso_soak_*/submitted.json')).parent
os.environ['NANOHUNTER_ROOT']=str(Path.home()/'.iproteinstudio')
sys.path.insert(0,str(repo/'Sources/iProteinStudio/Resources/pipeline/mcp'))
from server import MCPServer
server=MCPServer('run');job=json.loads((run/'submitted.json').read_text())['id']
deadline=time.monotonic()+1800
while time.monotonic()<deadline:
    status=server.tool_call('job_status',{'job_id':job})
    progress=json.loads((run/'progress.json').read_text()) if (run/'progress.json').exists() else {}
    if 'variant' in progress and list(run.glob('reference/attempt_*/unit_00')) and 'reference' not in progress:
        receipt=Path(progress['variant'])/'completed.json';before=sha(receipt)
        cancelled=server.tool_call('job_cancel',{'job_id':job})
        atomic(run/'recovery_cancel.json',dict(status=cancelled,completed_variant_sha256=before))
        for _ in range(60):
            status=server.tool_call('job_status',{'job_id':job})
            if status['status'] in ('cancelled','failed'):break
            time.sleep(1)
        if status['status'] not in ('cancelled','failed'):raise RuntimeError('Cancellation did not reach terminal state')
        resumed=server.tool_call('job_resume',{'job_id':job})
        if sha(receipt)!=before:raise RuntimeError('Completed reference changed during resume')
        atomic(run/'recovery_resume.json',dict(status=resumed,completed_variant_sha256=before))
        print(json.dumps(resumed),flush=True);break
    if status['status'] in ('completed','failed','cancelled'):
        raise RuntimeError('Soak ended before intended recovery boundary: '+str(status))
    time.sleep(2)
else:raise RuntimeError('Recovery observation timed out')
