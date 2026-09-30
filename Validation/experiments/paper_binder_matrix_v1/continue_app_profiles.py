"""Fork a campaign at a scientific-profile change; never alter old raw units.

Keep the original instrumented engine implementations and measured optimizations
for timing continuity. Resolve budgets from the app's versioned shared profiles.
The broker still owns the execution lease, provenance and runtime bindings.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parents[3]
ALIASES = dict(boltz='boltz', intellifold_flash='intellifold', openfold3='openfold-3-mlx',
               protenix_mini='protenix-mini', protenix_v2='protenix-v2',
               protenix_constraint='protenix-constraint-v0.5',
               esmfold2_full='esmfold2-full-mlx', esmfold2_fast='esmfold2-fast-mlx')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8 << 20), b''): h.update(chunk)
    return h.hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def compatible(measurement, settings):
    return (not measurement['warmup'] and not measurement['diagnostic']
            and measurement['steps'] == settings['diffusion_steps']
            and measurement['recycles'] == settings['recycles'])


def main():
    old = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve()
    old_plan = json.loads((old / 'plan.json').read_text())
    preserved = Path(old_plan['prepared_runtime_view']['path'])
    assert preserved.is_dir(), 'Original preserved runtime is required.'
    cfg = json.loads((old / 'frozen/config.json').read_text())
    profiles_path = REPO / 'Sources/iProteinStudio/Resources/pipeline/scripts/prediction_profiles.json'
    profiles = json.loads(profiles_path.read_text())
    for engine, spec in cfg['engines'].items():
        settings = profiles[ALIASES[engine]]
        spec['reduced'] = settings['diffusion_steps']
        spec['recycles'] = settings['recycles']
        if engine == 'esmfold2_fast': spec['full'] = settings['diffusion_steps']
    assert all(t['rows'] <= 128 and sha(t['msa']) == t['msa_sha256'] for t in cfg['targets'].values())
    cfg.update(output=str(out), app_prediction_profiles=profiles,
               app_profiles_sha256=sha(profiles_path), continued_from=str(old),
               preserved_instrumented_runtime=str(preserved))
    cfg['protocol'] = ('App profile v1: target MSA128, binder query-only. Mini5/4; ESMFull100/20; '
                       'ESMFast sequence-only50/3; other models25 steps/native recycles. '
                       'Same seed42, one sample, no templates/restraints, Boltz potentials off.')
    cfg['esm_native_schedule_note'] = ('Full100 and Fast50 are requested native sampler steps; '
                                       'the upstream schedule truncation remains unchanged.')
    cfg['selection']['scope'] = 'App-profile continuation of the preserved instrumented benchmark.'
    out.mkdir(parents=True, exist_ok=False)
    frozen = out / 'frozen'
    shutil.copytree(old / 'frozen', frozen, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(profiles_path, frozen / 'app_prediction_profiles.json')
    shutil.copy2(__file__, frozen / 'continue_app_profiles.py')
    # Separate runner so the frozen original worker uses exactly its original
    # adapters and profiling hooks, independent of later app installations.
    launcher = frozen / 'launch_continuation.py'
    launcher.write_text('import json, os, runpy, sys\nfrom pathlib import Path\n'
                        'c=json.loads(Path(sys.argv[1]).read_text())\n'
                        'os.environ["NANOHUNTER_ROOT"]=c["preserved_instrumented_runtime"]\n'
                        'runpy.run_path(str(Path(__file__).with_name("run.py")), run_name="__main__")\n')
    imports = []
    for engine, variant in cfg['arms']:
        origin = old / (engine + '__' + variant)
        dest = out / origin.name
        dest.mkdir()
        measurements = []
        seen = set()
        for receipt_path in sorted(origin.glob('*/complete.json')):
            mpath = receipt_path.with_name('measurement.json')
            m = json.loads(mpath.read_text())
            if not compatible(m, profiles[ALIASES[engine]]): continue
            receipt = json.loads(receipt_path.read_text())
            assert all(Path(p).is_file() and sha(p) == h for p, h in receipt['files'].items())
            key = (m['design_name'], m['seed'])
            assert key not in seen, ('Duplicate completed unit', engine, key)
            seen.add(key)
            unit = dest / receipt_path.parent.name
            unit.mkdir()
            for name in ('complete.json', 'measurement.json'):
                (unit / name).symlink_to(receipt_path.parent / name)
            measurements.append(str(unit / 'measurement.json'))
            imports.append(dict(engine=engine, design_name=m['design_name'], seed=m['seed'],
                                source=str(receipt_path), receipt_sha256=sha(receipt_path)))
        if len(measurements) == len(cfg['selected_rows']) * len(cfg['seeds']):
            save(dest / 'completed.json', dict(outputs=measurements, reused_from=str(origin)))
        if measurements and (origin / 'sessions').is_dir():
            (dest / 'sessions').mkdir()
            for load in (origin / 'sessions').glob('*/load.json'):
                target = dest / 'sessions' / ('original_' + load.parent.name)
                target.mkdir(); (target / 'load.json').symlink_to(load)
    save(frozen / 'config.json', cfg)
    save(frozen / 'selection.json', cfg['selection'])
    save(frozen / 'imported_units.json', imports)
    root = Path.home() / '.iproteinstudio'
    os.environ['NANOHUNTER_ROOT'] = str(root)
    sys.path.insert(0, str(root / 'mcp'))
    from server import MCPServer
    save(out / 'workflow_guide.json', MCPServer('read').tool_call('workflow_guide', {'workflow': 'prediction'}))
    from iprotein_mcp.plans import _persist, _script_provenance
    command = ['/usr/bin/env', 'PYTHONDONTWRITEBYTECODE=1', 'PYTORCH_ENABLE_MPS_FALLBACK=0',
               'OMP_NUM_THREADS=4', 'VECLIB_MAXIMUM_THREADS=4', 'MKL_NUM_THREADS=4', 'KMP_USE_SHM=0',
               'HF_HUB_OFFLINE=1', 'TRANSFORMERS_OFFLINE=1', 'TOKENIZERS_PARALLELISM=false',
               '/usr/bin/caffeinate', '-dimsu', str(root / 'components/control/current/python/bin/python3'),
               str(launcher), str(frozen / 'config.json')]
    normalized = dict(workflow='runtime_benchmark', engines=list(cfg['engines']),
                      runtime_python_paths=[e['python'] for e in cfg['engines'].values()],
                      output=str(out), msa_policy=cfg['protocol'], scheduler=cfg['scheduler'],
                      steps=[dict(stage='app-profile-continuation', command=command, cwd=str(out))])
    files = [p for p in frozen.rglob('*') if p.is_file()]
    files += [p for p in (preserved / 'scripts').rglob('*.py')]
    files += [Path(t['msa']) for t in cfg['targets'].values()]
    plan = _persist('desktop_runtime_benchmark', 'paper-binder-matrix', normalized,
                    command, 'apple_gpu_exclusive', _script_provenance(files))
    assert plan['runtime_bindings'] == old_plan['runtime_bindings'], 'Runtime versions changed; review before starting.'
    save(out / 'plan.json', plan)
    print(json.dumps(dict(id=plan['id'], sha256=plan['sha256'], imported=len(imports), output=str(out))))


if __name__ == '__main__': main()
