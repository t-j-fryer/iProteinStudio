"""Audit a completed pilot, then submit the already reviewed full immutable plan.

No inference is launched directly. Failure/cancellation or missing branch coverage
blocks the continuation. Stop the watcher with STOP_CONTINUATION in its state dir.
"""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'Sources/iProteinStudio/Resources/pipeline/mcp'))
from server import MCPServer
from iprotein_mcp.common import atomic_json, runtime_root, utc_now


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_branch(output):
    """Require actual successful repair advancement and the two-parent limit."""
    selection = read(output / 'cycle02/partial_noising/selection.json')
    proposals = read(output / 'cycle02/proposal_round.json')
    require(proposals['normal_parent_limit'] == 2, 'Ordinary sampling parent limit differs')
    require(all(0 < len(v) <= 2 for v in proposals['parents'].values()), 'Invalid ordinary parent count')
    require(proposals['sampled'] == sum(map(len, proposals['parents'].values())) * 3,
            'Unexpected ordinary proposal count')
    selected = [name for row in selection['trajectories'].values()
                if row['status'] == 'selected' and row['selected_backbone']
                for name in row['advanced']]
    require(bool(selected), 'Pilot did not advance a complete cycle-2 repair')
    for name in selected:
        row = read(output / 'candidates' / (name + '.json'))
        require(row['branch'] == 'partial-noising-repair' and row['passed'] and row['final_eligible'],
                'Repair is not a qualified complete candidate')
        require(set(row['sequence']) <= set('ACDEFGHIKLMNPQRSTVWY'), 'Repair contains unknown residues')
        require(all(isinstance(row.get(k), (float, int)) and math.isfinite(row[k])
                    for k in ('score', 'pbind', 'ligand_plddt')), 'Non-finite repair score')
        require(row['atom_checks']['passed'], 'Repair fails recorded atom criteria')
        require(set(row['atom_checks']['exposure']) == {'O18', 'O19'}, 'Wrong exposure selection')
    return selected


