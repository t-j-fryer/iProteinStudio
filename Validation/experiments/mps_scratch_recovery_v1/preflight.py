"""Freeze old/published Boltz comparison and launch through the execution broker."""
import argparse,json,os,shutil,sys
from pathlib import Path
from datetime import datetime,timezone
here=Path(__file__).resolve().parent;repo=here.parents[2];root=Path.home()/'.iproteinstudio'
os.environ['NANOHUNTER_ROOT']=str(root);sys.path.insert(0,str(root/'mcp'))
from server import MCPServer
from iprotein_mcp.plans import _persist,_script_provenance
p=argparse.ArgumentParser();p.add_argument('--phase',required=True);p.add_argument('--repeats',type=int,default=1);a=p.parse_args()
s=MCPServer('run');guide=s.tool_call('workflow_guide',{'workflow':'prediction'})
active=[j['id'] for j in s.tool_call('jobs_list',{'limit':100})['jobs'] if j['status'] in ('running','queued','stopping')]
if active:raise RuntimeError('Active jobs: '+str(active))
out=repo/'Validation/output/mps_scratch_recovery_v1'/(a.phase+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));f=out/'frozen';f.mkdir(parents=True)
original=repo/'Validation/output/portable_runtimes_v1/relocation_20260920T160128Z/frozen'
for name in ('worker.py','boltz_worker.py','relocation_worker.py'):shutil.copy2(original/name,f/name)
shutil.copy2(here/'coordinator.py',f/'coordinator.py');shutil.copy2(here/'manifest.json',f/'manifest.json')
blocks=[];old=next(r for r in json.loads((original/'run.json').read_text())['blocks'] if r['engine']=='boltz' and r['arm']=='baseline')
for arm in ('previous','published'):
 for repeat in range(a.repeats):
  req=dict(old);req['arm']=arm+'-'+str(repeat);req['output']=str(out/req['arm'])
  if arm=='published':req['python']=str((root/'components/boltz/current').resolve()/'python/bin/python')
  req['cases']=old['cases']*(3 if a.phase=='after' else 1);blocks.append(req)
(f/'run.json').write_text(json.dumps(dict(output=str(out),blocks=blocks,timeout_seconds=120 if a.phase=='before' else 240),indent=2))
files=list(f.glob('*'))+[Path(r['python']).resolve() for r in blocks]
command=[sys.executable,'-B',str(f/'coordinator.py'),str(f/'run.json')]
plan=_persist('desktop_mps_scratch_recovery','portable-runtime-qualification',dict(workflow='mps-scratch-recovery',output=str(out),steps=[dict(stage='paired-'+a.phase,command=command,cwd=str(out))]),command,'apple_gpu_exclusive',_script_provenance(files))
(out/'plan.json').write_text(json.dumps(plan,indent=2));(out/'workflow_guide.json').write_text(json.dumps(guide,indent=2))
job=s.tool_call('job_start',dict(plan_id=plan['id'],plan_sha256=plan['sha256']));(out/'submitted.json').write_text(json.dumps(job,indent=2));print(json.dumps(dict(output=str(out),job=job)),flush=True)
