import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'Validation/output/portable_runtimes_v1';repo='t-j-fryer/iProteinStudio';tag='runtimes-2026.09.20-1'
def gh(*args):return subprocess.check_output(['gh',*args],text=True)
r=json.loads(gh('release','view',tag,'--repo',repo,'--json','isDraft,assets'));assert r['isDraft']
rows=json.loads((OUT/'publication-assets.json').read_text());expected={Path(v[key]).name for v in rows for key in ('archive_path','metadata')};present={a['name'] for a in r['assets']}
for row in rows:
 for key in ('archive_path','metadata'):
  path=row[key]
  if Path(path).name not in present:subprocess.run(['gh','release','upload',tag,path,'--repo',repo],check=True)
for name in present-expected-{'FINAL_PACKAGE_INVENTORY.json'}:
 subprocess.run(['gh','release','delete-asset',tag,name,'--repo',repo,'--yes'],check=True)
subprocess.run(['gh','release','upload',tag,str(OUT/'FINAL_PACKAGE_INVENTORY.json'),'--clobber','--repo',repo],check=True)
print('Final draft asset set uploaded',flush=True)
