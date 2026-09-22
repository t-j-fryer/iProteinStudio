import csv,json,os,shutil,sys
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2];managed=Path.home()/'.iproteinstudio'
os.environ['NANOHUNTER_ROOT']=str(managed);sys.path.insert(0,str(managed/'mcp'))
from server import MCPServer
from iprotein_mcp.plans import _persist,_script_provenance
server=MCPServer('run');guide=server.tool_call('workflow_guide',{'workflow':'nise'})
out=REPO/'Validation/output/portable_runtimes_v1'/('psichic_smoke_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));f=out/'frozen';f.mkdir(parents=True)
for p in HERE.glob('*'):
 if p.suffix in ('.py','.json'):shutil.copy2(p,f/p.name)
scripts=f/'scripts';shutil.copytree(REPO/'Sources/iProteinStudio/Resources/pipeline/scripts',scripts,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
reference=REPO/'Validation/output/psichic_mps_v1/validate_20260920T032848Z/cpu_upstream_pass0.csv';shutil.copy2(reference,f/'reference.csv')
rows=list(csv.DictReader(reference.open()));print('reference columns',list(rows[0]),flush=True)
with (f/'inputs.csv').open('w') as stream:
 w=csv.DictWriter(stream,fieldnames=['Protein','Ligand']);w.writeheader();w.writerows({k:r[k] for k in w.fieldnames} for r in rows)
root=managed if '--installed' in sys.argv else REPO/'Validation/output/portable_runtimes_v1/installed';base=(root/'components/psichic/current').resolve();py=base/'python/bin/python3'
cfg=dict(output=str(out),root=str(root),scripts=str(scripts),inputs=str(f/'inputs.csv'),reference=str(f/'reference.csv'),private_cache='--private-cache' in sys.argv,private_tmp='--private-tmp' in sys.argv,trace_cache=str(REPO/'Validation/output/portable_runtimes_v1/trace_mkdir.dylib') if '--trace-cache' in sys.argv else None)
if cfg['trace_cache']:
 shutil.copy2(cfg['trace_cache'],f/'trace_mkdir.dylib');cfg['trace_cache']=str(f/'trace_mkdir.dylib')
(f/'config.json').write_text(json.dumps(cfg,indent=2))
(out/'workflow_guide.json').write_text(json.dumps(guide,indent=2))
files=[p for p in f.rglob('*') if p.is_file()]+[base/'runtime.json']+[p for p in (root/'models/psichic').rglob('*') if p.is_file()]
manifest=json.loads((base/'runtime.json').read_text());files += [base/p for p,v in manifest['files'].items() if 'sha256' in v]
command=['/usr/bin/caffeinate','-dimsu',str(py),'-B',str(f/'psichic_smoke.py'),str(f/'config.json')]
plan=_persist('desktop_psichic_portable_validation','psichic-portable-validation',dict(workflow='psichic-portable-validation',output=str(out),steps=[dict(stage='psichic-smoke',command=command,cwd=str(out))]),command,'apple_gpu_exclusive',_script_provenance(files))
(out/'plan.json').write_text(json.dumps(plan,indent=2));print(json.dumps(dict(output=str(out),plan_id=plan['id'],sha256=plan['sha256'])),flush=True)
result=server.tool_call('job_start',{'plan_id':plan['id'],'plan_sha256':plan['sha256']});(out/'submitted.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
