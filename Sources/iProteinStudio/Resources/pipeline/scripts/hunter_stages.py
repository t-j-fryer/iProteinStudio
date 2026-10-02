"""Explicit, checkpointed cycle-00 handoff; existing Hunter owns all refinement.

The supervisor owns this process and its descendants under one execution lease.
Generators finish and release their models before the refinement worker loads.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys

ENGINES = {'boltz', 'intellifold', 'protenix-v2', 'protenix-mini',
           'protenix-constraint-v0.5', 'openfold-3-mlx',
           'esmfold2-fast-mlx', 'esmfold2-full-mlx'}
FLAGS = {'--initialization-method', '--initialization-predictor',
         '--initialization-model', '--initialization-target'}


def value(args, flag, default=None):
    return args[args.index(flag) + 1] if flag in args else default


def replace(args, flag, val=None, boolean=False):
    result = list(args)
    while flag in result:
        i = result.index(flag)
        del result[i:i + (1 if boolean else 2)]
    if val is not None:
        result += [flag] if boolean else [flag, str(val)]
    return result


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.part')
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    tmp.replace(path)


def validate(args):
    for flag in FLAGS:
        if args.count(flag) > 1 or (flag in args and (args.index(flag)+1 == len(args) or args[args.index(flag)+1].startswith('--'))):
            raise ValueError('Missing or repeated stage option: ' + flag)
    method = value(args, '--initialization-method', 'hallucination')
    refine = value(args, '--predictor', 'boltz')
    initial = value(args, '--initialization-predictor', refine)
    if method not in {'hallucination', 'rfd3'}:
        raise ValueError('Starting backbones must use hallucination or rfd3.')
    if refine not in ENGINES or initial not in ENGINES:
        raise ValueError('Choose supported starting and refinement engines.')
    if method == 'hallucination' and initial.startswith('esmfold2-'):
        raise ValueError('ESMFold2 is available for refinement, not X-token initialization. Choose a different starting engine or RFdiffusion3.')
    if method == 'rfd3' and any(flag in args for flag in ['--initialization-predictor', '--initialization-model']):
        raise ValueError('RFdiffusion3 is the starting engine; remove hallucination-only stage options.')
    if method == 'hallucination' and '--initialization-target' in args:
        raise ValueError('--initialization-target is for RFdiffusion3; use --target-template for predictor guidance.')
    if method == 'rfd3' and value(args, '--workflow', 'nanobody') != 'protein':
        raise ValueError('RFdiffusion3 starting backbones require de novo protein design, not a fixed nanobody framework.')
    if any(x in args for x in ['--initial-structure', '--motif-scaffolding', '--partial-redesign', '--initialization-max-attempts']):
        raise ValueError('Separate starting engines cannot be combined with imported seeds, motif or partial redesign.')
    if value(args, '--initialization-model', 'v2-flash') not in {'v2-flash', 'v2'}:
        raise ValueError('Starting IntelliFold model must be v2-flash or v2.')
    return method, initial, refine


def schedule(args, engine):
    for flag in ['--design-scheduler', '--wave-batch-size', '--max-parallel', '--throughput-profile']:
        args = replace(args, flag)
    args += ['--max-parallel', '1', '--throughput-profile', 'off']
    if engine == 'protenix-v2':
        args += ['--design-scheduler', 'cycle-wave']
    else:
        args += ['--design-scheduler', 'resident', '--wave-batch-size', 'all']
    return args


def engine_python(root, engine):
    component = ('esmfold2' if engine.startswith('esmfold2-') else
                 'protenix_constraint' if engine == 'protenix-constraint-v0.5' else
                 'protenix' if engine.startswith('protenix-') else
                 'openfold3_mlx' if engine == 'openfold-3-mlx' else engine)
    return root / 'venvs' / ('NanoHunter_' + component) / 'bin/python'


def verify_handoff(output):
    receipt = json.loads((output / 'initialization.json').read_text())
    if receipt.get('status') != 'complete':
        raise ValueError('Initial backbone generation is not complete.')
    if not receipt.get('files') or receipt.get('trajectories', 0) < 1:
        raise ValueError('Empty starting-backbone checkpoint.')
    for relative, expected in receipt['files'].items():
        if (output / relative).resolve().is_relative_to(output.resolve()) is False:
            raise ValueError('Checkpoint path escapes its run directory.')
        if sha(output / relative) != expected:
            raise ValueError('Starting backbone checkpoint changed: ' + relative)
    return receipt


def main(args):
    method, initial, refine = validate(args)
    root = Path(os.environ.get('NANOHUNTER_ROOT', Path(__file__).parents[1]))
    code = Path(os.environ.get('IPROTEINSTUDIO_PIPELINE_SNAPSHOT', Path(__file__).parents[1]))
    for flag in ['--template-yaml', '--out-root', '--run-name']:
        if not value(args, flag): raise ValueError('Separate stages require ' + flag)
    if '--check-config' not in args:
        subprocess.run([sys.executable, str(Path(__file__)), *args, '--check-config'], check=True)
    output = Path(value(args, '--out-root')) / value(args, '--run-name')
    check_only = '--check-config' in args
    temporary = tempfile.TemporaryDirectory(prefix='hunter-preflight-') if check_only else None
    if temporary: output = Path(temporary.name)
    output.mkdir(parents=True, exist_ok=True)
    count = int(value(args, '--num-runs', '1'))
    if count < 1: raise ValueError('At least one trajectory is required.')
    base = list(args)
    for flag in FLAGS: base = replace(base, flag)
    # Hash original inputs rather than paths alone; never silently regenerate a
    # different start under the same scientific campaign.
    spec = dict(schema=1, method=method, initial_engine=initial if method == 'hallucination' else 'rfd3',
                refinement_engine=refine, trajectories=count,
                arguments=[x for x in args if x != '--resume'],
                template_sha256=sha(value(args, '--template-yaml')),
                target_sha256=sha(value(args, '--initialization-target')) if value(args, '--initialization-target') else None)
    spec_path = output / 'initialization_request.json'
    if spec_path.exists() and json.loads(spec_path.read_text()) != spec:
        raise ValueError('Starting/refinement settings changed. Create a new run.')
    if not spec_path.exists(): atomic(spec_path, spec)
    io_python = root / 'rfd3/.venv/bin/python' if method == 'rfd3' else engine_python(root, initial)
    if not io_python.is_file() or not engine_python(root, refine).is_file():
        raise ValueError('Install both the starting-backbone and refinement engines in Studio first.')
    receipt_path = output / 'initialization.json'
    if check_only:
        if method == 'rfd3':
            subprocess.run([str(io_python), str(code / 'scripts/hunter_initialization_io.py'),
                            'prepare', str(spec_path), str(output / '_initialization/rfd3')], check=True)
        else:
            initial_args = replace(base, '--predictor', initial)
            initial_args = replace(initial_args, '--model', value(args, '--initialization-model', 'v2-flash'))
            subprocess.run(['/bin/bash', str(code / 'nanohunter_run.sh'), *schedule(initial_args, initial)], check=True)
    elif receipt_path.exists():
        verify_handoff(output)
        print('NHSTEP|initialization||Reusing audited starting backbones', flush=True)
    else:
        work = output / '_initialization'
        work.mkdir(exist_ok=True)
        if method == 'hallucination':
            start_args = replace(base, '--out-root', work)
            start_args = replace(start_args, '--run-name', 'hallucination')
            start_args = replace(start_args, '--predictor', initial)
            start_args = replace(start_args, '--model', value(args, '--initialization-model', value(args, '--model', 'v2-flash')))
            start_args = replace(start_args, '--num-opt-cycles', '0')
            start_args = replace(start_args, '--post-predictor', 'none')
            start_args = replace(start_args, '--post-mode', 'none')
            start_args = replace(start_args, '--resume', True, boolean=True)
            start_args = schedule(start_args, initial)
            source = work / 'hallucination'
            source.mkdir(exist_ok=True)
            atomic(source / 'studio_run.json', {'arguments': start_args, 'initialization_only': True})
            print('NHSTEP|initialization||Generating cycle-00 backbones with ' + initial, flush=True)
            subprocess.run(['/bin/bash', str(code / 'nanohunter_run.sh'), *start_args], check=True)
            source = work / 'hallucination'
        else:
            print(f'NHSTEP|initialization||Generating {count} RFdiffusion3 starting backbones', flush=True)
            source = work / 'rfd3'
            subprocess.run([str(io_python), str(code / 'scripts/hunter_initialization_io.py'),
                            'rfd3', str(spec_path), str(source)], check=True)
        print('NHSTEP|handoff||Checking starting coordinates, chain identities and exact trajectory count', flush=True)
        subprocess.run([str(io_python), str(code / 'scripts/hunter_initialization_io.py'),
                        'handoff', str(spec_path), str(source)], check=True)
        verify_handoff(output)
    refinement_template = output / 'refinement_template.yaml'
    subprocess.run([str(io_python), str(code / 'scripts/hunter_initialization_io.py'),
                    'refinement-template', str(spec_path), str(refinement_template)], check=True)
    refine_args = replace(schedule(base, refine), '--template-yaml', refinement_template)
    refine_args = replace(refine_args, '--resume', True, boolean=True)
    # No X-token memory-calibration prediction may reach a sequence-only engine.
    if refine.startswith('esmfold2-'):
        refine_args = replace(refine_args, '--skip-predictor-calibration', True, boolean=True)
    # Generation-only restraints are not silently pretended to apply to an
    # incompatible refinement engine. The stage manifest records this scope.
    if refine not in {'boltz', 'protenix-constraint-v0.5'}:
        refine_args = replace(refine_args, '--target-epitope-residues')
    if refine not in {'boltz', 'protenix-v2', 'intellifold'}:
        for flag in ['--target-template', '--target-template-mode', '--target-template-threshold']:
            refine_args = replace(refine_args, flag)
    if refine == 'esmfold2-fast-mlx':
        refine_args = replace(refine_args, '--target-msa-mode', 'off')
        refine_args = replace(refine_args, '--require-target-msa', boolean=True)
    print(('NHSTEP|preflight||Validating refinement settings for ' if check_only else 'NHSTEP|refinement||Refining cycles 01 onward with ') + refine, flush=True)
    env = dict(os.environ, IPROTEINSTUDIO_HUNTER_HANDOFF=str(output / 'initialization.json'))
    subprocess.run(['/bin/bash', str(code / 'nanohunter_run.sh'), *refine_args], env=env, check=True)
    if temporary: temporary.cleanup()


if __name__ == '__main__':
    try:
        if len(sys.argv) == 3 and sys.argv[1] == 'verify': verify_handoff(Path(sys.argv[2]))
        else: main(sys.argv[1:])
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit('Protein Hunter stage error: ' + str(exc))
