from pathlib import Path
import json,subprocess,re,concurrent.futures
root=Path.home()/'.iproteinstudio/components'
def audit(name):
 p=(root/name/'current').resolve();m=json.loads((p/'runtime.json').read_text());found={}
 for rel in m['native_files']:
  f=p/rel
  if not f.is_file():continue
  s=subprocess.run(['otool','-l',str(f)],text=True,capture_output=True).stdout
  versions=re.findall(r'\bminos\s+(\d+\.\d+(?:\.\d+)?)',s)+re.findall(r'cmd LC_VERSION_MIN_MACOSX\s+cmdsize \d+\s+version (\S+)',s)
  if versions:found[rel]=max(versions,key=lambda v:tuple(map(int,v.split('.'))))
 mx=max(found.values(),key=lambda v:tuple(map(int,v.split('.'))))
 return name,dict(manifest_minimum=m['minimum_macos'],binary_maximum=mx,highest_requirement_files=[k for k,v in found.items() if v==mx],native_files_checked=len(found))
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:r=dict(pool.map(audit,['protenix','openfold3','rfd3','esmfold2','rfd4']))
Path('/private/tmp/studio-os-audit.json').write_text(json.dumps(r,indent=2)+'\n')
for k,v in r.items():print(k, json.dumps(v)[:2200])
