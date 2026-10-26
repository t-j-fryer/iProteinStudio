"""Pause the declared managed pilot after its first complete prediction pair."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--run',type=Path,required=True);p.add_argument('--job',required=True)
p.add_argument('--bridge',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
assert not a.output.exists()
marker=a.run/'cycles/design_0001/ligandmpnn-fixed/001/untemplated/complete.json'
deadline=time.monotonic()+1800
while not marker.exists():
    if (a.run/'status.json').exists():
        raise SystemExit('Run ended before interruption point; no cancellation sent')
    if time.monotonic()>deadline:raise SystemExit('Receipt wait timed out; no cancellation sent')
    time.sleep(1)
# Preserve hashes and timestamps of completed units before asking the broker to stop.
files={}
for receipt in a.run.glob('cycles/**/complete.json'):
    paths=[receipt]+[receipt.parent/name for name in json.loads(receipt.read_text())['files']]
    for path in paths:
        files[str(path.relative_to(a.run))]=dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),mtime_ns=path.stat().st_mtime_ns)
result=subprocess.run(['python3',str(a.bridge),'cancel',a.job],text=True,capture_output=True)
a.output.write_text(json.dumps(dict(job=a.job,completed_files=files,cancel_returncode=result.returncode,
                                    cancel=json.loads(result.stdout) if result.stdout else result.stderr),indent=2)+'\n')
assert result.returncode==0,result.stderr
print('Managed cancellation recorded after complete guided/untemplated pair.')
