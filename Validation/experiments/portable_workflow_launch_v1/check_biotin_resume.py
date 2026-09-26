"""Verify old durable units are unchanged and new work appears after resume."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];out=ROOT/'Validation/output/portable_workflow_launch_v1';managed=Path.home()/'.iproteinstudio'
saved=json.loads((out/'biotin-stopped-checkpoints.json').read_text())['receipts'];started=json.loads((out/'biotin-resumed.json').read_text());root=Path(started['before']['output_root']);job=managed/'agent/jobs/job-221c7d6db092';state=json.loads((job/'state.json').read_text())
changed=[name for name,h in saved.items() if not (root/name).is_file() or hashlib.sha256((root/name).read_bytes()).hexdigest()!=h]
assert not changed,changed
all_receipts={str(p.relative_to(root)) for p in root.rglob('completed.json')};new=sorted(all_receipts-set(saved))
with (job/'pipeline.log').open('rb') as stream:stream.seek(started['pipeline_log_bytes_before']);tail=stream.read().decode(errors='replace')
receipt={'job_id':state['id'],'status':state['status'],'plan_id':state['plan_id'],'old_receipts_unchanged':len(saved),'new_completion_receipts':new,'new_progress_lines':tail.count('IPROTEINSTUDIO_PROGRESS|'),'new_log_tail':tail.splitlines()[-15:]}
(out/'biotin-resume-verification.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k!='new_log_tail'}))
