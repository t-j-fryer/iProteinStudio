"""Shared admission for prediction plans, including native submissions."""
import importlib.util
import hashlib
import json
import subprocess
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from .common import StudioError, runtime_root


POLICY = ContextVar('studio_memory_policy', default='enforce')


def requested_policy(request=None):
    value = (request or {}).get('memory_policy', POLICY.get())
    if value not in ('enforce', 'override'):
        raise StudioError('memory_policy must be enforce or override.')
    return value


def memory_request(function):
    """Scope an explicit choice to this plan and its nested planners."""
    @wraps(function)
    def wrapped(request, *args, **kwargs):
        token = POLICY.set(requested_policy(request))
        try:
            return function({k: v for k, v in request.items() if k != 'memory_policy'}, *args, **kwargs)
        finally:
            POLICY.reset(token)
    return wrapped


def contract():
    bridge = Path(__file__).resolve().parents[1]
    support = bridge / 'runtime_support'
    if not support.is_dir():
        support = bridge.parent / 'scripts'
    path = support / 'memory_admission.py'
    spec = importlib.util.spec_from_file_location('studio_memory_admission', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_template(path):
    """Parse YAML in an installed CPU interpreter; do not import model packages."""
    text = Path(path).read_text()
    try:
        return json.loads(text)  # YAML's JSON subset; also useful for offline tests.
    except ValueError:
        pass
    interpreters = [runtime_root() / 'venvs' / name / 'bin/python' for name in
                    ('NanoHunter_boltz', 'NanoHunter_protenix', 'NanoHunter_intellifold', 'NanoHunter_esmfold2')]
    for python in interpreters:
        if python.is_file():
            try:
                result = subprocess.run([str(python), '-c',
                    'import json,sys,yaml; print(json.dumps(yaml.safe_load(sys.stdin.read())))'],
                    input=text, capture_output=True, text=True, timeout=15)
                if result.returncode == 0:
                    return json.loads(result.stdout)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                continue
    raise StudioError('The protein template could not be read for the memory check. Repair the selected engine in Setup.')


def iterative_configs(normalized):
    manifest = normalized.get('manifest', {})
    args = normalized.get('arguments') or manifest.get('arguments', [])
    def option(name, default=None):
        return args[args.index(name)+1] if name in args else default
    if option('--initialization-method') == 'rfd3':
        raise StudioError('RFdiffusion3 memory estimates are not yet qualified. This run is blocked by the memory check.')
    path = normalized.get('template_artifact', {}).get('path') or option('--template-yaml')
    if not path:
        raise StudioError('The saved design has no protein template for its memory check.')
    document = read_template(path)
    maximum = int(option('--binder-max-len', 150))
    if not 1 <= maximum <= 916:
        raise StudioError('The requested binder length is outside the memory profile range (1–916 residues).')
    chains = []
    for item in document.get('sequences', []):
        if set(item) != {'protein'}:
            raise StudioError('Memory estimates currently cover protein-only design. Ligand design is not yet qualified.')
        protein = item['protein']
        ids = protein.get('id')
        ids = ids if isinstance(ids, list) else [ids]
        for chain_id in ids:
            sequence = protein.get('sequence', '')
            if chain_id == 'A' and (option('--workflow', 'protein') != 'nanobody' or '--random-binder' in args):
                sequence = 'X' * maximum
            chains.append(dict(id=chain_id, kind='protein', sequence=sequence, msa=protein.get('msa', 'auto')))
    # Some de-novo templates have only target chains; include the generated binder.
    if not any(c['id'] == 'A' for c in chains):
        chains.insert(0, dict(id='A', kind='protein', sequence='X'*maximum, msa='empty'))
    engine = option('--predictor', 'boltz')
    model = option('--model', 'v2-flash')
    def variant(predictor, selected_model):
        return 'intellifold-full' if predictor == 'intellifold' and selected_model == 'v2' else predictor
    initial_model = option('--initialization-model', model)
    engines = [variant(option('--initialization-predictor', engine), initial_model), variant(engine, model)]
    checkers = option('--post-predictor', 'intellifold' if option('--workflow') == 'nanobody' else 'none')
    engines += [variant(e, model) for e in checkers.split(',') if e != 'none']
    parallel = option('--max-parallel', '1')
    if parallel == 'auto':
        raise StudioError('Select an explicit worker count before checking design memory. Calibration cannot safely discover an oversized first prediction.')
    guidance = any(flag in args for flag in ('--target-template', '--boltz-use-potentials', '--motif-scaffolding', '--partial-redesign', '--helix-kill'))
    guidance = guidance or bool(document.get('constraints')) or bool(document.get('templates'))
    # Match the runner's automatic Boltz partner potentials; absence of an
    # explicit flag does not mean this is an unrestrained prediction.
    if 'boltz' in engines and len(chains) > 1 and '--boltz-no-potentials' not in args:
        guidance = True
    samples = option('--predictor-samples', 'auto')
    base = dict(jobs=[dict(name='largest-design-complex', chains=chains)],
                max_parallel=int(parallel), batch_size=1,
                diffusion_samples=0 if samples == 'auto' else int(samples),
                intellifold_model='v2-flash',  # Variants above are explicit per stage.
                prediction_settings=json.loads(option('--prediction-settings-json', '{}')),
                use_potentials=guidance)
    return [{**base, 'predictors':list(dict.fromkeys(engines)), 'memory_scope':'resident-design'}]


def configs_for_plan(kind, normalized):
    if kind == 'desktop_motif_beta':
        if normalized.get('request', {}).get('stage') == 'prepare':
            return []  # Exact file preparation loads no model.
        raise StudioError('Atomic motif beta inference uses RFdiffusion3 and ligand complexes, whose memory profiles are not yet qualified. Prepare inputs remains available; no model has been loaded.')
    if kind in {'iterative_design', 'desktop_iterative'}:
        return iterative_configs(normalized)
    if kind == 'iterative_batch':
        return [cfg for child in normalized['children'] for cfg in configs_for_plan(
            child['plan']['kind'], child['plan']['normalized_request'])]
    if kind == 'desktop_iterative_batch':
        return [cfg for child in normalized['engine_campaigns'] for cfg in iterative_configs(child)]
    if kind == 'desktop_rfd4':
        raise StudioError('RFD4 memory estimates are not yet qualified. Choose the explicit memory override to run RFD4.')
    if kind.startswith('rfd3_') or kind == 'desktop_rfdiffusion3' or kind.startswith('desktop_nise'):
        raise StudioError('Memory estimates for RFdiffusion3 and ligand NISE are not yet qualified. '
                          'This run is blocked by the memory check; no model has been loaded.')
    if kind not in {'prediction', 'target_prepare', 'desktop_prediction', 'desktop_target_prepare'}:
        return []
    config = normalized.get('config')
    if config is None:
        # Older plans did not embed their native config; provenance is verified
        # by load_plan before dispatch. Never exempt them from the new check.
        config = json.loads((Path(normalized['output']) / 'prediction_config.json').read_text())
    return [config]


def check_plan(kind, normalized, live=False):
    policy = requested_policy(normalized)
    module = contract()
    try:
        configs = normalized.get('memory_workloads') or configs_for_plan(kind, normalized)
    except StudioError as exc:
        if policy != 'override':
            raise
        result = dict(policy=module.DATA['policy'], profile_sha256=module.PROFILE_SHA256,
                      contract_sha256=module.CONTRACT_SHA256, status='blocked',
                      estimated_gib=None, message=str(exc), details=[])
    else:
        if not configs:
            return None
        machine = module.machine_memory(live)
        results = [module.assess({**cfg, 'memory_policy': 'enforce'}, machine=machine, live=live)
                   for cfg in configs]
        blocked = [r for r in results if r['status'] == 'blocked']
        result = dict(blocked[0] if blocked else max(results, key=lambda r: r['estimated_gib'] or 0), stages=results)
        if result['status'] == 'blocked' and policy != 'override':
            raise StudioError(result['message'])
    return {**module.apply_policy(result, policy),
            'planner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def check_saved_plan(plan):
    result = check_plan(plan['kind'], plan['normalized_request'])
    if result is not None:
        saved = plan['normalized_request'].get('memory_admission', {})
        if any(saved.get(key) != result[key] for key in ('profile_sha256','contract_sha256','planner_sha256')):
            raise StudioError('This saved job predates the current memory protection. Create a new checked plan for its saved inputs before resuming; completed outputs were kept.')
    return result
