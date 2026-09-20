"""Exercise deployed managed launchers via public prediction_plan/job_start."""
import json,os,sys
from pathlib import Path
from worker import atomic
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2]
OUT=REPO/'Validation/output/apple_runtime_release_v4';managed=Path.home()/'.iproteinstudio'
os.environ['NANOHUNTER_ROOT']=str(managed)
sys.path.insert(0,str(managed/'mcp'))
from server import MCPServer
from iprotein_mcp.common import project_root
project_root('runtime214-release-smoke',create=True)
s=MCPServer('run');atomic(OUT/'installed_workflow_guide.json',s.tool_call('workflow_guide',{'workflow':'prediction'}))
seq=json.loads((HERE.parent/'apple_runtime_throughput_v1/manifest.json').read_text())['cases'][1]['sequence']
msa=str(managed/'msa_cache/00e99841616c44295043375bc0ba6286.a3m')
submitted=[]
for engine,model in [('boltz',None),('intellifold','v2-flash'),('intellifold','v2')]:
 request=dict(predictors=[engine],jobs=[dict(name='sumo',chains=[dict(id='A',kind='protein',sequence=seq,msa=msa)])],num_seeds=1,diffusion_samples=1,max_parallel=1,offline_only=True,use_potentials=engine=='boltz')
 if model:request['intellifold_model']=model
 plan=s.tool_call('prediction_plan',dict(project='runtime214-release-smoke',request=request))
 name=engine+'-'+str(model);atomic(OUT/(name+'.installed-plan.json'),plan)
 job=s.tool_call('job_start',{'plan_id':plan['id'],'plan_sha256':plan['sha256']});submitted.append(dict(engine=engine,model=model,job=job));atomic(OUT/'installed_smoke_jobs.json',submitted)
 print(json.dumps(submitted[-1]),flush=True)
