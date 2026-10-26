"""Typed RFD4 preflight shared by the native form and MCP clients."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from .common import StudioError, import_artifact, load_json, project_root, runtime_root, validate_slug
from .memory import memory_request
from .plans import _persist, _script_provenance


def contract():
    path = Path(__file__).resolve().parents[2] / 'scripts/rfd4/contract.py'
    spec = importlib.util.spec_from_file_location('studio_rfd4_contract', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(output, request):
    root, output, module = runtime_root(), Path(output), contract()
    try:
        cfg = module.normalize(request)
        original = dict(cfg)
        module.fixed(output / 'requested_settings.json', original)
        inputs = []
        if cfg['source']:
            for name in ('target_prediction.json', 'target_prediction_config.json'):
                sidecar = Path(cfg['source']).parent / name
                if sidecar.is_file(): inputs.append(Path(import_artifact(str(sidecar))['path']))
        for key in ('source', 'target_msa', 'scaffold_msa'):
            if cfg[key] and cfg[key] not in ('empty', 'auto'):
                cfg[key] = import_artifact(cfg[key])['path']
                inputs.append(Path(cfg[key]))
        cfg['starting_structures'] = [import_artifact(p)['path'] for p in cfg['starting_structures']]
        inputs += [Path(p) for p in cfg['starting_structures']]
        module.fixed(output / 'settings.json', cfg)
        python = root / 'venvs/NanoHunter_rfd4/bin/python'
        runner = root / 'scripts/rfd4_cli.py'
        search = cfg['search'] != 'native' or cfg['assess_native'] or cfg['native_search']
        engines = [] if cfg['starting_structures'] and not cfg['native_search'] else ['rfd4']
        required = [] if not engines else [python, root / 'components/rfd4/current/runtime.json']
        if not cfg['starting_structures']:
            for sub in ('transformer', 'vae'):
                required.append(root / 'models/rfd4/diffusers' / sub / 'diffusion_pytorch_model.safetensors')
            required += sorted((root / 'models/rfd4/diffusers').rglob('*.json'))
        if cfg['native_search']:
            required += [root / 'models/rfd4/native' / name for name in ('model.safetensors', 'config.json')]
        if search:
            engines += ['boltz' if cfg['task'] == 'ligand' else cfg['predictor']]
            family = 'boltz' if cfg['predictor'] == 'boltz' or cfg['task'] == 'ligand' else 'esmfold2'
            required.append(root / f'venvs/NanoHunter_{family}/bin/python')
            if cfg['search'] != 'native':
                engines += [cfg['sequence_model']]
                if cfg['task'] == 'ligand':
                    required += [root / 'venvs/NanoHunter_lasermpnn/bin/python',
                                 root / 'src/LASErMPNN/model_weights/laser_weights_0p1A_nothing_heldout.pt']
                else:
                    required += [root / 'venvs/NanoHunter_ligandmpnn/bin/python', root / 'src/LigandMPNN/run.py',
                             root / 'src/LigandMPNN/model_params' / {
                                 'solublempnn':'solublempnn_v_48_020.pt', 'proteinmpnn':'proteinmpnn_v_48_020.pt',
                                 'abmpnn':'abmpnn.pt'}[cfg['sequence_model']]]
            # The selected portable runtime's model directory is preserved by
            # runtime_view; fingerprint its model receipts and files as well.
            models = root / ('models/boltz2' if family == 'boltz' else 'models/esmfold2')
            required += [p for p in models.rglob('*') if p.is_file()]
            if cfg['task'] == 'ligand':
                required.append(root / 'models/boltz2/boltz2_aff.ckpt')
            if cfg['target_msa'] == 'auto':
                engines += ['boltz']
                required.append(root / 'venvs/NanoHunter_boltz/bin/boltz')
        if cfg['scaffold_id']:
            required += [root / 'examples/nanobody_scaffolds/structures' / (cfg['scaffold_id'] + '.pdb'),
                         root / 'examples/nanobody_scaffolds/structures/PROVENANCE.json',
                         root / 'examples/nanobody_scaffolds/msas' / cfg['scaffold_id'] / 'full_msa.a3m']
        for path in required + [runner]:
            if not path.is_file(): raise ValueError('Install the required RFD4/search component: ' + str(path))
        if not cfg['starting_structures']:
            receipt = output / 'preflight_completed.json'
            if receipt.exists(): module.verify(receipt)
            else:
                for action in ('author', 'audit'):
                    result = subprocess.run([str(python), '-B', str(runner), action, '--root', str(root),
                        '--config', str(output / 'settings.json'), '--output', str(output)],
                        capture_output=True, text=True, timeout=300)
                    (output / (action + '.log')).write_text(result.stdout + result.stderr)
                    if result.returncode: raise ValueError('RFD4 ' + action + ' failed: ' + result.stderr[-2000:])
                module.seal(receipt, dict(passed=True), [output / 'settings.json', output / 'annotated.cif',
                            output / 'condition_spec.json', output / 'feature_audit.json',
                            *[output / name for name in ('molecule.json', 'molecule.cif', 'reference.cif', 'protein_source.cif', 'framework_identity.json', 'target_identity.json') if (output / name).is_file()]])
            inputs += [output / name for name in ('annotated.cif', 'condition_spec.json', 'feature_audit.json', 'preflight_completed.json')]
            inputs += [output / name for name in ('molecule.json', 'molecule.cif', 'reference.cif', 'protein_source.cif', 'framework_identity.json') if (output / name).is_file()]
        elif cfg['native_search']:
            receipt = output / 'preflight_completed.json'
            audits = [output / f'start_{i:05d}_audit.json' for i in range(cfg['count'])]
            if receipt.exists(): module.verify(receipt)
            else:
                result = subprocess.run([str(python), '-B', str(runner), 'audit-starts', '--root', str(root),
                    '--config', str(output / 'settings.json'), '--output', str(output)],
                    capture_output=True, text=True, timeout=300 * cfg['count'])
                (output / 'audit-starts.log').write_text(result.stdout + result.stderr)
                if result.returncode: raise ValueError('RFD4 imported input audit failed: ' + result.stderr[-2000:])
                module.seal(receipt, dict(passed=True), [output / 'settings.json', *cfg['starting_structures'], *audits])
            inputs += [receipt, *audits]
        config = dict(settings=cfg, output=str(output), annotated_cif=str(output / 'annotated.cif'))
        identity = output / 'target_identity.json'
        if cfg['task'] in ('protein', 'nanobody') and not identity.is_file():
            sys.path.insert(0, str(root / 'rfd3_scripts'))
            from protein_structure import read_protein_atoms
            expected = None
            for source in cfg['starting_structures'] or [output / 'annotated.cif']:
                sequences = {}
                for atom in read_protein_atoms(source):
                    if atom.atom == 'CA' and atom.chain != cfg['binder_chain']:
                        sequences[atom.chain] = sequences.get(atom.chain, '') + module.residue_letter(atom.residue)
                if not sequences: raise ValueError('Every input needs explicit target chains distinct from the binder.')
                if expected is not None and expected != sequences:
                    raise ValueError('Imported families must share the same target chains and sequences.')
                expected = sequences
            module.fixed(identity, dict(chains=[dict(sequence=seq, output_chain=c, native_chain=c) for c, seq in expected.items()]))
        if identity.is_file():
            target = load_json(identity)
            if 'chains' in target:
                config['target_sequences'] = {row['output_chain']: row['sequence'] for row in target['chains']}
                config['target_native_chains'] = {row['output_chain']: row.get('native_chain', row['output_chain']) for row in target['chains']}
            else:
                config['target_sequence'] = target['sequence']
            if len(config.get('target_sequences', {})) > 1 and cfg['target_msa'] not in ('auto', 'empty', ''):
                raise ValueError('Multiple target chains require automatic per-chain MSAs or explicit single-sequence mode.')
            inputs.append(identity)
        module.fixed(output / 'rfd4_config.json', config)
        controller = python if not cfg['starting_structures'] or cfg['native_search'] else root / (
            'venvs/NanoHunter_boltz/bin/python' if cfg['predictor'] == 'boltz' else 'venvs/NanoHunter_esmfold2/bin/python')
        command = [str(controller), '-B', str(runner), 'run', '--root', str(root),
                   '--config', str(output / 'rfd4_config.json'), '--output', str(output)]
        scripts = sorted((root / 'scripts').rglob('*.py')) + sorted((root / 'rfd3_scripts').rglob('*.py'))
        provenance = _script_provenance(list(dict.fromkeys(scripts + inputs + required +
                      [output / 'rfd4_config.json', output / 'requested_settings.json', output / 'settings.json'])))
        context = dict(request=cfg, supporting_engines=engines,
                       prediction_budget=dict(maximum_structure_predictions=module.prediction_budget(cfg)),
                       scheduler=('active-time budget; sequential families; resident search within each family; atomic operation boundaries'
                                  if cfg['time_budget_minutes'] else 'resident stages; batch 1 generation; 25-family cycle waves; sequential CPU sequence design'))
        return dict(steps=[dict(command=command, cwd=str(root), stage='rfd4')], **context), provenance
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        raise StudioError(str(exc)) from exc


@memory_request
def plan(request):
    unknown = set(request) - {'project', 'run_name', 'request'}
    if unknown: raise StudioError('Unknown RFD4 plan fields: ' + ', '.join(sorted(unknown)))
    project = validate_slug(request.get('project', ''))
    name = validate_slug(request.get('run_name', ''), 'run name')
    output = project_root(project) / 'rfd4_runs' / name
    output.mkdir(parents=True, exist_ok=True)
    context, provenance = prepare(output, request.get('request', {}))
    normalized = dict(output=str(output), workflow='rfd4', **context)
    return _persist('desktop_rfd4', project, normalized, context['steps'][0]['command'],
                    'apple_gpu_exclusive', provenance)
