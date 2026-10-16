"""Freeze the optional desktop ligand screening stage before campaign submission."""
from pathlib import Path
import importlib.util
import json
import shutil
import sys

from .common import StudioError


def prepare(root, output, workflow, value, smiles, *, detected=None, preparation_root=None, prediction_settings=None):
    from .prediction_settings import normalize
    profiles = normalize(prediction_settings)
    root, output = Path(root), Path(output)
    module_dir = root / 'scripts/nise'
    sys.path.insert(0, str(module_dir))
    try:
        spec = importlib.util.spec_from_file_location('studio_ligand_screening', module_dir / 'ligand_screening.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        opts = module.options(value)
        from screening_registry import contract as scorer_contract
        selected = scorer_contract(opts['engine'])
        selected.validate_installation(root)
        assets = list(selected.installation_files(root))
    except (ValueError, OSError) as exc:
        raise StudioError(str(exc)) from exc
    finally:
        sys.path.remove(str(module_dir))
    if not isinstance(smiles, str) or not smiles.strip() or any(c.isspace() for c in smiles.strip()) or "'" in smiles:
        raise StudioError('Experimental screening needs the ligand SMILES, without a name or whitespace.')
    if workflow not in {'iterative', 'rfdiffusion3'}:
        raise StudioError('Experimental screening is restricted to ligand design campaigns.')
    if detected is None:
        from .catalog import detect_engines
        detected = detect_engines()['engines']
    required = [opts['predictor']]
    if opts['predictor'].startswith('protenix_'):
        required.append('protenix')
    if opts['predictor'] == 'intellifold' and opts['intellifoldModel'] == 'v2':
        required.append('intellifold_full')
    missing = [key for key in required if detected.get(key, {}).get('state') != 'ok']
    if missing:
        raise StudioError('Install or repair Screening verification components before running: ' + ', '.join(missing))
    stage = output / 'nesso_verification'
    prepared = Path(preparation_root) if preparation_root else stage
    prepared.mkdir(parents=True, exist_ok=True)
    snapshot = prepared / 'runtime'
    if not snapshot.exists():
        temp = prepared / 'runtime.part'
        if temp.exists():
            shutil.rmtree(temp)
        for source_root, relative in ((root / 'scripts', Path('scripts')),
                                      (root / 'rfd3_overlay/scripts', Path('predictors'))):
            for source in source_root.rglob('*'):
                if not source.is_file() or source.suffix not in ('.py','.json'): continue
                target = temp / relative / source.relative_to(source_root)
                target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
        # Pinned source patches and installation protocol, never model weights.
        shutil.copytree(root / 'scripts/nise/nesso_assets', temp / 'scripts/nise/nesso_assets', dirs_exist_ok=True)
        if not (temp / 'predictors/run_predictors.py').is_file():
            raise StudioError('The shared predictor adapters have not been staged. Repair the app runtime.')
        temp.rename(snapshot)
    # Engine source/model bytes are provenance, not copied into the campaign.
    family = {'boltz': 'boltz2', 'intellifold': 'intellifold', 'protenix_v2': 'protenix',
              'protenix_mini': 'protenix', 'openfold3': 'openfold3',
              'esmfold2_full': 'esmfold2', 'esmfold2_fast': 'esmfold2'}[opts['predictor']]
    model_root = root / 'models' / family
    if family == 'boltz2':
        model_paths = [model_root / 'boltz2_conf.ckpt', model_root / 'mols']
    elif family == 'intellifold':
        model_paths = [model_root / ('intellifold_v2.pt' if opts['intellifoldModel'] == 'v2' else 'intellifold_v2_flash.pt'), model_root / 'ccd_v2.pkl']
    elif family == 'protenix':
        checkpoint = 'protenix-v2.pt' if opts['predictor'] == 'protenix_v2' else 'protenix_mini_default_v0.5.0.pt'
        model_paths = [model_root / 'checkpoint' / checkpoint, model_root / 'common']
    elif family == 'esmfold2':
        model_paths = [model_root]
    else:
        model_paths = [model_root / 'of3_ft3_v1.pt']
    for path in model_paths:
        assets += [p for p in path.rglob('*') if p.is_file()] if path.is_dir() else [path]
    source_family = {'boltz2': 'boltz', 'intellifold': 'IntelliFold', 'protenix': 'Protenix', 'openfold3': 'openfold-3-mlx', 'esmfold2': 'esmfold2'}[family]
    assets += list((root / 'src' / source_family).rglob('*.py'))
    venv = root / 'venvs' / ('NanoHunter_' + {'boltz2': 'boltz', 'openfold3': 'openfold3_mlx'}.get(family, family))
    assets += [venv / 'bin/python']
    package = {'boltz2': 'boltz', 'openfold3': 'openfold'}.get(family, family)
    assets += list((venv / 'lib').glob('python*/site-packages/' + package + '/**/*.py'))
    assets += list((root / 'scripts').rglob('*.py'))
    assets += [p for p in snapshot.rglob('*') if p.is_file() and p.suffix in ('.py','.json')]
    assets += [p for p in (snapshot / 'scripts/nise/nesso_assets').iterdir() if p.is_file()]
    from .plans import _script_provenance
    from hashlib import sha256
    dependencies = _script_provenance(sorted(set(assets)))
    dependency_digest = sha256(json.dumps(dependencies, sort_keys=True).encode()).hexdigest()
    config = dict(version=1, prediction_settings=profiles, root=str(root), output=str(stage), workflow=workflow, options=opts,
                  source=str(output / ('summary_all_runs.csv' if workflow == 'iterative' else 'mpnn/sequences.csv')),
                  smiles=smiles.strip(), scripts=str(snapshot / 'scripts'),
                  predictor_runner=str(snapshot / 'predictors/run_predictors.py'))
    config['dependency_digest'] = dependency_digest
    path = prepared / 'config.json'
    if path.exists():
        if json.loads(path.read_text()) != config:
            raise StudioError('The recorded screening settings or dependencies changed. Create a new campaign to change its shortlist or model.')
    else:
        temp = path.with_suffix('.json.part'); temp.write_text(json.dumps(config, indent=2) + '\n'); temp.replace(path)
    assets += [path]
    return ({'command': ['/usr/bin/caffeinate', '-dimsu', sys.executable,
                        str(snapshot / 'scripts/nise/ligand_screening.py'), '--config', str(path)],
             'cwd': str(snapshot), 'stage': 'nesso-verification'}, assets)


def frozen_preparation(root, output, workflow, options, smiles, *, prediction_settings=None):
    """Prepare the same native verification route without creating campaign outputs."""
    from .common import agent_root, canonical_digest
    import fcntl
    from .prediction_settings import normalize
    profiles = normalize(prediction_settings)
    identity = canonical_digest(dict(output=str(output), workflow=workflow, options=options, smiles=smiles, prediction_settings=profiles))
    destination = agent_root() / 'ligand_preparations' / identity
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / 'prepare.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        step, assets = prepare(root, output, workflow, options, smiles, preparation_root=destination, prediction_settings=profiles)
    return {"directory": str(destination), "step": step}, assets


def template_smiles(root, path):
    """Read the saved ligand identity with the managed YAML parser, never infer it."""
    import subprocess
    command = [str(Path(root)/'venvs/NanoHunter_boltz/bin/python'), '-B', '-c',
        'import yaml,json,sys;d=yaml.safe_load(open(sys.argv[1]));'
        'print(json.dumps([v["ligand"].get("smiles") for v in d["sequences"] if "ligand" in v]))', str(path)]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
        ligands = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise StudioError('Cannot inspect ligand identity with the managed Boltz YAML parser.') from exc
    if len(ligands) != 1 or not isinstance(ligands[0], str) or not ligands[0].strip():
        raise StudioError('Ligand verification requires exactly one explicit SMILES ligand in the input template.')
    return ligands[0]
