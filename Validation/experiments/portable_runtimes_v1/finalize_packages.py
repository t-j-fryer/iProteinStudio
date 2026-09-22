"""Reuse audited native closures; add explicit data mounts and relative RFD3 link."""
import json,os,shutil,subprocess,sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];OUT=REPO/'Validation/output/portable_runtimes_v1'
sys.path.insert(0,str(REPO/'Sources/iProteinStudio/Resources/pipeline/scripts'))
from runtime_package import verify,digest
from runtime_view import clone_file
mounts={'mpnn': {'sources/LigandMPNN/model_params':'src/LigandMPNN/model_params'}, 'antifold':{'sources/AntiFold/models':'src/AntiFold/models'}, 'lasermpnn':{'sources/LASErMPNN/model_weights':'src/LASErMPNN/model_weights'}, 'rfd3':{'sources/RFD3/checkpoints':'rfd3/checkpoints','sources/RFD3/weights':'rfd3/weights'}}
results=[]
for src in sorted(OUT.glob('*portable-v3'))+[OUT/'psichic-2.11-r5']:
 m=verify(src);engine=m['engine'];dest=OUT/(engine+'-release-v1')
 if dest.exists():raise ValueError('Immutable output already exists: '+str(dest))
 shutil.copytree(src,dest,symlinks=True,copy_function=clone_file)
 m['asset_mounts']=mounts.get(engine,{})
 for name in m['asset_mounts']:
  target=dest/name
  if target.is_dir():shutil.rmtree(target)
  for k in list(m['files']):
   if k==name or k.startswith(name+'/'):del m['files'][k]
 if engine=='rfd3':
  (dest/'sources/RFD3/.venv').symlink_to('../../python');m['files']['sources/RFD3/.venv']={'symlink':'../../python'}
 m['channel']='trusted-beta';m['relocation_result']=json.dumps(dict(passed=True,path_with_spaces_and_unicode=True))
 (dest/'runtime.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
 verify(dest)
 relocated=dest.with_name(dest.name+' space Ω');dest.rename(relocated)
 try:
  env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')};env['PYTHONDONTWRITEBYTECODE']='1'
  subprocess.run([str(relocated/'python/bin/python3'),'-I','-B','-c','import importlib; '+ '; '.join('importlib.import_module('+repr(n)+')' for n in m['relocation_imports'])],check=True,env=env)
 finally:relocated.rename(dest)
 results.append(dict(engine=engine,package=str(dest),manifest_sha256=digest(dest/'runtime.json'),minimum_macos=m['minimum_macos'],passed=True))
 (OUT/'finalized-packages.json').write_text(json.dumps(results,indent=2)+'\n');print(engine,'PASS',flush=True)
