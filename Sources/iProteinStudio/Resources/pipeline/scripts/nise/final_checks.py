"""Optional final refolds; never mutate NISE candidates, scores or selection."""
import json
from pathlib import Path
import re
import subprocess
from runtime import atomic


def shortlist(output, limit):
    rows = [json.loads(p.read_text()) for p in (Path(output) / 'candidates').glob('*.json')]
    rows = [r for r in rows if r.get('passed') and r.get('trajectory') is not None
            and r.get('branch') != 'masked-backbone' and r.get('score') is not None
            and re.fullmatch('[ACDEFGHIKLMNPQRSTVWY]+', r.get('sequence', ''))]
    # Repeated observations of the same sequence are not extra independent folds.
    seen, selected = set(), []
    for row in sorted(rows, key=lambda r: (-r['score'], r['name'])):
        if row['sequence'] not in seen:
            selected.append(row); seen.add(row['sequence'])
        if len(selected) == limit: break
    return selected


def run(root, output, settings, smiles):
    root, output = Path(root), Path(output)
    selected = shortlist(output, settings['top_x'])
    target = output / 'final_checks'; inputs = target / 'inputs'
    inputs.mkdir(parents=True, exist_ok=True)
    spec = dict(engines=settings['final_predictors'], candidates=[dict(name=r['name'], sequence=r['sequence'], score=r['score']) for r in selected],
                smiles=smiles, seed=settings['seed'], msa='empty', restrained=False,
                selection='Distinct completed sequences ranked by the recorded NISE objective; final refolds do not rerank the search.')
    manifest = target / 'request.json'
    if manifest.exists() and json.loads(manifest.read_text()) != spec:
        raise ValueError('Final-check shortlist changed; preserve the completed checks and use a new run.')
    atomic(manifest, spec)
    if not selected:
        atomic(target / 'summary.json', dict(status='no_candidates')); return
    for row in selected:
        name = row['name']
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', name): raise ValueError('Unsafe candidate name')
        text = ('version: 1\nsequences:\n  - protein:\n      id: A\n      sequence: ' + row['sequence']
                + '\n      msa: empty\n  - ligand:\n      id: B\n      smiles: ' + json.dumps(smiles) + '\n')
        (inputs / (name + '.yaml')).write_text(text)
    for engine in settings['final_predictors']:
        print('NHSTEP|final-checks|0|Refolding final shortlist with ' + engine, flush=True)
        command = [str(root / 'venvs/NanoHunter_esmfold2/bin/python'), str(root / 'scripts/esmfold2_predict.py'),
                   '--inputs', str(inputs), '--output', str(target / engine), '--nanohunter-root', str(root),
                   '--model', 'fast' if engine == 'esmfold2-fast-mlx' else 'full', '--seeds', str(settings['seed'])]
        with (target / (engine + '.log')).open('a') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    atomic(target / 'summary.json', dict(status='completed', candidates=len(selected), engines=settings['final_predictors']))
