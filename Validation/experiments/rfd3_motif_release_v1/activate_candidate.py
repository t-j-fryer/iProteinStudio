"""Activate the verified candidate transactionally, only between GPU jobs."""
import fcntl,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'))
from runtime_package import activate,digest
managed=Path.home()/'.iproteinstudio';out=ROOT/'Validation/output/rfd3_motif_release_v1';package=out/'rfd3-candidate'
end=time.monotonic()+1800
while time.monotonic()<end:
    with (managed/'agent/registry.lock').open('a+') as registry,(managed/'agent/execution.lock').open('a+') as execution:
        try:
            fcntl.flock(registry,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(execution,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:pass
        else:
            install=managed/'.install.lock'
            try:install.mkdir()
            except FileExistsError:pass
            else:
                (install/'pid').write_text(str(os.getpid())+'\n')
                before=(managed/'components/rfd3/current').resolve()
                try:
                    final=activate(managed,'rfd3',package,digest(package/'runtime.json'),[str(managed/'rfd3')+'=sources/RFD3'])
                    receipt={'before':str(before),'after':str(final),'manifest_sha256':digest(package/'runtime.json'),'old_runtime_retained':before.exists()}
                    (out/'rfd3-activation.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
                finally:(install/'pid').unlink();install.rmdir()
                break
    time.sleep(.1)
else:raise SystemExit('No idle lease; no runtime switched')
