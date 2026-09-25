"""Compare released/new cancellation with one inert setsid child retaining a lease."""
import fcntl,json,os,signal,subprocess,sys,tempfile,threading,time,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Sources/iProteinStudio/Resources/pipeline/mcp'))
from iprotein_mcp import broker,common
old=types.ModuleType('iprotein_mcp.released_broker');old.__package__='iprotein_mcp'
old.__file__=broker.__file__
source=subprocess.check_output(['git','show','v0.2.3-beta:Sources/iProteinStudio/Resources/pipeline/mcp/iprotein_mcp/broker.py'],cwd=ROOT,text=True)
exec(compile(source,old.__file__,'exec'),old.__dict__)
results=[]
for label,module in [('released_0.2.3',old),('candidate',broker)]:
 with tempfile.TemporaryDirectory(prefix='studio-owned-child-fixture-') as directory:
  root=Path(directory);before=dict(os.environ);os.environ.update(NANOHUNTER_ROOT=str(root),IPROTEINSTUDIO_AGENT_ROOT=str(root/'agent'))
  child_pid=None;controller=None
  try:
   jid='job-owned-fixture';state=module.state_path(jid)
   common.atomic_json(state,dict(id=jid,status='running'))
   child_file=root/'child.pid';script=root/'fixture.py'
   script.write_text("import subprocess,sys,time,pathlib\np=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'],start_new_session=True,close_fds=False)\npathlib.Path(sys.argv[1]).write_text(str(p.pid))\ntime.sleep(60)\n")
   def cancel():
    deadline=time.monotonic()+10
    while not child_file.exists() and time.monotonic()<deadline:time.sleep(.01)
    time.sleep(.3);common.atomic_json(state.parent/'cancel.json',{'requested':True})
   controller=threading.Thread(target=cancel);controller.start()
   lease=root/'agent/execution.lock'
   with lease.open('a+') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);module._EXECUTION_FD=lock.fileno()
    code=module._run_logged(jid,[sys.executable,str(script),str(child_file)],root,dict(os.environ))
   controller.join();child_pid=int(child_file.read_text())
   with lease.open('a+') as test:
    try:fcntl.flock(test,fcntl.LOCK_EX|fcntl.LOCK_NB);blocked=False
    except BlockingIOError:blocked=True
   results.append(dict(implementation=label,exit_code=code,child_survived=common.process_alive(child_pid),execution_lock_still_blocked=blocked))
  finally:
   if child_file.exists():
    child_pid=int(child_file.read_text())
    if common.process_alive(child_pid):os.kill(child_pid,signal.SIGKILL)
   if controller:controller.join(timeout=12)
   os.environ.clear();os.environ.update(before)
assert results[0]['child_survived'] and results[0]['execution_lock_still_blocked'],results
assert not results[1]['child_survived'] and not results[1]['execution_lock_still_blocked'],results
print(json.dumps(results,indent=2))
