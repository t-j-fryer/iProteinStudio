#!/usr/bin/env python3
"""Atomic motif beta workbench; inference entry is owned by Studio's broker."""
import argparse
import json
from pathlib import Path
from motif_beta.contract import atomic, catalog, prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('catalog')
    for name in ('prepare', '_managed-run'):
        p = sub.add_parser(name); p.add_argument('--config', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('freeze-root')
    for key in ('bundle', 'structure', 'metadata', 'output'): p.add_argument('--' + key, type=Path, required=True)
    p = sub.add_parser('templates')
    p.add_argument('--reference', type=Path, required=True); p.add_argument('--sequence', required=True)
    p.add_argument('--engine', required=True); p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('source-guide')
    p.add_argument('--case', required=True); p.add_argument('--mapping', type=Path, required=True)
    p.add_argument('--sequence', required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--structure', type=Path, help='Optional native PDB/mmCIF with original chain/residue IDs; otherwise use released motif residues.')
    p = sub.add_parser('designers')
    for key in ('reference', 'structure', 'ccd-cache', 'output'): p.add_argument('--' + key, type=Path, required=True)
    p = sub.add_parser('chemistry-audit'); p.add_argument('--ccd-cache', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('score')
    for key in ('reference', 'prediction', 'output'): p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--protein-plddt', type=float, required=True)
    p.add_argument('--guided', action='store_true')
    p = sub.add_parser('score-input-motif')
    for key in ('reference', 'structure', 'output'): p.add_argument('--' + key, type=Path, required=True)
    p = sub.add_parser('select'); p.add_argument('--candidates', type=Path, required=True)
    p.add_argument('--policy', choices=['greedy', 'beam'], required=True); p.add_argument('--width', type=int, default=4)
    p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'catalog': print(json.dumps(catalog(), indent=2))
    elif args.command == 'prepare': prepare(args.output, json.loads(args.config.read_text()))
    elif args.command == '_managed-run':
        from motif_beta.runner import run
        run(args.config, args.output)
    elif args.command == 'freeze-root':
        from motif_beta.geometry import freeze_root
        freeze_root(args.bundle, args.structure, json.loads(args.metadata.read_text()), args.output)
    elif args.command == 'templates':
        from motif_beta.templates import prepare as template
        template(args.reference, args.sequence, args.engine, args.output)
    elif args.command == 'source-guide':
        from motif_beta.source_guide import prepare as source_guide
        source_guide(args.case, json.loads(args.mapping.read_text()), args.sequence, args.output, structure=args.structure)
    elif args.command == 'designers':
        from motif_beta.designers import prepare as designers
        designers(args.reference, args.structure, args.ccd_cache, args.output)
    elif args.command == 'chemistry-audit':
        from motif_beta.designers import chemistry_audit
        atomic(args.output, {c['case_id']: chemistry_audit(c, args.ccd_cache) for c in catalog()['cases']})
    elif args.command == 'score':
        from motif_beta.geometry import evaluate
        atomic(args.output, evaluate(args.reference, args.prediction, args.protein_plddt, guided=args.guided))
    elif args.command == 'score-input-motif':
        from motif_beta.geometry import input_motif_report
        atomic(args.output, input_motif_report(args.reference, args.structure))
    elif args.command == 'select':
        from motif_beta.search import advance
        atomic(args.output, advance(args.policy, json.loads(args.candidates.read_text()), args.width))


if __name__ == '__main__': main()
