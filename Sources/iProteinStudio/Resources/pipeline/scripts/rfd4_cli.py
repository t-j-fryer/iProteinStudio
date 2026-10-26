#!/usr/bin/env python3
"""Studio's typed RFD4 entry point; generation requires a managed broker job."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['validate', 'author', 'audit', 'audit-starts', 'generate', 'search', 'native', 'oracle', 'run'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--first', action='store_true')
    args = parser.parse_args()
    from rfd4.contract import normalize, prediction_budget
    if args.action == 'validate':
        cfg = normalize(json.loads(args.config.read_text()))
        print(json.dumps(dict(settings=cfg, predictions=prediction_budget(cfg))))
    elif args.action == 'author':
        from rfd4.prepare import author
        author(args.root, json.loads(args.config.read_text()), args.output)
    elif args.action == 'audit':
        from rfd4.prepare import audit_features
        cfg = normalize(json.loads(args.config.read_text()))
        audit_features(args.output / 'annotated.cif', cfg, args.output / 'feature_audit.json')
    elif args.action == 'audit-starts':
        from rfd4.prepare import audit_features
        cfg = normalize(json.loads(args.config.read_text()))
        for index, path in enumerate(cfg['starting_structures']):
            if Path(path).suffix.lower() != '.cif':
                raise ValueError('Native search requires annotated CIF starting structures.')
            audit_features(Path(path), cfg, args.output / f'start_{index:05d}_audit.json')
    elif args.action == 'generate':
        from rfd4.generate import main as generate
        generate(args.config, first_only=args.first)
    elif args.action == 'search':
        from rfd4.campaign import refine
        refine(json.loads(args.config.read_text()), first=args.first)
    elif args.action == 'native':
        from rfd4.native import main as native
        native(args.config, first_only=args.first)
    elif args.action == 'oracle':
        from rfd4.native_scorer import main as oracle
        oracle(args.config)
    else:
        from rfd4.campaign import main as run
        run(args.config)


if __name__ == '__main__':
    from rfd4.budget import BudgetExhausted
    try: main()
    except BudgetExhausted:
        print('Design time reached; saved atomic outputs remain available.',flush=True)
        raise SystemExit(75)
