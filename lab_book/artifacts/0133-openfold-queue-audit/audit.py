"""Read-only audit of the three desktop batches stopped by OpenFold residency."""
import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

root = Path(os.environ.get('NANOHUNTER_ROOT', Path.home() / '.iproteinstudio'))
rows = []
batches = []
for state_path in sorted((root / 'agent/jobs').glob('*/state.json')):
    job = json.loads(state_path.read_text())
    if job.get('kind') != 'desktop_iterative_batch' or 'no validated worker for predictor openfold-3-mlx' not in (job.get('error') or ''):
        continue
    batch = Path(job['output_root'])
    descriptor = json.loads((batch / 'studio_engine_batch.json').read_text())
    receipt = json.loads((batch / 'engine_batch_progress.json').read_text())
    checked = 0
    for name, campaign_path in zip(descriptor['engines'], descriptor['campaigns']):
        campaign = Path(campaign_path)
        manifest = json.loads((campaign / 'studio_run.json').read_text())
        files = receipt['completed'].get(str(campaign), {})
        for relative, digest in files.items():
            path = campaign / relative
            assert path.is_file(), path
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, path
            checked += 1
        summary = campaign / 'summary_all_runs.csv'
        data = list(csv.DictReader(summary.open())) if summary.exists() else []
        pairs = {(int(r['run']), int(r['cycle'])) for r in data}
        expected_pairs = {(r, c) for r in range(1, manifest['requestedTrajectories'] + 1)
                          for c in range(manifest['optimizationCycles'] + 1)}
        if files:
            assert pairs == expected_pairs and len(pairs) == len(data), campaign
            for r in data:
                assert Path(r['structure_path']).is_file(), r['structure_path']
        else:
            assert not data and not list(campaign.glob('run_*/cycle_*/pred_min/*.cif')), campaign
        request = manifest['request']
        rows.append(dict(batch=batch.name, job=job['id'], campaign=campaign.name,
                         engine=name, kind=request['designType'], scaffold=request.get('scaffoldID', ''),
                         helix=request.get('helixKill', ''), manifest_state=manifest['state'],
                         audited_state='completed' if files else ('failed_before_inference' if manifest['state']=='failed' else 'never_started'),
                         optimized=sum(int(r['cycle']) > 0 for r in data),
                         starts=sum(int(r['cycle']) == 0 for r in data),
                         expected=manifest['expectedOptimizedDesigns']))
    batches.append(dict(job=job['id'], batch=batch.name, status=job['status'],
                        created_at=job['created_at'], finished_at=job.get('finished_at'),
                        completed_campaigns=len(receipt['completed']),
                        total_campaigns=len(descriptor['campaigns']), checked_artifact_hashes=checked))
output = Path(__file__).resolve().parent
with (output / 'campaigns.csv').open('w') as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
report = dict(batches=batches, campaign_states=dict(Counter(r['audited_state'] for r in rows)),
              optimized_completed=sum(r['optimized'] for r in rows), starts_completed=sum(r['starts'] for r in rows),
              optimized_outstanding=sum(r['expected'] for r in rows if r['audited_state']!='completed'))
(output / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
