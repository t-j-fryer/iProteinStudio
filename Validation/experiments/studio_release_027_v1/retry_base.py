"""Retry a failed isolated base install with current bundled files; retain old evidence."""
import argparse, hashlib, json, os, shutil, subprocess
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
p = argparse.ArgumentParser()
p.add_argument('--installation', type=Path, required=True)
p.add_argument('--attempt', required=True)
a = p.parse_args()
installation = a.installation.resolve()
original = json.loads((installation / 'result.json').read_text())
assert original['exit_code'] != 0, 'Only resume a recorded failed installation'
root = Path(original['root'])
assert root.parent == installation and root.name == 'empty base Ω'
out = installation / a.attempt
out.mkdir(exist_ok=False)
source = REPO / 'Sources/iProteinStudio/Resources/pipeline'
files = [f for f in source.rglob('*') if f.is_file() and '__pycache__' not in f.parts and f.suffix != '.pyc']
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
changes = {str(f.relative_to(source)): {'before': digest(root / f.relative_to(source)) if (root / f.relative_to(source)).is_file() else None, 'after': digest(f)} for f in files}
(out / 'bundled-source.json').write_text(json.dumps(changes, indent=2) + '\n')
shutil.copytree(source, root, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
guardlog = installation / 'developer-tools.log'
env = {**os.environ, 'PATH': str(installation / 'blocked-tools') + ':/usr/bin:/bin:/usr/sbin:/sbin',
       'NANOHUNTER_ROOT': str(root), 'HF_HOME': str(root / 'cache/hf'),
       'STUDIO_RELEASE_GUARD_LOG': str(guardlog), 'PYTHONDONTWRITEBYTECODE': '1'}
for key in ('PYTHONPATH','PYTHONHOME','IPROTEINSTUDIO_BUILD_FROM_SOURCE','IPROTEINSTUDIO_LOCAL_PACKAGES'): env.pop(key,None)
with (out / 'install.log').open('w') as log:
    result = subprocess.run(['/bin/bash',str(root / 'setup_pipeline.sh'),'--base'],env=env,stdout=log,stderr=subprocess.STDOUT)
with (out / 'detect.log').open('w') as log:
    detect = subprocess.run(['/bin/bash',str(root / 'setup_pipeline.sh'),'--detect'],env=env,stdout=log,stderr=subprocess.STDOUT)
required = ('control','mpnn','esmfold2','esmfold2_full','abmpnn','boltz','boltz_affinity','rfd4','lasermpnn')
receipts = {key: json.loads((root / 'receipts' / (key + '.json')).read_text()) if (root / 'receipts' / (key + '.json')).exists() else None for key in required}
report = dict(exit_code=result.returncode,detect_exit_code=detect.returncode,root=str(root),
              developer_tools_called=guardlog.read_text().splitlines() if guardlog.exists() else [],receipts=receipts,
              model_assets_preseeded=False,platform_scope='isolated root on development Mac; not a second machine',
              resumed_from=str(installation / 'result.json'))
(out / 'result.json').write_text(json.dumps(report,indent=2)+'\n')
assert result.returncode == detect.returncode == 0, 'Inspect retained install/detect logs'
assert not report['developer_tools_called']
assert all(value and value['complete'] for value in receipts.values())
print(json.dumps({'passed':True,'components':list(required),'result':str(out / 'result.json')}))
