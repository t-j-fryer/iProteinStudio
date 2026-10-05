"""Derive a new immutable runtime, repairing the Foundry atom-selection mask."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'))
from runtime_package import verify,digest
from runtime_view import clone_file
old=(Path.home()/'.iproteinstudio/components/rfd3/current').resolve()
manifest=verify(old)
out=ROOT/'Validation/output/rfd3_motif_release_v1/rfd3-candidate'
out.mkdir(exist_ok=False)
for name,entry in manifest['files'].items():
    dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True)
    if 'symlink' in entry:dest.symlink_to(entry['symlink'])
    else:clone_file(old/name,dest)
import importlib.util
patch_path=ROOT/'Sources/iProteinStudio/Resources/rfd3_overlay/scripts/patch_foundry_rasa.py'
spec=importlib.util.spec_from_file_location('selection_patch',patch_path)
patch=importlib.util.module_from_spec(spec);spec.loader.exec_module(patch)
parser=out/'python/lib/python3.12/site-packages/rfd3/inference/input_parsing.py'
parser.write_text(patch.patch_source(parser.read_text()))
helper=out/'sources/RFD3/scripts/patch_foundry_rasa.py';shutil.copy2(patch_path,helper)
changed=[str(parser.relative_to(out)),str(helper.relative_to(out))]
for name in changed:
    dest=out/name
    manifest['files'][name]={'sha256':digest(dest),'size':dest.stat().st_size}
manifest['studio_selection_revision']='rasa-only-fixed-atoms-v1'
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
