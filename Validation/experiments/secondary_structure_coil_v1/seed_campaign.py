#!/usr/bin/env python3
"""Matched seed-only turn/anti-helix interventions through immutable Studio jobs."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('seed_trial_base', HERE.parent / 'secondary_structure_seed_mask_v1/campaign.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
base = driver.base
base.CONFIG = json.loads((HERE / 'seed_config.json').read_text())
base.OUTPUT = base.ROOT / 'Validation/output/secondary_structure_coil_v1/seed_trials'
base.PROJECT = 'validation_secondary_structure_coil_v1'


def prepare(phase):
    # Reuse the already-staged, validated scientific implementation. This is a
    # settings-only comparison; refuse a changed runtime rather than restaging.
    reference_root = base.ROOT / 'Validation/output/secondary_structure_seed_mask_v1'
    reference = json.loads((reference_root / 'manifest_full.json').read_text())
    for name,key in [('nanohunter_run.sh','runner_sha256'),('scripts/secondary_structure_control.py','secondary_helper_sha256')]:
        if base.sha256(base.RUNTIME / name) != reference['runtime'][key]:
            base.die('Reference scientific implementation changed; do not run an unmatched contrast')
    receipt = base.OUTPUT / 'stage_receipt.json'
    if not receipt.exists():
        base.atomic_json(receipt, json.loads((reference_root / 'stage_receipt.json').read_text()))
    manifest = driver.prepare(phase)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare','start','status'])
    parser.add_argument('--phase', choices=['smoke','full'], default='smoke')
    args = parser.parse_args()
    if args.action == 'prepare':
        result = prepare(args.phase)
    elif args.action == 'start':
        prepare(args.phase)
        result = base.start(args.phase)
    else:
        states = base.status(args.phase)
        result = {arm:{key:state.get(key) for key in ('id','status','error','message','pipeline_log_tail')}
                  for arm,state in states.items()}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
