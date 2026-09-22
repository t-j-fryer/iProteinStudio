"""Upload immutable runtime assets to a draft; publication is a separate step."""
import json,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[3];out=root/'Validation/output/portable_runtimes_v1';repo='t-j-fryer/iProteinStudio';tag='runtimes-2026.09.20-1'
subprocess.run(['gh','release','create',tag,'--repo',repo,'--draft','--prerelease','--title','Apple Silicon portable runtimes — 2026.09.20 profile','--notes-file',str(out/'runtime-release-notes.md')],check=True)
for row in json.loads((out/'publication-assets.json').read_text()):
 subprocess.run(['gh','release','upload',tag,row['archive_path'],row['metadata'],'--repo',repo],check=True)
 print(row['engine'],'UPLOADED',flush=True)
subprocess.run(['gh','release','upload',tag,str(out/'FINAL_PACKAGE_INVENTORY.json'),'--repo',repo],check=True)
