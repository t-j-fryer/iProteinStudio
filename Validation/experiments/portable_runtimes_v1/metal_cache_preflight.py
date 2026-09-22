import json,os,shutil,sys
from pathlib import Path
from datetime import datetime,timezone
repo=Path(__file__).resolve().parents[3];root=Path.home()/'.iproteinstudio';os.environ['NANOHUNTER_ROOT']=str(root);sys.path.insert(0,str(repo/'Sources/iProteinStudio/Resources/pipeline/mcp'))
from server import MCPServer
from iprotein_mcp.plans import _persist,_script_provenance
s=MCPServer('run');s.tool_call('workflow_guide',{'workflow':'prediction'});out=repo/'Validation/output/portable_runtimes_v1'/('metal_cache_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));f=out/'frozen';f.mkdir(parents=True)
shutil.copy2(Path(__file__).with_name('metal_cache_probe.py'),f/'probe.py');(f/'request.json').write_text(json.dumps(dict(output=str(out),python=str(root/'venvs/NanoHunter_boltz/bin/python'))))
command=[sys.executable,str(f/'probe.py'),str(f/'request.json')];p=_persist('desktop_metal_cache_probe','portable-runtime-qualification',dict(workflow='native-cache-diagnostic',output=str(out),steps=[dict(stage='metal-cache',command=command,cwd=str(out))]),command,'apple_gpu_exclusive',_script_provenance([f/'probe.py',f/'request.json']))
(out/'plan.json').write_text(json.dumps(p));j=s.tool_call('job_start',dict(plan_id=p['id'],plan_sha256=p['sha256']));print(json.dumps(dict(output=str(out),job=j)),flush=True)
