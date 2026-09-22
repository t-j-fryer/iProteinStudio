"""Migrate the current Mac through the final installer under the managed lease."""
import json,os,shutil,sys
from pathlib import Path
from datetime import datetime,timezone
REPO=Path(__file__).resolve().parents[3];OUT=REPO/'Validation/output/portable_runtimes_v1';root=Path.home()/'.iproteinstudio';os.environ['NANOHUNTER_ROOT']=str(root)
sys.path.insert(0,str(root/'mcp'))
from server import MCPServer
from iprotein_mcp.plans import _persist,_script_provenance
s=MCPServer('run');guide=s.tool_call('workflow_guide',{'workflow':'prediction'})
out=OUT/('installation_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));f=out/'frozen';f.mkdir(parents=True)
shutil.copytree(REPO/'Sources/iProteinStudio/Resources/pipeline/scripts',f/'scripts',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
components='control,mpnn,abmpnn,lasermpnn,antifold,boltz,boltz_affinity,intellifold,intellifold_full,protenix,protenix_v2,protenix_mini,protenix_constraint,openfold3,rfd3,nesso,psichic'
command=[sys.executable,str(f/'scripts/setup_portable.py'),'--root',str(root),'--components',components,'--local-packages',str(OUT)]
files=[p for p in f.rglob('*') if p.is_file()]+[Path(r['package'])/'runtime.json' for r in json.loads((OUT/'publication-assets.json').read_text())]
plan=_persist('desktop_portable_install','portable-runtime-qualification',dict(workflow='portable-install',output=str(out),steps=[dict(stage='install-portable',command=command,cwd=str(out))]),command,'environment_install',_script_provenance(files))
(out/'plan.json').write_text(json.dumps(plan,indent=2));(out/'workflow_guide.json').write_text(json.dumps(guide));job=s.tool_call('job_start',{'plan_id':plan['id'],'plan_sha256':plan['sha256']});(out/'submitted.json').write_text(json.dumps(job,indent=2));print(json.dumps(dict(output=str(out),job=job)),flush=True)
