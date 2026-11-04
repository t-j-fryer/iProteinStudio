"""Submit T4 prediction checks via the existing source-qualified Studio view."""
import json,os,subprocess,sys
from pathlib import Path
out=Path(sys.argv[1]).resolve();prep=json.loads((out/'preparation.json').read_text())
root=Path(os.environ.get('NANOHUNTER_ROOT',Path.home()/'.iproteinstudio'))
cli=Path(prep['code_snapshot']['path'])/'mcp/studioctl.py'
python=root/'components/control/current/python/bin/python3'
env=dict(os.environ,NANOHUNTER_ROOT=str(out/'runtime'),IPROTEINSTUDIO_AGENT_ROOT=str(root/'agent'),PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
inputs=root/'projects/studio-release-032-v2/inputs'
sequence=''.join(s.strip() for s in (inputs/'target.fasta').read_text().splitlines() if not s.startswith('>'));assert len(sequence)==164
jobs=json.loads((out/'prediction_jobs.json').read_text()) if (out/'prediction_jobs.json').exists() else []
for enabled in [False,True]:
 name='t4-template-on' if enabled else 't4-template-off'
 if any(j['name']==name for j in jobs):continue
 folder=out/name;folder.mkdir(exist_ok=True)
 request=dict(predictors=['boltz'],offline_only=True,num_seeds=1,diffusion_samples=1,jobs=[dict(name=name,chains=[dict(id='A',kind='protein',sequence=sequence,msa='empty')])])
 if enabled:request['template']=dict(path=str(inputs/'2LZM.cif'),chains=['A'],mode='guide')
 payload=dict(project='studio-release-032-v2',request=request,memory_policy='override')
 path=folder/'request.json';path.write_text(json.dumps(payload,indent=2)+'\n')
 for action,args in [('plan',['plan-prediction',str(path)])]:
  run=subprocess.run([str(python),'-B',str(cli),*args],env=env,capture_output=True,text=True)
  (folder/(action+'.log')).write_text(run.stdout+run.stderr);run.check_returncode();plan=json.loads(run.stdout);(folder/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
 assert plan['command_preview'][:2]==['/usr/bin/caffeinate','-dimsu'] and plan['resource_class']=='apple_gpu_exclusive'
 run=subprocess.run([str(python),'-B',str(cli),'start',plan['id'],plan['sha256']],env=env,capture_output=True,text=True)
 (folder/'start.log').write_text(run.stdout+run.stderr);run.check_returncode();job=json.loads(run.stdout);(folder/'job.json').write_text(json.dumps(job,indent=2)+'\n')
 jobs.append(dict(name=name,plan_id=plan['id'],job_id=job['id'],sha256=plan['sha256'],output=plan['normalized_request']['output']))
 (out/'prediction_jobs.json').write_text(json.dumps(jobs,indent=2)+'\n');print(name,job['id'],flush=True)
