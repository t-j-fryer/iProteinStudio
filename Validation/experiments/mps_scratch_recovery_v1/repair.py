"""Explicitly authorized one-time repair; never installed or run automatically."""
import fcntl,json,os,stat,subprocess,sys,time
from pathlib import Path
root=Path.home()/'.iproteinstudio';repo=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(root/'mcp'))
from server import MCPServer
s=MCPServer('run')
with (root/'agent/execution.lock').open('a+') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 active=[j['id'] for j in s.tool_call('jobs_list',{'limit':500})['jobs'] if j['status'] in ('running','queued','stopping')]
 if active:raise RuntimeError('Active Studio jobs: '+str(active))
 temp=Path(subprocess.check_output(['/usr/bin/getconf','DARWIN_USER_TEMP_DIR'],text=True).strip())
 path=temp/'com.apple.MetalPerformanceShadersGraph';st=path.lstat()
 if not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.getuid():raise RuntimeError('Expected an owned real directory')
 stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime());backup=path.with_name(path.name+'.studio-backup-'+stamp)
 if backup.exists():raise RuntimeError('Backup already exists')
 out=repo/'Validation/output/mps_scratch_recovery_v1'/('repair_'+stamp);out.mkdir(parents=True)
 record=dict(path=str(path),backup=str(backup),inode=st.st_ino,directory_metadata_bytes=st.st_size,mode=stat.S_IMODE(st.st_mode),contents_deleted=False,active_studio_jobs=active)
 (out/'before.json').write_text(json.dumps(record,indent=2));print(json.dumps(record),flush=True)
 os.rename(path,backup)
 try:os.mkdir(path,stat.S_IMODE(st.st_mode));os.chmod(path,stat.S_IMODE(st.st_mode))
 except BaseException:
  if not path.exists():os.rename(backup,path)
  raise
 assert backup.stat().st_ino==st.st_ino
 record.update(new_inode=path.stat().st_ino,new_directory_metadata_bytes=path.stat().st_size)
 (out/'completed.json').write_text(json.dumps(record,indent=2));print(json.dumps(record),flush=True)
