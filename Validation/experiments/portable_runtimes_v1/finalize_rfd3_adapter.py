"""Freeze shared-registry routing without changing the inference implementation."""
import json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'Validation/output/portable_runtimes_v1'
sys.path.insert(0,str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'))
from runtime_view import clone_file
from runtime_package import digest,verify
source=OUT/'rfd3-release-v1';dest=OUT/'rfd3-release-v2'
shutil.copytree(source,dest,symlinks=True,copy_function=clone_file)
name='sources/RFD3/scripts/run_predictors.py';shutil.copy2(ROOT/'Sources/iProteinStudio/Resources/rfd3_overlay/scripts/run_predictors.py',dest/name)
p=dest/'runtime.json';m=json.loads(p.read_text());m['files'][name]=dict(sha256=digest(dest/name),size=(dest/name).stat().st_size);p.write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');verify(dest)
print(digest(p))
