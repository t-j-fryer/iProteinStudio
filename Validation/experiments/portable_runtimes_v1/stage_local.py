"""Stage qualified application resources atomically under the shared execution lease."""
import fcntl,json,os,shutil,time
from pathlib import Path
repo=Path(__file__).resolve().parents[3];root=Path.home()/'.iproteinstudio';source=repo/'Sources/iProteinStudio/Resources'
(root/'agent').mkdir(exist_ok=True)
with (root/'agent/execution.lock').open('a+') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 # Installing while a queued job carries a pre-update plan would invalidate it.
 active=[]
 for p in (root/'agent/jobs').glob('*/state.json'):
  state=json.loads(p.read_text())
  if state.get('status') in ('queued','running','stopping'):active.append(state['id'])
 if active:raise RuntimeError('Active jobs must finish before staging: '+str(active))
 backup=root/'backups/studio-resources'/('0177-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()));backup.mkdir(parents=True)
 items=list((source/'pipeline').iterdir())+[source/'rfd3_overlay']
 for p in items:
  dest=root/p.name;staged=root/('.stage-0177-'+p.name)
  if staged.exists():raise RuntimeError('Unexpected previous stage '+str(staged))
  if p.is_dir():shutil.copytree(p,staged,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.DS_Store'))
  else:shutil.copy2(p,staged)
  if dest.exists() or dest.is_symlink():dest.rename(backup/p.name)
  staged.rename(dest)
 print(json.dumps(dict(backup=str(backup),staged=[p.name for p in items])),flush=True)
