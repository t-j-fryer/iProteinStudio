"""Read-only validation audit, independent of the batch runner's summary."""
import argparse
import json
from pathlib import Path
import re
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'Sources/iProteinStudio/Resources/pipeline/scripts/nise'))
from runtime import Journal, atomic, digest


def audit(output):
    summary = json.loads((output / 'summary.json').read_text())
    assert summary['status'] == 'completed' and summary['recovery_verified']
    assert summary['repeat_resume_reused_all']
    config = json.loads((output / 'nise_config.json').read_text())
    names = config['batch_test']['ids']
    receipts = {}
    for name in names:
        for filename in ('completed.json', 'affinity_completed.json'):
            path = output / 'folds' / name / filename
            data = json.loads(path.read_text())
            result = Journal(output).load(path, data['input'])
            assert result is not None
            if filename == 'affinity_completed.json':
                assert 0 <= result['prediction']['pbind'] <= 1
            receipts[str(path.relative_to(output))] = digest(path)
    batches = []
    for path in sorted((output / 'folds/_batches').glob('*/batch.json')):
        descriptor = json.loads(path.read_text())
        events = list((path.parent / 'items').glob('*.json'))
        batches.append(dict(phase=descriptor['phase'], inputs=len(descriptor['specifications']),
                           completions=len(events), descriptor_sha256=digest(path)))
    assert sorted(b['inputs'] for b in batches if b['phase'] == 'structure') == [1, 2]
    assert [b['inputs'] for b in batches if b['phase'] == 'affinity'] == [2]
    ready = [json.loads(p.read_text()) for p in output.glob('sessions/*/ready.json')]
    assert len(ready) == 2 and all(r['device'] == 'mps' and r['model_load_count'] == 1 for r in ready)
    responses = [json.loads(p.read_text()) for p in output.glob('sessions/*/responses/*.json')]
    affinity = [r for r in responses if r.get('phase') == 'affinity']
    assert len(affinity) == 1 and affinity[0]['ok']
    assert affinity[0]['completed_jobs'] == 2 and affinity[0]['model_load_count'] == 2
    assert len(responses) == 2, 'Repeated resume unexpectedly issued another request'
    logs = [p.read_text() for p in output.glob('sessions/*/worker.log')]
    fallbacks = [line.strip() for log in logs for line in log.splitlines()
                 if 'fall back' in line or 'falling back' in line]
    assert all('aten::linalg_svd' in line for line in fallbacks), fallbacks
    assert all('GPU available: True (mps), used: True' in log for log in logs)
    return dict(status='passed', output=str(output), receipts=receipts, batches=batches,
                workers=ready, completed_requests=responses, documented_svd_fallback_warnings=len(fallbacks),
                untested=['Long campaign memory soak', 'Full-funnel outcome equivalence',
                          'Mixed per-input seed overrides (unsupported)'],
                interpretation='Transport/recovery audit; no performance or binder-quality conclusion')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--save', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.output)
    atomic(args.save, result)
    print(json.dumps(result, indent=2))
