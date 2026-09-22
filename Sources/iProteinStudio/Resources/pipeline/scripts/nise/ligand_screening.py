#!/usr/bin/env python3
"""Optional campaign-wide NESSO shortlist followed by structural verification.

Protein Hunter supplies completed optimized cycles; RFD3 supplies MPNN rows.
Ranking is sequence screening, never a replacement for structural confidence.
Run through Studio's broker, which freezes this config and holds the GPU lease.
"""
from __future__ import annotations
import argparse
import os
import csv
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

from nesso_contract import RANKING_POLICY, installation, placement_score, validate_scores
from nesso_screen import NessoClient
from runtime import Journal, atomic, digest

PREDICTORS = {'boltz': 'boltz', 'intellifold': 'intellifold',
              'protenix_mini': 'protenix-mini', 'protenix_v2': 'protenix-v2', 'openfold3': 'openfold-3-mlx'}


def options(value):
    if not isinstance(value, dict) or value.get('enabled') is not True:
        raise ValueError('NESSO screening must be explicitly enabled.')
    from screening_registry import descriptor
    engine = value.get('engine', 'nesso'); descriptor(engine)
    top = value.get('topK')
    if type(top) is not int or not 1 <= top <= 100000:
        raise ValueError('NESSO shortlist size must be an integer from 1 to 100,000.')
    predictor = value.get('predictor')
    if predictor not in PREDICTORS:
        raise ValueError('Unsupported NESSO verification predictor.')
    model = value.get('intellifoldModel', 'v2-flash')
    if model not in {'v2-flash', 'v2'}:
        raise ValueError('Unsupported IntelliFold checkpoint.')
    return dict(enabled=True, engine=engine, topK=top, predictor=predictor, intellifoldModel=model)


def candidates(source, workflow):
    """One entry per independent cycle/MPNN derivative, including repeated sequences."""
    result = {}
    with Path(source).open(newline='') as stream:
        reader = csv.DictReader(stream)
        expected = {'run', 'cycle', 'binder_sequence'} if workflow == 'iterative' else {'design', 'seq_index', 'sequence'}
        if not expected.issubset(reader.fieldnames or []):
            raise ValueError('Candidate CSV is missing required identity/sequence columns.')
        for row in reader:
            if workflow == 'iterative':
                # Accept both numerical and canonical run_001/cycle_01 fields.
                run = row['run'].removeprefix('run_')
                cycle = row['cycle'].removeprefix('cycle_')
                if not run.isdigit() or not cycle.isdigit():
                    raise ValueError('Invalid Protein Hunter run/cycle identity.')
                if int(cycle) == 0:
                    continue
                name = f'run_{int(run):03d}_cycle_{int(cycle):02d}'
                sequence = row['binder_sequence'].strip()
                origin = dict(run=row['run'], cycle=row['cycle'])
            elif workflow == 'rfdiffusion3':
                name = row['design'] + '_' + row['seq_index']
                sequence = row['sequence'].strip()
                origin = dict(backbone=row['design'], derivative=row['seq_index'])
            else:
                raise ValueError('Unknown ligand screening workflow.')
            if not re.fullmatch(r'[A-Za-z0-9_-]+', name) or name in result:
                raise ValueError('Duplicate or unsafe candidate identity: ' + name)
            if not re.fullmatch(r'[ACDEFGHIKLMNPQRSTVWY]+', sequence):
                raise ValueError('Invalid or masked optimized sequence: ' + name)
            result[name] = dict(sequence=sequence, origin=origin)
    if not result:
        raise ValueError('No completed, unmasked designs are available for NESSO screening.')
    return result


def csv_report(path, rows):
    fields = ['candidate', 'sequence', 'origin', 'selected', 'pbind', 'interface_entropy',
              'full_pl_entropy', 'screening_score', 'eligible', 'rejection_reason', 'ranking_policy']
    if rows and 'predicted_binding_affinity' in rows[0]:
        fields += ['predicted_binding_affinity', 'predicted_antagonist', 'predicted_nonbinder', 'predicted_agonist']
    temp = path.with_suffix('.csv.part')
    with temp.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    temp.replace(path)


