"""Real public downloads into an empty root on this Mac; not a fresh-Mac test."""
import json,os,shutil,subprocess
from datetime import datetime,timezone
from pathlib import Path
repo=Path(__file__).resolve().parents[3];out=repo/'Validation/output/portable_runtimes_v1'/('github_install_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));root=out/'empty root Ω';out.mkdir(parents=True)
shutil.copytree(repo/'Sources/iProteinStudio/Resources/pipeline',root,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
blocked=out/'blocked-tools';blocked.mkdir();calls=out/'developer-tool-calls.log'
for name in ('xcode-select','xcrun','clang','clang++','gcc','g++','git','make','cmake','python3'):
 p=blocked/name;p.write_text('#!/bin/sh\necho "'+name+' invoked" >> "'+str(calls)+'"\nexit 97\n');p.chmod(0o755)
env={**os.environ,'NANOHUNTER_ROOT':str(root),'PATH':str(blocked)+':/usr/bin:/bin:/usr/sbin:/sbin','KMP_USE_SHM':'0'}
with (out/'install.log').open('w') as log:r=subprocess.run(['/bin/bash',str(root/'setup_pipeline.sh'),'--retry-components','control,mpnn'],env=env,stdout=log,stderr=subprocess.STDOUT)
record=dict(root=str(root),returncode=r.returncode,developer_tools_called=calls.read_text().splitlines() if calls.exists() else [],fresh_mac=False)
(out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(dict(output=str(out),**record)),flush=True)
raise SystemExit(r.returncode or bool(record['developer_tools_called']))
