"""Serial resident workers; checkpointed recovery and concise live job progress."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from common import save, sha


def main():
    config = Path(sys.argv[1])
    cfg = json.loads(config.read_text())
    out = Path(cfg['output'])
    previous = json.loads((out / 'progress.json').read_text()).get('results', []) if (out / 'progress.json').exists() else []
    previous = {(r['engine'], r['variant']): r for r in previous}
    results = []
    for engine, variant in cfg['arms']:
        dest = out / (engine + '__' + variant)
        if (dest / 'completed.json').exists():
            completed = json.loads((dest / 'completed.json').read_text())
            for measurement in completed['outputs']:
                receipt = json.loads(Path(measurement).with_name('complete.json').read_text())
                assert all(Path(f).is_file() and sha(f) == h for f, h in receipt['files'].items())
            results.append(previous.get((engine, variant), dict(engine=engine, variant=variant, exit_code=0, reused_completed=True)))
            continue
        env = dict(os.environ)
        env.pop('PYTORCH_MPS_FAST_MATH', None)
        env.pop('PYTORCH_MPS_PREFER_METAL', None)
        if variant == 'metal':
            env['PYTORCH_MPS_PREFER_METAL'] = '1'
        command = [cfg['engines'][engine]['python'], str(Path(__file__).with_name('worker.py')), str(config), engine, str(dest), variant]
        attempts = []
        max_attempts = 2 if cfg['phase'] == 'campaign' else 1
        for attempt in range(1, max_attempts + 1):
            started = time.time()
            print('ARM_START', engine, variant, 'attempt', attempt, flush=True)
            log_path = out / (engine + '__' + variant + f'__{time.time_ns()}.log')
            with log_path.open('x', buffering=1) as log:
                process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in process.stdout:
                    log.write(line)
                    if line.startswith(('UNIT ', 'UNIT_START ', 'ASSET_VERIFY ')) or 'event=heartbeat' in line:
                        print(line, end='', flush=True)
                code = process.wait()
            attempts.append(dict(attempt=attempt, exit_code=code, seconds=time.time()-started, log=str(log_path)))
            if code == 0:
                break
            if (dest / 'active.json').exists():
                active = json.loads((dest / 'active.json').read_text())
                if active.get('status') == 'running':
                    save(dest / 'active.json', {**active, 'status': 'worker_failed', 'exit_code': code, 'log': str(log_path)})
            if attempt < max_attempts:
                print('ARM_RETRY', engine, 'same settings; completed units will be hash-verified; partial outputs preserved', flush=True)
        results.append(dict(engine=engine, variant=variant, exit_code=code, seconds=sum(a['seconds'] for a in attempts), attempts=attempts))
        save(out / 'progress.json', dict(results=results))
        print('ARM_END', results[-1], flush=True)
        if cfg['phase'] == 'campaign':
            report = subprocess.run([cfg['analysis_python'], str(Path(__file__).with_name('campaign_report.py')), str(config)], env={**env, 'OPENBLAS_NUM_THREADS': '1', 'MPLCONFIGDIR': str(out / 'analysis/mpl')})
            if report.returncode:
                save(out / 'analysis_failure.json', dict(engine=engine, exit_code=report.returncode))
                raise RuntimeError('Independent campaign audit failed; inspect analysis/audit.json')
    save(out / 'finished.json', dict(results=results))
    if any(r['exit_code'] for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
