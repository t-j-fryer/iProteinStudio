#!/usr/bin/env python3
"""Stage only the reviewed sampler and runner, retaining old files and hashes."""
import fcntl
import json
import os
import shutil
import subprocess
from pathlib import Path
from campaign import base


def main():
    source = base.ROOT / 'Sources/iProteinStudio/Resources/pipeline'
    receipt_path = base.OUTPUT / 'stage_receipt.json'
    names = ('nanohunter_run.sh', 'scripts/secondary_structure_control.py')
    with (base.RUNTIME / 'agent/execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        jobs = base.run_ctl('jobs')['jobs']
        if any(job['status'] not in {'completed', 'failed', 'cancelled'} for job in jobs):
            base.die('An active/queued job exists; do not change managed scientific code')
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            for name in names:
                expected = receipt['files'][name]['after_sha256']
                if base.sha256(source / name) != expected or base.sha256(base.RUNTIME / name) != expected:
                    base.die('Staging receipt exists but source/runtime changed; review before restaging')
            print(json.dumps(receipt, indent=2))
            return
        reference = json.loads((base.ROOT / 'Validation/output/secondary_structure_priors_v1/manifest_full.json').read_text())
        records = {}
        for name, key in zip(names, ('runner_sha256', 'secondary_helper_sha256')):
            before = base.sha256(base.RUNTIME / name)
            if before != reference['runtime'][key]:
                base.die(f'Unexpected installed version before staging: {name}')
            backup = base.OUTPUT / 'runtime_before' / name
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(base.RUNTIME / name, backup)
            records[name] = {'before_sha256': before, 'after_sha256': base.sha256(source / name),
                             'backup': str(backup.relative_to(base.OUTPUT))}
        fingerprints = {}
        for relative in ('receipts/boltz.json', 'models/boltz2/boltz2_conf.ckpt',
                         'src/LigandMPNN/model_params/solublempnn_v_48_020.pt'):
            path = base.RUNTIME / relative
            if path.is_file():
                fingerprints[relative] = {'sha256': base.sha256(path), 'bytes': path.stat().st_size}
        for name in names:
            dest = base.RUNTIME / name
            temporary = dest.with_name(dest.name + '.seed-mask-stage')
            shutil.copy2(source / name, temporary)
            os.replace(temporary, dest)
        receipt = {'files': records, 'engine_fingerprints': fingerprints,
                   'hardware': subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'], text=True).strip(),
                   'memory_bytes': int(subprocess.check_output(['sysctl', '-n', 'hw.memsize'], text=True)),
                   'os_version': subprocess.check_output(['sw_vers', '-productVersion'], text=True).strip()}
        base.atomic_json(receipt_path, receipt)
        print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
