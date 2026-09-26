"""Derive a new immutable runtime, changing export metadata code only."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'))
from runtime_package import verify,digest
from runtime_view import clone_file
old=(Path.home()/'.iproteinstudio/components/rfd3/current').resolve()
manifest=verify(old)
out=ROOT/'Validation/output/portable_workflow_launch_v1/rfd3-candidate'
out.mkdir(exist_ok=False)
for name,entry in manifest['files'].items():
    dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True)
    if 'symlink' in entry:dest.symlink_to(entry['symlink'])
    else:clone_file(old/name,dest)
changed=['milestone0_oracle.py','scripts/generate_backbones.py']
for name in changed:
    dest=out/'sources/RFD3'/name
    shutil.copy2(ROOT/'Sources/iProteinStudio/Resources/rfd3_overlay'/name,dest)
    manifest['files'][str(dest.relative_to(out))]={'sha256':digest(dest),'size':dest.stat().st_size}
manifest['studio_export_revision']='ligand-atom-identities-v1'
(out/'runtime.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
verify(out)
# Check actual relocation without changing or depending on installed links.
relocated=out.with_name(out.name+' relocation Ω');out.rename(relocated)
try:
    code='import importlib;'+ ';'.join('importlib.import_module('+repr(n)+')' for n in manifest['relocation_imports'])
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')};env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    subprocess.run([str(relocated/'python/bin/python3'),'-I','-B','-c',code],check=True,env=env)
finally:relocated.rename(out)
receipt={'parent_manifest_sha256':digest(old/'runtime.json'),'manifest_sha256':digest(out/'runtime.json'),'changed_files':changed,'unchanged_file_count':len(manifest['files'])-len(changed),'relocation_imports_passed':True,'contains_weights':False}
(out.parent/'rfd3-candidate-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt),flush=True)
