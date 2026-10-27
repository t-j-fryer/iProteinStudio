"""Fetch pinned beta assets only; never execute model repository code."""
import argparse, hashlib, json, shutil, subprocess, sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[3]
SCRIPTS=REPO/'Sources/iProteinStudio/Resources/pipeline/scripts'
p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,required=True);p.add_argument('--reuse-root',type=Path);a=p.parse_args()
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
items=json.loads((SCRIPTS/'runtime_assets.json').read_text())['assets']['esmfold2_600']
for item in items:
 dest=a.cache/item['path'];dest.parent.mkdir(parents=True,exist_ok=True)
 old=a.reuse_root/item['path'] if a.reuse_root else None
 if not dest.exists() and old and old.is_file() and sha(old)==item['sha256']:
  shutil.copyfile(old,dest)
 subprocess.run([sys.executable,str(SCRIPTS/'download_verified.py'),'--url',item['url'],'--sha256',item['sha256'],'--output',str(dest),'--label',item['label']],check=True)
assert all(sha(a.cache/i['path'])==i['sha256'] for i in items)
(a.cache/'verified-assets.json').write_text(json.dumps(items,indent=2)+'\n')
print('All beta assets downloaded and verified')