def run(config, *, client_class=NessoClient, predictor_run=subprocess.run):
    cfg = json.loads(Path(config).read_text())
    opts = options(cfg['options'])
    from screening_registry import contract as scorer_contract, client as scorer_client
    engine = opts['engine']; module = scorer_contract(engine)
    RANKING_POLICY = module.RANKING_POLICY; placement_score = module.placement_score
    validate_scores = module.validate_scores; installation = module.installation
    if engine == 'psichic' and client_class is NessoClient: client_class = scorer_client(engine)
    if not isinstance(cfg.get('smiles'), str) or not cfg['smiles'] or any(c.isspace() for c in cfg['smiles']) or "'" in cfg['smiles']:
        raise ValueError('Supply a single ligand SMILES without whitespace or quote characters.')
    root = Path(os.environ.get('NANOHUNTER_ROOT',cfg['root']) if json.loads(os.environ.get('IPROTEINSTUDIO_RUNTIME_BINDINGS','{}')) else cfg['root']).resolve()
    output = Path(cfg['output']).resolve()
    output.mkdir(parents=True, exist_ok=True)
    journal = Journal(output)
    source = Path(cfg['source'])
    entries = candidates(source, cfg['workflow'])
    spec = dict(config=cfg, source_sha256=digest(source), candidates=entries, ranking=dict(RANKING_POLICY))
    begin = output / 'inputs.json'
    if journal.load(begin, spec) is None:
        journal.save(begin, spec, True)
    # Audit earlier completed folds before spending time on more inference.
    complete = output / 'completed.json'
    if journal.load(complete, spec) is not None:
        return json.loads((output / 'results.json').read_text())
    if engine == 'psichic':
        from psichic_screen import score_candidates
        worker_holder = []
        def factory():
            if not worker_holder: worker_holder.append(client_class(root, output, cfg['scripts'], 0))
            return worker_holder[0]
        try:
            scores = score_candidates({n:v['sequence'] for n,v in entries.items()}, cfg['smiles'], output/'scores', journal, factory, root, 0)
        finally:
            for worker in worker_holder: worker.close()
    else:
        scores = {}; worker = None
        try:
            for name, entry in entries.items():
                unit = output / 'scores' / name
                score_spec = dict(sequence=entry['sequence'], smiles=cfg['smiles'], seed=0,
                                  installation_sha256=digest(installation(root) / 'receipt.json'),
                                  protocol='nesso-v1.0.0-mps-float32-refined-5')
                receipt = unit / 'completed.json'
                saved = journal.load(receipt, score_spec)
                if saved is None:
                    if worker is None:
                        worker = client_class(root, output, cfg['scripts'], 0)
                    saved = worker.score(entry['sequence'], cfg['smiles'], unit)
                    validate_scores(saved['scores'])
                    journal.save(receipt, score_spec, saved, [p for p in unit.rglob('*') if p.is_file() and p != receipt])
                scores[name] = validate_scores(saved['scores'])
                print(f'NHSTEP|nesso-screen|0|NESSO screened {name}', flush=True)
        finally:
            if worker is not None:
                worker.close()
    assessments = {name: placement_score(score) for name, score in scores.items()}
    selected = sorted((name for name in entries if assessments[name]['eligible']),
                      key=lambda name: (-assessments[name]['score'], name))[:opts['topK']]
    selection = dict(ranking=dict(RANKING_POLICY), selected=selected, scores=scores, assessments=assessments)
    receipt = output / 'selection.json'
    prior = journal.load(receipt, spec)
    if prior is None:
        journal.save(receipt, spec, selection, [output / 'scores' / name / 'completed.json' for name in entries])
    elif prior != selection:
        raise RuntimeError('NESSO ranking differs from the recorded shortlist.')
    csv_report(output / (engine + '_screening.csv'), [dict(candidate=name, sequence=entry['sequence'],
        origin=json.dumps(entry['origin'], sort_keys=True), selected=name in selected,
        pbind=scores[name].get('affinity_probability_binary', scores[name].get('binding_probability_proxy')), interface_entropy=scores[name].get('entropy_crop_pl'),
        full_pl_entropy=scores[name].get('entropy_pl'), screening_score=assessments[name]['score'],
        eligible=assessments[name]['eligible'], rejection_reason=assessments[name]['rejection_reason'],
        ranking_policy=RANKING_POLICY['version'], **({k:scores[name][k] for k in module.SCALARS} if engine == 'psichic' else {})) for name, entry in entries.items()])
    if not selected:
        raise RuntimeError('NESSO rejected every placement; see nesso_screening.csv. No structures were folded.')

    runner = Path(cfg['predictor_runner'])
    predictor = PREDICTORS[opts['predictor']]
    folds = output / 'folds'
    pending = []; results = []
    # Receipts, not opportunistically discovered CIFs, determine safe reuse.
    fold_spec = dict(options=opts, smiles=cfg['smiles'], ranking=dict(RANKING_POLICY),
                     runner_sha256=digest(runner), msa='empty', restrained=False)
    for name in selected:
        unit_spec = dict(**fold_spec, candidate=name, sequence=entries[name]['sequence'])
        saved = journal.load(output / 'fold_receipts' / (name + '.json'), unit_spec)
        if saved is not None:
            results.append(saved)
        else:
            pending.append(name)
    if pending:
        print(f'NHSTEP|nesso-verification|0|Folding {len(pending)} NESSO-selected sequences with {predictor}', flush=True)
        import uuid
        inputs = output / 'prediction_inputs' / uuid.uuid4().hex
        inputs.mkdir(parents=True)
        for name in pending:
            # The shared runner's MSA guard reads explicit YAML fields. Quote
            # SMILES with YAML single quotes, preserving backslashes through
            # the OpenFold adapter as well as full YAML parsers.
            query = ('version: 1\nsequences:\n  - protein:\n      id: A\n      sequence: '
                     + json.dumps(entries[name]['sequence']) + '\n      msa: empty\n'
                     + "  - ligand:\n      id: B\n      smiles: '" + cfg['smiles'] + "'\n")
            (inputs / (name + '.yaml')).write_text(query)
            stale = folds / predictor / name
            if stale.exists():
                quarantine = output / 'interrupted_folds' / uuid.uuid4().hex
                quarantine.parent.mkdir(exist_ok=True)
                shutil.move(str(stale), str(quarantine))
        command = [sys.executable, str(runner), '--inputs', str(inputs), '--output', str(folds),
                   '--predictors', predictor, '--max-parallel', '4', '--intellifold-model', opts['intellifoldModel'],
                   '--nanohunter-root', str(root)]
        atomic(output / 'prediction_command.json', dict(command=command, pending=pending))
        previous_metrics = folds / 'prediction_metrics.csv'
        if previous_metrics.exists():
            history = output / 'prediction_history'
            history.mkdir(exist_ok=True)
            shutil.move(str(previous_metrics), str(history / (uuid.uuid4().hex + '.csv')))
        with (output / 'prediction.log').open('a') as log:
            completed = predictor_run(command, stdout=log, stderr=subprocess.STDOUT)
        metrics_path = folds / 'prediction_metrics.csv'
        rows = []
        if metrics_path.exists():
            with metrics_path.open(newline='') as stream:
                rows = list(csv.DictReader(stream))
        seen = set()
        for row in rows:
            name = row.get('design')
            if name not in pending or name in seen or row.get('predictor') != predictor:
                raise RuntimeError('Unexpected or duplicate verification result identity.')
            seen.add(name)
            if row.get('exit_code') != '0':
                continue
            artifacts = []
            for key in ('structure', 'confidence_json'):
                path = Path(row.get(key) or '').resolve()
                if folds not in path.parents or not path.is_file() or path.stat().st_size == 0:
                    raise RuntimeError('Missing or unsafe verification artifact: ' + key)
                artifacts.append(path)
            json.loads(artifacts[1].read_text())
            structural = {}
            for key in ('iptm', 'ptm', 'plddt', 'complex_plddt', 'confidence_score', 'ligand_iptm'):
                if row.get(key):
                    value = float(row[key])
                    if not math.isfinite(value):
                        raise RuntimeError('Nonfinite structural confidence: ' + name)
                    structural[key] = value
            result = dict(candidate=name, **entries[name], predictor=predictor, intellifold_model=opts['intellifoldModel'],
                          structure=str(artifacts[0].relative_to(output)), confidence_json=str(artifacts[1].relative_to(output)),
                          screening_engine=engine, screening={**scores[name], 'screening_score': assessments[name]['score']},
                          ranking_policy=dict(RANKING_POLICY), structure_scores=structural)
            result[engine] = result['screening']
            unit_spec = dict(**fold_spec, candidate=name, sequence=entries[name]['sequence'])
            journal.save(output / 'fold_receipts' / (name + '.json'), unit_spec, result, artifacts + [inputs / (name + '.yaml')])
            results.append(result)
        if completed.returncode or len(results) != len(selected):
            atomic(output / 'results.json', sorted(results, key=lambda r: selected.index(r['candidate'])))
            raise RuntimeError('Shortlist verification is incomplete; successful folds were checkpointed. See prediction.log.')
    results.sort(key=lambda r: selected.index(r['candidate']))
    atomic(output / 'results.json', results)
    # Include nested artifacts, so even a completed invocation is audited on resume.
    files = [output / 'results.json', output / (engine + '_screening.csv'), receipt, begin]
    files += [p for p in (output / 'scores').rglob('*') if p.is_file()]
    for name in selected:
        fold_receipt = output / 'fold_receipts' / (name + '.json')
        files.append(fold_receipt)
        files += [output / rel for rel in json.loads(fold_receipt.read_text())['files']]
    journal.save(complete, spec, True, files)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    run(parser.parse_args().config)
