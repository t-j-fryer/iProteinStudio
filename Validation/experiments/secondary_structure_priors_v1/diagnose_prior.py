#!/usr/bin/env python3
"""Compare the saved beta grammar with observed sequences and P-SEA assignments."""
import argparse
import csv
import importlib.util
import json
import math
from pathlib import Path
import statistics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    rows = list(csv.DictReader((root / 'analysis/audited_per_structure.csv').open()))
    summary = {}
    for arm in ['beta_seed_only', 'beta_seed_and_cycles']:
        measured = []
        for row in rows:
            if row['arm'] != arm or int(row['cycle']) == 0: continue
            run = root / 'campaigns' / ('full__' + arm) / row['run']
            plan = json.loads((run / 'secondary_structure_plan.json').read_text())
            records = {int(item['cycle']): item for item in csv.DictReader((run / 'metrics_per_cycle.csv').open())}
            sequence = records[int(row['cycle'])]['binder_sequence']
            strands = [p['index'] - 1 for p in plan['positions'] if p['region'] == 'strand']
            turns = [p['index'] - 1 for p in plan['positions'] if p['region'] == 'turn']
            measured.append({
                'planned_turn_fraction': len(turns) / 90,
                'beta_favoured_aa_in_planned_strands': sum(sequence[i] in 'VITFYW' for i in strands) / len(strands),
                'gly_pro_in_planned_strands': sum(sequence[i] in 'GP' for i in strands) / len(strands),
                'observed_sheet_at_planned_strands': sum(row['psea'][i] == 'b' for i in strands) / len(strands),
                'observed_helix_at_planned_strands': sum(row['psea'][i] == 'a' for i in strands) / len(strands),
                'observed_coil_at_planned_turns': sum(row['psea'][i] == 'c' for i in turns) / len(turns),
            })
        assert len(measured) == 50
        summary[arm] = {key: statistics.mean(r[key] for r in measured) for key in measured[0]}
    report = {'unit': '10 complete trajectories per arm, each averaged over cycles 01-05; equal cardinality', 'measured': summary,
              'analytical_antihelix_odds_multiplier_vs_unbiased_residue': {
                  'definition': 'exp(-1.2 * strength / temperature), holding backbone logits and other biases fixed; not measured sequence frequencies',
                  'strength_0_5_temperature_0_3': math.exp(-1.2 * .5 / .3),
                  'strength_0_5_temperature_0_1': math.exp(-1.2 * .5 / .1)}}
    (root / 'analysis/prior_diagnostics.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__': main()
