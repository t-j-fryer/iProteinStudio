#!/usr/bin/env python3
"""Execute a prospectively declared sequence-only search round via Studio plans.

A declaration is never overwritten or inferred from successful outputs. Every
plan preserves X initialization and validates the prior scientific implementation.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('secondary_search_base', HERE.parent / 'secondary_structure_priors_v1/campaign.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
BASE_ARGUMENTS = base.arguments_for


def configure(path):
    declaration = json.loads(path.read_text())
    if declaration.get('initialization') != {'binder_percent_x': 50, 'binder_structure': None}:
        base.die('Search requires exactly 50% X initialization and no binder structure')
    if not 1 <= declaration['campaign']['smoke_trajectories'] <= 10:
        base.die('Each search round is bounded to 1-10 trajectories per declared arm')
    base.CONFIG = declaration
    base.RUNTIME = Path(os.environ.get('NANOHUNTER_ROOT', str(Path.home() / '.iproteinstudio'))).resolve()
    base.OUTPUT = base.ROOT / 'Validation/output/secondary_structure_search_v1' / declaration['round']
    base.PROJECT = 'validation_ss_search_' + declaration['round']
    def arguments(arm, trajectories):
        args = BASE_ARGUMENTS({'mode': 'none'}, trajectories)
        if arm['mode'] != 'none':
            args += ['--secondary-bias', arm['mode'], '--secondary-bias-scope', arm['scope'],
                     '--anti-helix-strength', str(arm['anti_helix_strength']),
                     '--beta-strength', str(arm['beta_strength']),
                     '--beta-pattern-strength', str(arm['beta_pattern_strength']),
                     '--turn-strength', str(arm['turn_strength'])]
        args += ['--ligand-temp-cycle1', str(arm.get('temperature_cycle1', .30)),
                 '--ligand-temp-other', str(arm.get('temperature_other', .10))]
        return args
    base.arguments_for = arguments
    return declaration


def prepare(declaration):
    reference = json.loads((base.ROOT / 'Validation/output/secondary_structure_priors_v1/manifest_full.json').read_text())
    for name, key in [('nanohunter_run.sh', 'runner_sha256'), ('scripts/secondary_structure_control.py', 'secondary_helper_sha256')]:
        if base.sha256(base.RUNTIME / name) != reference['runtime'][key]:
            base.die('Scientific implementation differs from baseline; declare a versioned comparison first')
    # Check the actual mask default rather than assuming the declaration changes
    # a flag that the immutable bridge does not expose.
    import re
    runner = (base.RUNTIME / 'nanohunter_run.sh').read_text()
    if not re.search(r'^BINDER_PERCENT_X=50$', runner, re.M):
        base.die('The recorded runner no longer has the required 50% X default')
    manifest = base.OUTPUT / 'manifest_smoke.json'
    if manifest.exists():
        saved = json.loads(manifest.read_text())
        if saved['config'] != declaration:
            base.die('Round declaration changed after planning; create a new round')
        return saved
    if not declaration.get('hypothesis') or not declaration.get('decision_rule'):
        base.die('A hypothesis and decision rule must be declared before planning')
    return base.prepare('smoke')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'start', 'status'])
    p.add_argument('--declaration', type=Path, required=True)
    args = p.parse_args()
    declaration = configure(args.declaration)
    if args.action == 'prepare': result = prepare(declaration)
    elif args.action == 'start':
        prepare(declaration)
        result = base.start('smoke')
    else: result = base.status('smoke')
    print(json.dumps(result, indent=2))

if __name__ == '__main__': main()
