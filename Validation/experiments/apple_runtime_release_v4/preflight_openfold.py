import json,os,shutil,sys,subprocess
from pathlib import Path
from datetime import datetime,timezone
from worker import atomic,sha
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2];V2=REPO/'Validation/output/apple_runtime_throughput_v2';OUT=REPO/'Validation/output/apple_runtime_release_v4'
managed=Path.home()/'.iproteinstudio';os.environ['NANOHUNTER_ROOT']=str(managed)
sys.path.insert(0,str(REPO/'Sources/iProteinStudio/Resources/pipeline/mcp'))
from server import MCPServer
from iprotein_mcp.plans import _persist,_script_provenance
s=MCPServer('run');guide=s.tool_call('workflow_guide',{'workflow':'prediction'})
out=OUT/('openfold_msa_init_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir();f=out/'frozen';f.mkdir()
for p in HERE.iterdir():
 if p.suffix in ('.py','.json'):shutil.copy2(p,f/p.name)
msa=f/'colabfold_main.a3m';shutil.copy2(managed/'msa_cache/00e99841616c44295043375bc0ba6286.a3m',msa)
case=json.loads((REPO/'Validation/experiments/apple_runtime_throughput_v1/manifest.json').read_text())['cases'][1]
assert msa.read_text().splitlines()[1]==case['sequence']
case.update(msa=str(msa),msa_sha256=sha(msa))
shutil.copy2(V2/'openfold-baseline.seal.json',f/'baseline.seal.json');shutil.copy2(V2/'openfold.source.json',f/'source.seal.json')
root=V2/'roots/openfold';blocks=[dict(id=key,runtime='baseline',torch_version='2.6.0',variant=var,engine='openfold',seed=42,threads=4,cases=[dict(**case,warmup=True),dict(**case,warmup=False)]) for key,var in [('variant','checkpoint_init'),('reference',None)]]
cfg=dict(output=str(out),root=str(root),scripts=str(root/'scripts'),managed_root=str(managed),seals={'baseline':str(f/'baseline.seal.json')},source_seal=str(f/'source.seal.json'),blocks=blocks)
atomic(f/'run.json',cfg);atomic(out/'workflow_guide.json',guide)
assets=[managed/'models/openfold3/of3_ft3_v1.pt'];cmd=['/usr/bin/caffeinate','-dimsu',sys.executable,str(f/'coordinator.py'),'--manifest',str(f/'run.json')]
plan=_persist('desktop_runtime_benchmark','validation-runtime-benchmark',dict(workflow='runtime_benchmark',output=str(out),scheduler='serial under shared GPU lease',steps=[dict(stage='runtime-benchmark',command=cmd,cwd=str(out))]),cmd,'apple_gpu_exclusive',_script_provenance([p for p in f.iterdir() if p.is_file()]+assets+[Path(sys.executable).resolve()]))
atomic(out/'plan.json',plan);job=s.tool_call('job_start',{'plan_id':plan['id'],'plan_sha256':plan['sha256']});atomic(out/'submitted.json',job);print(json.dumps(dict(output=str(out),job=job)))
