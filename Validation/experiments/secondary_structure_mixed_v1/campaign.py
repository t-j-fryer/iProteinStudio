#!/usr/bin/env python3
"""Bounded mixed-prior pilot through Studio's immutable plan and job bridge."""
import argparse
import importlib.util
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('secondary_prior_base', HERE.parent / 'secondary_structure_priors_v1/campaign.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.CONFIG = json.loads((HERE / 'config.json').read_text())
base.OUTPUT = base.ROOT / 'Validation/output/secondary_structure_mixed_v1'
base.PROJECT = 'validation_secondary_structure_mixed_v1'
base.RUNTIME = Path(os.environ.get('NANOHUNTER_ROOT', str(Path.home() / '.iproteinstudio')))
original_arguments = base.arguments_for

def mixed_arguments(arm, trajectories):
    args = original_arguments({'mode': 'none'}, trajectories)
    return args + ['--secondary-bias', 'mixed', '--secondary-bias-scope', arm['scope'],
                   '--anti-helix-strength', str(arm['anti_helix_strength']),
                   '--beta-strength', '0.50', '--beta-pattern-strength', '0.50', '--turn-strength', '0.50']

base.arguments_for = mixed_arguments

def prepare():
    previous = json.loads((base.ROOT / 'Validation/output/secondary_structure_priors_v1/manifest_full.json').read_text())
    for path, key in [('nanohunter_run.sh', 'runner_sha256'), ('scripts/secondary_structure_control.py', 'secondary_helper_sha256')]:
        if base.sha256(base.RUNTIME / path) != previous['runtime'][key]:
            base.die('Scientific implementation changed since controls; do not silently compare across versions')
    path = base.OUTPUT / 'manifest_smoke.json'
    if path.exists():
        manifest = json.loads(path.read_text())
        if manifest['config'] != base.CONFIG:
            base.die('Declared pilot settings changed after planning')
        return manifest
    return base.prepare('smoke')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'start', 'status'])
    args = parser.parse_args()
    if args.action == 'prepare': result = prepare()
    elif args.action == 'start':
        prepare()
        result = base.start('smoke')
    else: result = base.status('smoke')
    print(json.dumps(result, indent=2))

if __name__ == '__main__': main()
