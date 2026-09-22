"""Install repaired data closure in isolation and compare actual CPU inference."""
import json,os,shutil,sys
from datetime import datetime,timezone
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent;OUT=REPO/'Validation/output/portable_runtimes_v1';root=Path.home()/'.iproteinstudio'
os.environ['NANOHUNTER_ROOT']=str(root);sys.path.insert(0,str(REPO/'Sources/iProteinStudio/Resources/pipeline/mcp'))
from server import MCPServer
from iprotein_mcp.plans import _persist,_script_provenance
server=MCPServer('run');guide=server.tool_call('workflow_guide',{'workflow':'prediction'})
out=OUT/('lasermpnn_final_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));f=out/'frozen';f.mkdir(parents=True)
shutil.copytree(REPO/'Sources/iProteinStudio/Resources/pipeline/scripts',f/'scripts',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copy2(HERE/'sequence_smoke.py',f/'sequence_smoke.py');shutil.copy2(HERE/'lasermpnn_final_worker.py',f/'worker.py')
shutil.copy2(OUT/'relocation_20260920T160128Z/frozen/fixtures/fluorescein.pdb',f/'fixture.pdb')
cfg=dict(output=str(out),root=str(root),candidate=str(OUT/'qualification_root'),package=str(OUT/'lasermpnn-release-final3'));(f/'request.json').write_text(json.dumps(cfg))
command=[sys.executable,str(f/'worker.py'),str(f/'request.json')]
files=[p for p in f.rglob('*') if p.is_file()]+[Path(cfg['package'])/'runtime.json']
plan=_persist('desktop_lasermpnn_final','portable-runtime-qualification',dict(workflow='portable-relocation',output=str(out),steps=[dict(stage='lasermpnn-final',command=command,cwd=str(out))]),command,'apple_gpu_exclusive',_script_provenance(files))
(out/'workflow_guide.json').write_text(json.dumps(guide));(out/'plan.json').write_text(json.dumps(plan));job=server.tool_call('job_start',{'plan_id':plan['id'],'plan_sha256':plan['sha256']});print(json.dumps(dict(output=str(out),job=job)),flush=True)