def audit(output):
    selected = check_branch(output)
    sys.path.insert(0, str(output / '.studio_runtime/pipeline/scripts/nise'))
    from runtime import Journal, Backend
    from atom_geometry import measure
    from ligand_atoms import audit_atoms
    settings = read(output / 'nise_config.json')['request']
    manifest = read(output / 'ligand_atom_map.json')
    journal = Journal(output)
    count = 0
    for path in output.rglob('*.json'):
        if '.studio_runtime' in path.parts:
            continue
        row = read(path)
        if isinstance(row, dict) and {'input', 'result', 'files'} <= row.keys():
            journal.load(path, row['input'])
            count += 1
    require(count > 0, 'No operation receipts to audit')
    for name in selected:
        row = read(output / 'candidates' / (name + '.json'))
        pdb = output / row['pdb']
        Backend.audit_structure(pdb, row['sequence'], True)
        audit_atoms(pdb, manifest)
        require(measure(pdb, settings, manifest)['passed'], 'Repair fails recomputed atom criteria')
    sessions = list((output / 'sessions').glob('*/ready.json'))
    # One planned application-update interruption is recorded for this pilot.
    # Each execution segment must remain resident; do not permit stage reloads.
    require(1 <= len(sessions) <= 2, 'Unexpected resident-session count')
    readies = [read(p) for p in sessions]
    require(all(r['device'] == 'mps' and r['model_load_count'] == 1 for r in readies), 'Invalid resident startup')
    responses = [read(p) for session in sessions for p in session.parent.glob('responses/*.json')]
    require(responses and all(r.get('ok') and r.get('completed_jobs') == 1 and
                             r.get('model_load_count') in (1, 2) for r in responses), 'Invalid resident receipt')
    require(any(r.get('phase') == 'affinity' and r['model_load_count'] == 2 for r in responses),
            'Affinity head was not exercised')
    cycle_sessions = set()
    for cycle in ('cycle01', 'cycle02'):
        for receipt in (output / cycle).rglob('completed.json'):
            row = read(receipt)
            cycle_sessions.add(row['result']['timing']['session'])
    require(len(cycle_sessions) == 1, 'Optimisation did not retain one resident worker across cycles')
    log = '\n'.join((session.parent / 'worker.log').read_text() for session in sessions)
    fallbacks = [line for line in log.splitlines() if 'will fall back to run on the CPU' in line]
    require(all('aten::linalg_svd' in line for line in fallbacks), 'Unexpected CPU fallback')
    return dict(accepted=True, audited_operation_receipts=count, selected_repairs=selected,
                resident_pids=[r['pid'] for r in readies], optimisation_sessions=sorted(cycle_sessions), responses=len(responses),
                allowed_svd_fallback_warnings=len(fallbacks), audited_at=utc_now())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    state_dir = args.state_dir.resolve()
    with (state_dir / 'continuation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pilot = read(state_dir / 'pilot_plan.json')
        full = read(state_dir / 'full_plan.json')
        expected = read(Path(__file__).with_name('full_request.json'))['request']
        require(full['normalized_request']['request'] == expected, 'Full request differs from reviewed settings')
        pilot_job = read(state_dir / 'pilot_job.json')['id']
        output = Path(pilot['normalized_request']['output'])
        server = MCPServer('run')
        report = None
        for _ in range(48 * 120):  # At most 48 h; 30-second polls.
            if (state_dir / 'STOP_CONTINUATION').exists():
                raise RuntimeError('Continuation stopped by local stop marker')
            status = server.tool_call('job_status', {'job_id': pilot_job})
            atomic_json(state_dir / 'pilot_status.json', status)
            require(status['status'] not in {'failed', 'cancelled', 'stopping'},
                    'Pilot did not complete: ' + str(status.get('error') or status.get('message')))
            if status['status'] == 'completed':
                if report is None:
                    run_id = 'test2/nise_runs/' + output.name
                    atomic_json(state_dir / 'pilot_overview.json', server.tool_call(
                        'results_overview', {'run_id': run_id, 'limit': 20}))
                    report = audit(output)
                    atomic_json(state_dir / 'pilot_audit.json', report)
                # The open updated app stages under the shared execution lease
                # after the pilot exits. Do not race it with the full campaign.
                staged = runtime_root() / 'mcp/MCP_VERSION'
                current = ROOT / 'Sources/iProteinStudio/Resources/pipeline/mcp/MCP_VERSION'
                expected_script = Path(full['normalized_request']['pipeline_snapshot']) / 'scripts/nise/nise_run.py'
                runtime_script = runtime_root() / 'scripts/nise/nise_run.py'
                if (staged.is_file() and staged.read_bytes() == current.read_bytes()
                        and runtime_script.is_file()
                        and hashlib.sha256(runtime_script.read_bytes()).digest() == hashlib.sha256(expected_script.read_bytes()).digest()):
                    job = server.tool_call('job_start', {'plan_id': full['id'], 'plan_sha256': full['sha256']})
                    atomic_json(state_dir / 'full_job.json', job)
                    atomic_json(Path(full['normalized_request']['output']) / 'studio_job.json',
                                {'id': job['id'], 'plan_id': full['id'], 'sha256': full['sha256']})
                    atomic_json(state_dir / 'continuation.json', dict(status='full_campaign_submitted',
                                job_id=job['id'], audit=report, updated_at=utc_now()))
                    return
            atomic_json(state_dir / 'continuation.json', dict(status='waiting_for_runtime_update' if report else 'waiting_for_pilot',
                        pilot_job=pilot_job, full_plan=full['id'], pid=os.getpid(), updated_at=utc_now()))
            time.sleep(30)
        raise RuntimeError('Continuation timed out after 48 hours')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Keep the failure visible; never weaken criteria or submit on error.
        if '--state-dir' in sys.argv:
            destination = Path(sys.argv[sys.argv.index('--state-dir') + 1])
            atomic_json(destination / 'continuation.json', dict(status='blocked', error=str(exc), updated_at=utc_now()))
        raise
