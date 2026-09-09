#!/usr/bin/env python3
"""Run the declared sequence-first, 50%-mask comparison through Studio's broker."""
import argparse
import importlib.util
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('seed_mask_base', HERE.parent / 'secondary_structure_priors_v1/campaign.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
BASE_ARGUMENTS = base.arguments_for
base.CONFIG = json.loads((HERE / 'config.json').read_text())
base.RUNTIME = Path(os.environ.get('NANOHUNTER_ROOT', str(Path.home() / '.iproteinstudio'))).resolve()
base.OUTPUT = base.ROOT / 'Validation/output/secondary_structure_seed_mask_v1'
base.PROJECT = 'validation_secondary_structure_seed_mask_v1'


def arguments_for(arm, trajectories):
    args = BASE_ARGUMENTS({'mode': 'none'}, trajectories)
    args += ['--secondary-bias', arm['mode'], '--secondary-bias-scope', 'seed-only',
             '--seed-sampling-order', 'sample-then-mask',
             '--beta-strength', str(arm['beta_strength']),
             '--beta-pattern-strength', str(arm['beta_pattern_strength']),
             '--turn-strength', str(arm['turn_strength']),
             '--ligand-temp-cycle1', '0.30', '--ligand-temp-other', '0.10']
    if arm['mode'] == 'mixed':
        args += ['--anti-helix-strength', str(arm['anti_helix_strength'])]
    return args


base.arguments_for = arguments_for


def verify_runtime(manifest=None):
    stage = json.loads((base.OUTPUT / 'stage_receipt.json').read_text())
    for name, record in stage['files'].items():
        if base.sha256(base.RUNTIME / name) != record['after_sha256']:
            base.die(f'Staged scientific code changed: {name}')
    if manifest and manifest['config'] != base.CONFIG:
        base.die('Configuration changed after planning; declare a new experiment')
    if manifest and manifest.get('stage_receipt_sha256') != base.sha256(base.OUTPUT / 'stage_receipt.json'):
        base.die('Staging receipt changed after planning')
    return stage


def prepare(phase):
    manifest_path = base.OUTPUT / f'manifest_{phase}.json'
    saved = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    stage = verify_runtime(saved)
    if phase == 'full':
        gate_path = base.OUTPUT / 'analysis/smoke/smoke_passed.json'
        gate = json.loads(gate_path.read_text())
        if gate.get('passed') is not True or gate.get('all_complete') is not True:
            base.die('Both prescribed smoke arms must pass the completed output audit')
        if saved and saved.get('smoke_gate_sha256') != base.sha256(gate_path):
            base.die('Smoke audit changed after full planning')
        base.atomic_json(base.OUTPUT / 'smoke_passed.json', gate)
    if saved:
        return saved
    manifest = base.prepare(phase)
    manifest['stage_receipt_sha256'] = base.sha256(base.OUTPUT / 'stage_receipt.json')
    manifest['engine_fingerprints'] = stage['engine_fingerprints']
    if phase == 'full':
        manifest['smoke_gate_sha256'] = base.sha256(base.OUTPUT / 'analysis/smoke/smoke_passed.json')
    base.atomic_json(manifest_path, manifest)
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'start', 'status'])
    p.add_argument('--phase', choices=['smoke', 'full'], default='smoke')
    args = p.parse_args()
    if args.action == 'prepare':
        value = prepare(args.phase)
    elif args.action == 'start':
        prepare(args.phase)
        value = base.start(args.phase)
    else:
        states = base.status(args.phase)
        value = {arm: {key: state.get(key) for key in
                      ('id', 'status', 'message', 'error', 'output_root', 'pipeline_log_tail')}
                 for arm, state in states.items()}
    print(json.dumps(value, indent=2))


if __name__ == '__main__':
    main()
