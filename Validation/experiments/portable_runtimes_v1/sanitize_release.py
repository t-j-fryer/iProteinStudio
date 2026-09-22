"""Seal relocatable Python metadata; executable model/native code stays identical."""
import concurrent.futures,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'Validation/output/portable_runtimes_v1';sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts')]
from relocate_python_metadata import relocate
from runtime_view import clone_file
from runtime_package import digest,verify

def one(row):
 source=Path(row['package']);dest=OUT/(row['engine']+'-release-final2');shutil.copytree(source,dest,symlinks=True,copy_function=clone_file)
 m=json.loads((dest/'runtime.json').read_text());changed,removed=relocate(dest/'python')
 for path in removed:del m['files'][str(path.relative_to(dest))]
 for path in changed:m['files'][str(path.relative_to(dest))]=dict(size=path.stat().st_size,sha256=digest(path))
 m['python_metadata_relocatable']=True;(dest/'runtime.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');verify(dest)
 env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX='/dev/null');env.pop('PYTHONPATH',None)
 code='import importlib,sys,sysconfig; '+ '; '.join('importlib.import_module('+repr(n)+')' for n in m['relocation_imports'])+'; assert sysconfig.get_config_var("LIBDIR")==sys.base_prefix+"/lib"; print("relocated metadata and imports PASS")'
 renamed=dest.with_name(dest.name+' space Ω');dest.rename(renamed)
 try:subprocess.run([str(renamed/'python/bin/python3'),'-I','-B','-c',code],check=True,env=env,stdout=subprocess.DEVNULL)
 finally:renamed.rename(dest)
 subprocess.run([sys.executable,str(ROOT/'tools/archive_runtime_package.py'),str(dest),'--output',str(OUT/'github-final2')],check=True,stdout=subprocess.DEVNULL)
 result=dict(engine=m['engine'],package=str(dest),manifest_sha256=digest(dest/'runtime.json'),changed_metadata=[str(p.relative_to(dest)) for p in changed],removed_local_install_metadata=len(removed),passed=True)
 print(m['engine'],'FINAL PASS',flush=True);return result
rows=json.loads((OUT/'publication-assets.json').read_text())
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(one,rows))
(OUT/'final-package-qualification-v2.json').write_text(json.dumps(results,indent=2)+'\n')
