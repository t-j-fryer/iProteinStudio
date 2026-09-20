"""Isolated, byte-sealed runtime preparation. Never modify installed engines."""
import argparse, hashlib, json, os, shutil, subprocess, sys, urllib.request
from pathlib import Path
REPO=Path(__file__).resolve().parents[3]
OUT=REPO/'Validation/output/apple_runtime_throughput_v2'
ROOT=Path(os.environ.get('NANOHUNTER_ROOT',Path.home()/'.iproteinstudio')).resolve()
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'apple_runtime_throughput_v1'))
from prepare_environments import sha, seal
SPECS={
'intellifold':('venvs/NanoHunter_intellifold','3.12','IntelliFold'),
'protenix':('venvs/NanoHunter_protenix','3.11','Protenix'),
'constraint':('venvs/NanoHunter_protenix_constraint','3.12','ProtenixConstraint'),
'openfold':('venvs/NanoHunter_openfold3_mlx','3.11','openfold-3-mlx'),
'nesso':('components/nesso/v1.0.0-mps-1/venv','3.12',None),
'antifold':('venvs/NanoHunter_antifold','3.10','AntiFold'),
'rfd3':('rfd3/.venv','3.12',None)}
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def clone(a,b):
 b.parent.mkdir(parents=True,exist_ok=True)
 subprocess.run(['/bin/cp','-cR',str(a),str(b)],check=True)
def wheel(package,version,py):
 cache=OUT/'wheels';cache.mkdir(exist_ok=True)
 meta=json.load(urllib.request.urlopen(f'https://pypi.org/pypi/{package}/{version}/json',timeout=40))
 tag='cp'+py.replace('.','')
 files=[x for x in meta['urls'] if x['filename'].endswith('.whl') and (((tag in x['filename'] or 'py3-none-' in x['filename']) and 'macosx' in x['filename'] and 'arm64' in x['filename']) or 'py3-none-any' in x['filename'])]
 if len(files)>1 and package.startswith('mlx'):
  files=[x for x in files if 'macosx_26_0' in x['filename']]
 if len(files)!=1:raise RuntimeError(f'Ambiguous wheel {package}: {[x["filename"] for x in files]}')
 info=files[0];path=cache/info['filename'];write(path.with_suffix('.json'),info)
 if not path.exists():
  with urllib.request.urlopen(info['url'],timeout=90) as r,path.with_suffix('.part').open('wb') as f:shutil.copyfileobj(r,f,8<<20)
  path.with_suffix('.part').replace(path)
 if sha(path)!=info['digests']['sha256']:raise RuntimeError('Wheel checksum mismatch')
 return path

def main():
 ap=argparse.ArgumentParser();ap.add_argument('engines',nargs='+',choices=SPECS);a=ap.parse_args()
 OUT.mkdir(parents=True,exist_ok=True);uv=ROOT/'toolchains/uv/0.11.32/uv'
 env=dict(os.environ,UV_CACHE_DIR=str(OUT/'uv-cache'),UV_PYTHON_DOWNLOADS='never',PYTHONDONTWRITEBYTECODE='1')
 for engine in a.engines:
  rel,py,source=SPECS[engine];shadow=OUT/'roots'/engine;shadow.mkdir(parents=True,exist_ok=True)
  if not (shadow/'scripts').exists():clone(ROOT/'scripts',shadow/'scripts')
  if source and not (shadow/'src'/source).exists():clone(ROOT/'src'/source,shadow/'src'/source)
  if not (shadow/'models').exists():(shadow/'models').symlink_to(ROOT/'models',target_is_directory=True)
  if engine=='rfd3':
   for name in ('mlx_port','scripts','port'):
    if not (shadow/'rfd3'/name).exists():clone(ROOT/'rfd3'/name,shadow/'rfd3'/name)
   for name in ('weights','checkpoints','assets','oracle'):
    if (ROOT/'rfd3'/name).exists() and not (shadow/'rfd3'/name).exists():(shadow/'rfd3'/name).symlink_to(ROOT/'rfd3'/name,target_is_directory=True)
   for name in ('rfd3_weight_set.py',):shutil.copy2(ROOT/'rfd3'/name,shadow/'rfd3'/name)
  # The strict version check is changed only in an experimental helper. Worker asserts exact arm version.
  p=shadow/'scripts/resident_predictor.py';s=p.read_text();s=s.replace('if importlib.metadata.version("torch") != "2.6.0":','if importlib.metadata.version("torch") not in {"2.6.0", "2.14.0"}:');p.write_text(s)
  for arm in ('baseline','candidate'):
   dest=OUT/'environments'/f'{engine}-{arm}';receipt=OUT/f'{engine}-{arm}.seal.json'
   if receipt.exists():print('PREPARED',engine,arm,flush=True);continue
   if not dest.exists():
    subprocess.run([str(uv),'venv','--python',str(ROOT/rel/'bin/python'),str(dest)],env=env,check=True)
    subprocess.run(['/bin/cp','-cR',str(ROOT/rel/f'lib/python{py}/site-packages')+'/.',str(dest/f'lib/python{py}/site-packages')],check=True)
    site=dest/f'lib/python{py}/site-packages'
    for p in [*site.glob('*finder.py'),*site.glob('*.pth')]:
     s=p.read_text();s=s.replace(str(ROOT/'src'),str(shadow/'src'));p.write_text(s)
    # Avoid stale editable-finder bytecode copied from the installed source.
    for p in site.glob('__pycache__/*finder*.pyc'):p.unlink()
   if arm=='candidate':
    packages=[('mlx','0.32.2'),('mlx-metal','0.32.2')] if engine=='rfd3' else [('torch','2.14.0'),('sympy','1.14.0')]
    paths=[wheel(n,v,py) for n,v in packages]
    subprocess.run([str(uv),'pip','install','--python',str(dest/'bin/python'),'--no-deps','--no-build',*[str(p) for p in paths]],env=env,check=True)
   check=subprocess.run([str(uv),'pip','check','--python',str(dest/'bin/python')],env=env,capture_output=True,text=True)
   (OUT/f'{engine}-{arm}.dependencies.txt').write_text(check.stdout+check.stderr)
   # Preserve pre-existing pin conflicts; don't silently rewrite package metadata. Compare before/after in report.
   packages=subprocess.check_output([str(uv),'pip','freeze','--python',str(dest/'bin/python')],env=env,text=True)
   (OUT/f'{engine}-{arm}.packages.txt').write_text(packages)
   write(receipt,seal(dest));print('SEALED',engine,arm,'dependency_check',check.returncode,flush=True)
  files={}
  for sub in ('scripts','src','rfd3/mlx_port','rfd3/scripts','rfd3/port'):
   for p in (shadow/sub).rglob('*'):
    if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts and p.suffix!='.pyc':files[str(p.relative_to(shadow))]=sha(p)
  write(OUT/f'{engine}.source.json',dict(root=str(shadow),files=files))
if __name__=='__main__':main()
