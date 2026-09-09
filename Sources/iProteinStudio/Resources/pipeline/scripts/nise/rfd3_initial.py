"""RFdiffusion3 initial backbones for the existing ligand-NISE funnel.

Reuse Studio's ligand preparation, official Foundry fixtures and MLX generator.
Generation finishes before LASErMPNN/Boltz; no inference happens at preflight.
"""
import csv
import json
import math
import os
from pathlib import Path
import subprocess
import uuid

from runtime import atomic, digest


def lengths(settings):
    low, high = settings['binder_min_len'], settings['binder_max_len']
    count = min(settings['rfd3_num_bins'], settings['num_starts'], high - low + 1)
    if count == 1:
        return [(low + high) // 2]
    return [low + math.floor(i * (high - low) / (count - 1) + 0.5) for i in range(count)]


def run(command, log, cwd, env):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('a') as stream:
        stream.write('\n' + json.dumps([str(p) for p in command]) + '\n'); stream.flush()
        result = subprocess.run([str(p) for p in command], cwd=cwd, env=env,
                                stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        tail = '\n'.join(log.read_text(errors='replace').splitlines()[-15:])
        raise RuntimeError(f'RFdiffusion3 failed; see {log}\n{tail}')


def generate(backend, smiles, directory):
    cfg, root = backend.settings, backend.root / 'rfd3'
    manifest = backend.atom_manifest(smiles)
    smiles = manifest['smiles_used']
    directory.mkdir(parents=True, exist_ok=True)
    work = directory / 'rfd3_initial'
    spec = dict(method='rfdiffusion3', smiles=smiles, starts=cfg['num_starts'],
                lengths=lengths(cfg), seed=cfg['seed'], steps=200, recycles=2,
                precision='bf16', batch_size=8, queues_per_bin=2,
                ligand_conformers=1, atom_signature=manifest['signature'],
                hotspot_atoms=cfg.get('hotspot_atoms', []), exposed_atoms=cfg.get('exposed_atoms', []),
                resume_protocol='audited-batches-v1')
    spec_path = directory / 'generation.json'
    if spec_path.exists() and json.loads(spec_path.read_text()) != spec:
        raise RuntimeError('Saved RFdiffusion3 generation settings changed')
    if not spec_path.exists():
        atomic(spec_path, spec)
    receipt = directory / 'initial_backbones.json'
    saved = backend.journal.load(receipt, spec)
    if saved is not None:
        return {name: str(backend.output / path) for name, path in saved.items()}
    python = root / '.venv/bin/python'
    env = dict(os.environ, DEBUG='false', TOKENIZERS_PARALLELISM='false',
               STUDIO_RFD3_AUDIT_RESUME='1', PYTORCH_ENABLE_MPS_FALLBACK='0')
    prep_receipt = directory / 'preparation.json'
    prepared = backend.journal.load(prep_receipt, spec)
    if prepared is None:
        # Preparation has no committed output until all fixtures succeed. Keep
        # interrupted raw outputs, and regenerate rather than trust partial NPZs.
        if work.exists():
            work.rename(directory / ('interrupted_preparation_' + uuid.uuid4().hex))
        work.mkdir()
        ligand_spec = work / 'ligand_spec.json'
        atomic(ligand_spec, dict(smiles=smiles))
        assets = work / 'assets'
        run([python, root / 'scripts/prepare_ligand_target.py', '--spec', ligand_spec,
             '--component-id', 'NIS', '--output-dir', assets, '--seed', cfg['seed'],
             '--base-json', work / 'ligand_base.json', '--design-name', 'nise_initial'],
            work / 'logs/ligand.log', root, env)
        # Map by the shared standardized SMILES input order, not canonical rank
        # numbers from potentially different RDKit builds. Retain both maps.
        names = atom_translation(work / 'assets', manifest)
        to_rfd3 = {boltz: rfd3 for rfd3, boltz in names.items()}
        atomic(work / 'atom_translation.json', names)
        design = {'nise_initial': {'input': str(assets / 'NIS.pdb'), 'ligand': 'NIS',
                  'select_fixed_atoms': {'NIS': 'ALL'}, 'infer_ori_strategy': 'com',
                  'redesign_motif_sidechains': False}}
        for field, selected in (('select_hotspots', spec['hotspot_atoms']), ('select_exposed', spec['exposed_atoms'])):
            if selected:
                design['nise_initial'][field] = {'NIS': ','.join(to_rfd3[name] for name in selected)}
        atomic(work / 'design.yaml', design)  # JSON is valid YAML; no quoting ambiguity.
        run(design_command(root, work, spec, 'fixtures'), work / 'logs/fixtures.log', root, env)
        files = [p for p in work.rglob('*') if p.is_file() and p.suffix != '.log']
        backend.journal.save(prep_receipt, spec, {'prepared': True}, files)
    atomic(backend.output / 'progress.json', dict(message=f"Generating {cfg['num_starts']} RFdiffusion3 backbones"))
    run(design_command(root, work, spec, 'backbones'), work / 'logs/backbones.log', root, env)
    paths = sorted((work / 'rfd3/backbones').glob('design_*.pdb'))
    if len(paths) != cfg['num_starts']:
        raise RuntimeError(f'Expected {cfg["num_starts"]} RFdiffusion3 backbones, found {len(paths)}')
    atoms = set(json.loads((work / 'assets/atom_selections.json').read_text())['all_heavy_atoms'])
    names = atom_translation(work / 'assets', manifest)
    lineages = {}
    for index, path in enumerate(paths):
        # The existing generator exports binder A / ligand B. Keep its ligand
        # atom names so LASErMPNN and NISE compare the same atom correspondence.
        n = len(backend.science.ca_coords_chain(path, 'A'))
        if n not in spec['lengths']:
            raise RuntimeError('RFdiffusion3 backbone length differs from the recorded bins')
        backend.audit_structure(path, 'X' * n, True)
        ligand_atoms = [line[12:16].strip() for line in path.read_text().splitlines()
                        if line.startswith('HETATM') and line[21] == 'B']
        if len(ligand_atoms) != len(atoms) or set(ligand_atoms) != atoms:
            raise RuntimeError('RFdiffusion3 ligand atoms differ from the prepared molecule')
        name = f'L{index:03d}'
        target = directory / (name + '_ref.pdb')
        backend.science.patch_unk_pdb(path, target)
        lines = target.read_text().splitlines()
        target.write_text('\n'.join(line[:12] + names[line[12:16].strip()].rjust(4) + line[16:]
                                   if line.startswith('HETATM') and line[21] == 'B' else line
                                   for line in lines) + '\n')
        from ligand_atoms import audit_atoms
        audit_atoms(target, manifest)
        lineages[name] = str(target.relative_to(backend.output))
    files = [p for p in work.rglob('*') if p.is_file() and p.suffix != '.log']
    files += [backend.output / path for path in lineages.values()] + [spec_path, prep_receipt]
    backend.journal.save(receipt, spec, lineages, files)
    return {name: str(backend.output / path) for name, path in lineages.items()}


def design_command(root, work, spec, stage):
    return [root / '.venv/bin/python', root / 'scripts/design_from_yaml.py', work / 'design.yaml',
            '--name', 'nise_initial', '--output', work, '--num-designs', spec['starts'],
            '--lengths', ','.join(map(str, spec['lengths'])), '--seed-base', spec['seed'],
            '--timesteps', spec['steps'], '--n-recycle', spec['recycles'],
            '--precision', spec['precision'], '--batch-size', spec['batch_size'],
            '--queues-per-bin', spec['queues_per_bin'], '--ccd-mirror', work / 'assets/ccd',
            '--stage', stage]


def atom_translation(assets, manifest):
    prepared = json.loads((assets / 'atom_selections.json').read_text())
    if prepared['smiles'] != manifest['smiles_used']:
        raise ValueError('RFdiffusion3 and Boltz ligand chemical states differ.')
    with (assets / 'atom_map.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    expected = manifest['atoms']
    if len(rows) != len(expected) or [int(r['rdkit_index']) for r in rows] != list(range(len(expected))):
        raise ValueError('RFdiffusion3 ligand input-order map is incomplete or reordered.')
    if len({r['atom_name'] for r in rows}) != len(rows) or any(r['element'].upper() != a['el'].upper() for r, a in zip(rows, expected)):
        raise ValueError('RFdiffusion3 ligand atom elements or identities changed.')
    return {r['atom_name']: a['name'] for r, a in zip(rows, expected)}
