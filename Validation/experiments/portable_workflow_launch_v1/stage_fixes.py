"""Stage app-owned launch fixes only while both Studio leases are available."""
import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parents[3]
MANAGED = Path.home()/'.iproteinstudio'
source = ROOT/'Sources/iProteinStudio/Resources'
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out = ROOT/'Validation/output/portable_workflow_launch_v1'/('staging-'+stamp)
out.mkdir()
files = [('pipeline/'+p,p) for p in [
    'nanohunter_run.sh','PIPELINE_VERSION','mcp/MCP_VERSION','scripts/openfold_query_json.py',
    'mcp/iprotein_mcp/__init__.py','mcp/iprotein_mcp/plans.py',
    'mcp/iprotein_mcp/broker.py','mcp/schemas/rfd3-v1.json']]
files += [('rfd3/prepare_campaign.py','rfd3_scripts/prepare_campaign.py')]
deadline = time.monotonic()+900
while time.monotonic()<deadline:
    with (MANAGED/'agent/registry.lock').open('a+') as registry, (MANAGED/'agent/execution.lock').open('a+') as execution:
        try:
            fcntl.flock(registry,fcntl.LOCK_EX|fcntl.LOCK_NB)
            fcntl.flock(execution,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            receipts=[]
            for relative,destination in files:
                src=source/relative;dest=MANAGED/destination
                assert not dest.is_symlink(), dest
                backup=out/destination;backup.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(dest,backup)
                temporary=dest.with_name('.'+dest.name+'.acceptance-staging')
                shutil.copy2(src,temporary);temporary.replace(dest)
                receipts.append({'path':destination,'before_sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),'after_sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
            (out/'receipt.json').write_text(json.dumps(receipts,indent=2)+'\n')
            print(json.dumps({'staged':len(receipts),'receipt':str(out/'receipt.json')}),flush=True)
            break
    time.sleep(0.1)
else:
    raise SystemExit('No idle execution lease became available; nothing staged')
