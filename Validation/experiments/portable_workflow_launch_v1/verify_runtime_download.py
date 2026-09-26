"""Verify the independently downloaded portable archive before release/install."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'))
from runtime_package import extract,verify,digest
out=ROOT/'Validation/output/portable_workflow_launch_v1';download=out/'runtime-download';record=json.loads(next(download.glob('*.release.json')).read_text());archive=download/record['archive']
assert digest(archive)==record['archive_sha256'] and archive.stat().st_size==record['bytes']
assert digest(archive)==digest(out/'runtime-release'/archive.name)
base=download/'extracted';base.mkdir(exist_ok=False);extract(archive,base);manifest=verify(base,record['manifest_sha256'],'rfd3')
receipt={**record,'independently_downloaded_archive_matches':True,'extracted_file_count':len(manifest['files']),'contains_weights':manifest['contains_weights']}
(out/'runtime-download-verification.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
