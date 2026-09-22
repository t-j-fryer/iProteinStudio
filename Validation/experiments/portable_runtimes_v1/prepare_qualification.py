"""Install the candidate closures in an isolated root; preserve the active app."""
import fcntl,json,os,shutil,sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];OUT=REPO/'Validation/output/portable_runtimes_v1';managed=Path.home()/'.iproteinstudio';root=OUT/'qualification_root'
sys.path.insert(0,str(REPO/'Sources/iProteinStudio/Resources/pipeline/scripts'))
from runtime_package import activate,digest
from engine_registry import engines
from runtime_view import clone_file
root.mkdir(exist_ok=True)
for name in ('models','shared','cache','patches','locks','numba_cache'):
 if not (root/name).exists():(root/name).symlink_to(managed/name)
for name in ('scripts','rfd3_scripts'):
 source=REPO/'Sources/iProteinStudio/Resources/pipeline'/name
 if source.exists():shutil.copytree(source,root/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
for directory in ('src','venvs'):
 (root/directory).mkdir(exist_ok=True)
 for source in (managed/directory).iterdir():
  dest=root/directory/source.name
  if not dest.exists():dest.symlink_to(source)
if not (root/'rfd3').exists():(root/'rfd3').symlink_to(managed/'rfd3')
base=root/'components/nesso/v1.0.0-mps-1';base.mkdir(parents=True,exist_ok=True)
for source in (managed/'components/nesso/v1.0.0-mps-1').iterdir():
 if not (base/source.name).exists():(base/source.name).symlink_to(source)
results=[]
for package in sorted(OUT.glob('*-release-v1')):
 if package.name=='antifold-release-v1':package=OUT/'antifold-release-v2'
 if not (package/'runtime.json').exists():continue
 engine=json.loads((package/'runtime.json').read_text())['engine'];mapping={k:v for d in engines().values() if d['component']==engine for k,v in d['mappings'].items()}
 installed=activate(root,engine,package,digest(package/'runtime.json'),[str(root/k)+'='+v for k,v in mapping.items()])
 results.append(dict(engine=engine,path=str(installed)));(OUT/'qualification-install.json').write_text(json.dumps(results,indent=2)+'\n');print(engine,'INSTALLED',flush=True)
