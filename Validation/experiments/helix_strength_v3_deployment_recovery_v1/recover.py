"""Continue the immutable v3 monomer study after a reviewed NISE-only deployment."""
import argparse
import fcntl
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'Validation/experiments/helix_strength_all_engines_v3'))
import campaign as c
import audit
import finish

RECOVERY = c.OUTPUT / 'deployment_recovery_v1'
REVIEWED = {'mcp/MCP_VERSION', 'mcp/README.md', 'mcp/iprotein_mcp/__init__.py',
            'mcp/iprotein_mcp/catalog.py', 'scripts/nise/campaign.py',
            'scripts/nise/contract.py', 'scripts/nise/nise_run.py',
            'scripts/nise/runtime.py', 'scripts/nise/setup_nesso.py'}


def verify_stage(full_hashes=False):
    baseline = c.read(c.OUTPUT / 'stage_receipt.json')
    amendment = c.read(RECOVERY / 'amendment.json')
    c.require(amendment['manifest_sha256'] == c.sha(c.OUTPUT / 'manifest.json'), 'Amendment manifest changed')
    c.require(amendment['controller_sha256'] == c.sha(__file__), 'Recovery controller changed')
    accepted = amendment['accepted_files']
    c.require(set(accepted) == REVIEWED, 'Unreviewed deployment scope')
    for name, record in baseline['files'].items():
        c.require(c.sha(c.SOURCE / name) == record['after_sha256'], f'Original source changed: {name}')
        expected = accepted[name]['sha256'] if name in accepted else record['after_sha256']
        c.require(c.sha(c.RUNTIME / name) == expected, f'Runtime provenance changed: {name}')
    for name, record in {**baseline['engine_files'], **baseline['engine_code']}.items():
        expected = accepted.get(name, record)
        path = c.RUNTIME / name
        stat = path.stat()
        c.require(stat.st_size == expected['bytes'] and stat.st_mtime_ns == expected['mtime_ns'], f'Engine file changed: {name}')
        if full_hashes or name in accepted:
            c.require(c.sha(path) == expected['sha256'], f'Engine checksum changed: {name}')
    return baseline


c.verify_stage = verify_stage


def run():
    c.prepare()
    with (c.OUTPUT / 'controller.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify_stage(full_hashes=True)
        for arm in c.CONFIG['arms']:
            for phase in ('pilot', 'remaining'):
                status_path = c.OUTPUT / 'status' / phase / (arm + '.json')
                state = c.read(status_path) if status_path.exists() else None
                # Completed units are audited in place; never re-plan/re-execute them.
                if not state or state['status'] not in c.TERMINAL:
                    plan = c.ensure_plan(phase, arm)
                    state = c.ctl('start', plan['id'], plan['sha256'])
                    c.atomic(c.OUTPUT / 'jobs' / phase / (arm + '.json'), {'id': state['id'], 'plan_id': plan['id']})
                    c.emit({'phase': phase, 'arm': arm, **c.compact(state)})
                    while state['status'] not in c.TERMINAL:
                        time.sleep(15)
                        state = c.ctl('job-status', state['id'])
                        c.atomic(status_path, state)
                    c.atomic(status_path, state)
                c.emit({'phase': phase, 'arm': arm, **c.compact(state)})
                result = audit.audit(phase, arm)
                c.emit({'phase': phase, 'arm': arm, 'operational_passed': result['operational_passed']})
                c.require(result['operational_passed'], f'Output audit requires diagnosis: {phase}/{arm}')
                c.atomic(c.OUTPUT / 'analysis_status.json', {
                    'complete': False, 'status': 'running', 'time': c.now(),
                    'last_audited': {'phase': phase, 'arm': arm}, 'geometry_policy': 'record_only'})
        verify_stage(full_hashes=True)
        audit.report()
        c.atomic(c.OUTPUT / 'analysis_status.json', finish.finish())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['audit-baseline', 'run'])
    args = parser.parse_args()
    try:
        if args.action == 'run':
            run()
        else:
            verify_stage(full_hashes=True)
            for phase in ('pilot', 'remaining'):
                result = audit.audit(phase, 'boltz_h0')
                c.emit({'phase': phase, 'operational_passed': result['operational_passed'],
                        'trajectories': len(result['trajectories']), 'structures': len(result['structures'])})
    except Exception as error:
        result = {'complete': False, 'status': 'blocked', 'error': str(error), 'time': c.now()}
        c.atomic(c.OUTPUT / 'analysis_status.json', result)
        c.emit(result)
        raise
