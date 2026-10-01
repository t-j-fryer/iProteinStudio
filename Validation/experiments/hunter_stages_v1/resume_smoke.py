import json, os, subprocess, sys, time, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'Validation/output/hunter_stages_v1'
subprocess.run([sys.executable,str(Path(__file__).with_name('preflight.py')),'boltz_full','--suffix=_resume','--start'],check=True)
os.environ['NANOHUNTER_ROOT']=str(OUT/'runtime')
os.environ['IPROTEINSTUDIO_AGENT_ROOT']=str(Path.home()/'.iproteinstudio/agent')
sys.path.insert(0,str(OUT/'runtime/mcp'))
from iprotein_mcp.broker import load_state,cancel_job,resume_job
job=json.loads((OUT/'boltz_full_resume.job.json').read_text())['id']
root=OUT/'runtime/projects/hunter-stages-acceptance/boltz_full_resume'
model=root/'run_001/cycle_01/pred_min/model_0.cif'
for _ in range(1200):
    state=load_state(job)
    if state['status'] in {'failed','cancelled','completed'}:raise RuntimeError('Test ended before interruption: '+str(state))
    if model.is_file():break
    time.sleep(1)
else:raise RuntimeError('No first refinement checkpoint within 20 minutes')
files=list((root/'run_001/cycle_00/pred_min').glob('model_0.*'))+[model]
before={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(OUT/'resume-before.json').write_text(json.dumps(before,indent=2))
print('ACCEPTANCE|interrupting after cycle 01',flush=True)
cancel_job(job)
for _ in range(90):
    state=load_state(job)
    if state['status'] in {'failed','cancelled'}:break
    time.sleep(1)
else:raise RuntimeError('Cancellation did not finish')
time.sleep(2)
print(json.dumps(resume_job(job)),flush=True)
for _ in range(1200):
    state=load_state(job)
    if state['status'] in {'failed','cancelled','completed'}:break
    time.sleep(1)
if state['status']!='completed':raise RuntimeError(str(state))
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in before.items())
(OUT/'resume-verification.json').write_text(json.dumps(dict(status='passed',job=job,preserved=before),indent=2))
print('ACCEPTANCE|resume passed; original start and cycle 01 unchanged',flush=True)
