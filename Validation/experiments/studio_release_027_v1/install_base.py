"""Run the shipped base installer in a new root with developer tools unavailable.

No inference. Public runtimes and separately verified model assets download via
normal installer paths. Existing user engines/projects are never touched.
"""
import argparse,json,os,shutil,subprocess
from pathlib import Path
REPO=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
root=out/'empty base Ω'
shutil.copytree(REPO/'Sources/iProteinStudio/Resources/pipeline',root,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
guards=out/'blocked-tools';guards.mkdir();guardlog=out/'developer-tools.log'
for name in ('git','pip','pip3','brew','xcodebuild','xcrun','python','python3'):
    file=guards/name
    file.write_text('#!/bin/sh\nprintf "%s\\n" "'+name+'" >> "$STUDIO_RELEASE_GUARD_LOG"\nexit 97\n')
    file.chmod(0o755)
env={**os.environ,'PATH':str(guards)+':/usr/bin:/bin:/usr/sbin:/sbin',
     'NANOHUNTER_ROOT':str(root),'HF_HOME':str(root/'cache/hf'),
     'STUDIO_RELEASE_GUARD_LOG':str(guardlog),'PYTHONDONTWRITEBYTECODE':'1'}
for key in ('PYTHONPATH','PYTHONHOME','IPROTEINSTUDIO_BUILD_FROM_SOURCE','IPROTEINSTUDIO_LOCAL_PACKAGES'):
    env.pop(key,None)
with (out/'install.log').open('w') as log:
    result=subprocess.run(['/bin/bash',str(root/'setup_pipeline.sh'),'--base'],env=env,stdout=log,stderr=subprocess.STDOUT)
with (out/'detect.log').open('w') as log:
    detect=subprocess.run(['/bin/bash',str(root/'setup_pipeline.sh'),'--detect'],env=env,stdout=log,stderr=subprocess.STDOUT)
required=('control','mpnn','esmfold2','esmfold2_full','abmpnn','boltz','boltz_affinity','rfd4','lasermpnn')
receipts={key:json.loads((root/'receipts'/f'{key}.json').read_text()) if (root/'receipts'/f'{key}.json').exists() else None for key in required}
report=dict(exit_code=result.returncode,detect_exit_code=detect.returncode,root=str(root),
            developer_tools_called=guardlog.read_text().splitlines() if guardlog.exists() else [],receipts=receipts,
            model_assets_preseeded=False,platform_scope='isolated root on development Mac; not a second machine')
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
assert result.returncode==0 and detect.returncode==0, 'Installer/detector failed; inspect retained logs'
assert not report['developer_tools_called'], 'Installer unexpectedly invoked developer tooling'
assert all(v and v['complete'] for v in receipts.values()), 'Base component receipt missing'
print(json.dumps({'passed':True,'root':str(root),'components':list(required)}))
