"""Managed RFD4 campaign: bounded smoke, then resumable generation/search.

Each model stays resident within its stage. Generator and assessor run in
separate interpreters so their model allocations and AtomWorks registries do
not overlap. The broker owns the execution lease across both stages.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from .contract import atomic, fixed, seal, sha, verify


def refine(config, first=False):
    from .search import execute
    if config['settings']['task'] == 'ligand':
        from .ligand_search import Engine
    else:
        from .search_engine import Engine
        from .msas import resolve
        config = resolve(config)
    output = Path(config['output'])
    starts = json.loads((output / 'generated.json').read_text())
    engine = Engine(config)
    try:
        return execute(config, starts[:1] if first else starts, engine, output, finalize=not first)
    finally:
        engine.close()


def main(config_path):
    path = Path(config_path).resolve()
    config = json.loads(path.read_text())
    output = Path(config['output'])
    if not (output / 'studio_job.json').is_file():
        raise ValueError('Submit this campaign through Studio job_start.')
    done = output / 'completed.json'
    if done.exists():
        verify(done)
        return
    root = Path(os.environ['NANOHUNTER_ROOT'])
    cfg = config['settings']
    script = Path(__file__).resolve().parents[1] / 'rfd4_cli.py'
    if cfg.get('time_budget_minutes'):
        from .budget import run, BudgetExhausted
        def child_stage(action, child_config, child_output):
            result=subprocess.run([sys.executable,'-B',str(script),action,'--root',str(root),
                '--config',str(child_config),'--output',str(child_output)])
            if result.returncode==75: raise BudgetExhausted()
            result.check_returncode()
        return run(path,child_stage)
    search = cfg['search'] != 'native' or cfg['assess_native']
    native = cfg['native_search']
    predictor_python = root / ('venvs/NanoHunter_boltz/bin/python' if cfg['predictor'] == 'boltz'
                              else 'venvs/NanoHunter_esmfold2/bin/python')
    def stage(action, python, first=False):
        from .budget import checkpoint, BudgetExhausted
        checkpoint()
        command = [str(python), '-B', str(script), action, '--root', str(root),
                   '--config', str(path), '--output', str(output)]
        if first: command.append('--first')
        result=subprocess.run(command, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        if result.returncode==75: raise BudgetExhausted()
        result.check_returncode()
    def generate(first=False):
        if cfg['starting_structures']:
            # Import once; these files were copied and fingerprinted at preflight.
            rows = [dict(id=f'seed_{cfg["seed"]+i}', family=f'seed_{cfg["seed"]+i}', seed=cfg['seed']+i,
                         structure=p, structure_sha256=sha(p)) for i, p in enumerate(cfg['starting_structures'])]
            atomic(output / 'generated.json', rows[:1] if first else rows)
            if not first:
                seal(output / 'generation_completed.json', dict(imported=len(rows)),
                     [output / 'generated.json', *cfg['starting_structures']])
        else:
            stage('generate', root / 'venvs/NanoHunter_rfd4/bin/python', first)
    # A completed end-to-end first family is mandatory before a larger cohort.
    # Smoke artifacts are reused by the same immutable full request on resume.
    smoke = output / 'smoke_completed.json'
    if cfg['count'] > 10 and not smoke.exists():
        generate(first=True)
        if search: stage('search', predictor_python, first=True)
        if native: stage('native', root / 'venvs/NanoHunter_rfd4/bin/python', first=True)
        files = list((output / 'candidates').glob('*/completed.json')) if search else []
        if native: files += list((output / 'families').glob('*/final/completed.json'))
        files += list((output / 'generation').glob('*/completed.json'))
        if not files: files = [Path(cfg['starting_structures'][0])]
        seal(smoke, dict(families=1, end_to_end=True), files)
    elif smoke.exists(): verify(smoke)
    generate()
    if search: stage('search', predictor_python)
    elif native: stage('native', root / 'venvs/NanoHunter_rfd4/bin/python')
    else: atomic(output / 'results.json', json.loads((output / 'generated.json').read_text()))
    receipts = [output / 'generation_completed.json', output / 'results.json', path]
    if search: receipts.append(output / 'search_completed.json')
    if native: receipts.append(output / 'native_search_completed.json')
    seal(done, dict(families=cfg['count'], policy=cfg['search']), receipts)
    atomic(output / 'progress.json', dict(stage='completed', completed=cfg['count'], total=cfg['count']))
