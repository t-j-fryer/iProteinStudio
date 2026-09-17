"""Prepare/start the ten explicitly authorized, unstarted OpenFold campaigns.

Uses Studio's native preflight and broker, preserving original frozen runtimes.
No direct inference launch, modification of old plans, or completed-output edits.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BRIDGE = REPO / 'Sources/iProteinStudio/Resources/pipeline/mcp'
sys.path.insert(0, str(BRIDGE))
from iprotein_mcp import broker, common, plans
from iprotein_mcp.desktop import desktop_plan


def prepare():
    root = common.runtime_root()
    audit = HERE.parent / '0133-openfold-queue-audit'
    rows = [r for r in csv.DictReader((audit / 'campaigns.csv').open())
            if r['audited_state'] != 'completed']
    rows.sort(key=lambda r: (r['kind'] == 'nanobody', r['helix'], r['campaign']))
    assert len(rows) == 10 and sum(int(r['expected']) for r in rows) == 750
    originals = {j['id']: j for j in json.loads((audit / 'jobs.json').read_text())}
    # Verify immutable source plans and original failure before touching manifests.
    for job in originals.values():
        state = broker.load_state(job['id'])
        assert state['status'] == 'failed'
        assert 'no validated worker for predictor openfold-3-mlx' in (state.get('error') or '')
        plans.load_plan(job['plan_id'], job['plan_sha256'])
    for state in broker.list_jobs():
        assert state['status'] not in ('queued', 'running', 'stopping'), state['id']
    prepared = []
    for row in rows:
        output = root / 'projects/untitled_design' / row['campaign']
        path = output / 'studio_run.json'
        manifest = common.load_json(path)
        assert not (output / 'summary_all_runs.csv').exists(), output
        assert not list(output.glob('run_*/cycle_*/pred_min/*.cif')), output
        backup = output / '.studio_recovery/openfold_scheduler_v1'
        backup.mkdir(parents=True, exist_ok=True)
        saved = backup / 'studio_run.json'
        if not saved.exists():
            saved.write_bytes(path.read_bytes())
            old_job = output / 'studio_job.json'
            if old_job.exists():
                (backup / 'studio_job.json').write_bytes(old_job.read_bytes())
        original = common.load_json(saved)
        args = list(original['arguments'])
        assert args[args.index('--predictor') + 1] == 'openfold-3-mlx'
        assert args[args.index('--design-scheduler') + 1] == 'resident'
        assert args[args.index('--max-parallel') + 1] == '1'
        assert '--require-target-msa' in args
        assert args[args.index('--num-runs') + 1] == str(original['requestedTrajectories'])
        assert original['expectedOptimizedDesigns'] == int(row['expected'])
        args[args.index('--design-scheduler') + 1] = 'run'
        index = args.index('--wave-batch-size')
        assert args[index + 1] == 'all'
        del args[index:index + 2]
        snapshot = Path(original['pipelineSnapshot'])
        env = common.stable_environment(original.get('environmentOverrides') or {})
        env['IPROTEINSTUDIO_PIPELINE_SNAPSHOT'] = str(snapshot)
        check = subprocess.run(['/bin/bash', str(snapshot / 'nanohunter_run.sh'), *args, '--check-config'],
                               env=env, capture_output=True, text=True, timeout=120)
        (HERE / (output.name + '-preflight.log')).write_text(check.stdout + check.stderr)
        if check.returncode:
            raise RuntimeError(f'Configuration rejected for {output.name}: {check.stderr[-2000:]}')
        updated = dict(original, arguments=args)
        common.atomic_json(path, updated)
        source_job = originals[row['job']]
        recovery = {'source_job': row['job'], 'source_plan': source_job['plan_id'],
                    'source_plan_sha256': source_job['plan_sha256'],
                    'original_manifest_sha256': common.file_digest(saved),
                    'change': 'design-scheduler resident -> run; remove resident-only wave-batch-size all',
                    'scientific_settings_unchanged': True}
        common.atomic_json(backup / 'recovery.json', recovery)
        plan = desktop_plan({'project': 'untitled_design', 'workflow': 'iterative', 'output': str(output)})
        plans.load_plan(plan['id'], plan['sha256'])
        assert plan['normalized_request']['steps'][0]['command'][3:] == args
        entry = {'output': str(output), 'expected': int(row['expected']),
                 'plan_id': plan['id'], 'plan_sha256': plan['sha256'], **recovery}
        prepared.append(entry)
        common.atomic_json(HERE / 'prepared.json', prepared)
        print(json.dumps({'campaign': output.name, 'plan': plan['id'], 'expected': entry['expected'],
                          'scheduler': 'run', 'snapshot': str(snapshot)}), flush=True)
    assert len(prepared) == 10


def start():
    prepared = json.loads((HERE / 'prepared.json').read_text())
    assert len(prepared) == 10
    for entry in prepared:
        plans.load_plan(entry['plan_id'], entry['plan_sha256'])
    started = []
    for entry in prepared:
        state = broker.start_job(entry['plan_id'], entry['plan_sha256'])
        output = Path(entry['output'])
        common.atomic_json(output / 'studio_job.json', {'id': state['id'], 'plan_id': entry['plan_id'], 'sha256': entry['plan_sha256']})
        started.append({**entry, 'job_id': state['id']})
        common.atomic_json(HERE / 'started.json', started)
        print(json.dumps({'job': state['id'], 'state': state['status'], 'campaign': output.name}), flush=True)


def status():
    result = []
    for entry in json.loads((HERE / 'started.json').read_text()):
        state = broker.load_state(entry['job_id'])
        result.append({k: state.get(k) for k in ('id', 'status', 'stage', 'message', 'error', 'output_root', 'pipeline_log_tail')})
    common.atomic_json(HERE / 'status.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'start', 'status'))
    action = parser.parse_args().action
    {'prepare': prepare, 'start': start, 'status': status}[action]()
