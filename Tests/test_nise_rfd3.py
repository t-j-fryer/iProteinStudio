"""Execute the RFdiffusion3 adapter and generator with model-boundary fixtures.

Ligand preparation uses real RDKit and the shipped script. No neural inference.
"""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / 'Sources/iProteinStudio/Resources/rfd3_overlay'
sys.path.insert(0, str(ROOT / 'Sources/iProteinStudio/Resources/pipeline/scripts/nise'))
sys.path.insert(0, str(OVERLAY / 'scripts'))
os.environ.setdefault('NANOHUNTER_ROOT', str(ROOT))
import contract
import rfd3_initial
from runtime import Backend
from test_rfd3_target_export import load_writer


class RFD3IntegrationTests(unittest.TestCase):
    def test_adapter_prepares_real_ligand_resumes_and_audits_handoff(self):
        self.exercise_adapter(False)

    def test_selected_hotspots_and_exposure_reach_diffusion_and_survive_resume(self):
        self.exercise_adapter(True)

    def exercise_adapter(self, conditioned):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            scripts = root / 'rfd3/scripts'; scripts.mkdir(parents=True)
            shutil.copy2(OVERLAY / 'scripts/prepare_ligand_target.py', scripts)
            (root / 'rfd3/.venv').symlink_to(sys.prefix, target_is_directory=True)
            output = root / 'campaign'; output.mkdir()
            cfg = contract.normalize(dict(smiles='CCO', num_starts=2, trajectories=2,
                binder_min_len=65, binder_max_len=65, backbone_method='rfdiffusion3'))
            if conditioned:
                from ligand_atoms import resolve
                mapping = resolve('CC[NH3+]')
                cfg.update(smiles='CC[NH3+]', hotspot_atoms=[mapping['atoms'][0]['name']],
                           exposed_atoms=[mapping['atoms'][-1]['name']], ligand_atom_signature=mapping['signature'],
                           ligand_atoms_generated_for='CC[NH3+]')
            backend = Backend(root, output, cfg, scripts)
            directory = output / 'phase0/cycle00'
            calls = []
            interrupted = True
            real_run = rfd3_initial.run
            def child(command, log, cwd, env):
                nonlocal interrupted
                calls.append([str(x) for x in command])
                if str(command[1]).endswith('prepare_ligand_target.py'):
                    return real_run(command, log, cwd, env)
                self.assertEqual(env['STUDIO_RFD3_AUDIT_RESUME'], '1')
                work = Path(command[command.index('--output') + 1])
                stage = command[command.index('--stage') + 1]
                if stage == 'fixtures':
                    path = work / 'rfd3/fixtures/fixture.npz'
                    path.parent.mkdir(parents=True); np.savez(path, fixture=np.zeros(1))
                    return
                if interrupted:
                    interrupted = False
                    raise RuntimeError('injected generation interruption')
                self.assertEqual(command[command.index('--num-designs') + 1], 2)
                backbones = work / 'rfd3/backbones'; backbones.mkdir()
                ligand = (work / 'assets/NIS.pdb').read_text().splitlines()
                ligand = [line[:21] + 'B' + line[22:] for line in ligand if line.startswith('HETATM')]
                for index in range(1, 3):
                    lines = [f'ATOM  {i:5d}  CA  ALA A{i:4d}    {i*3.8:8.3f}{0.:8.3f}{0.:8.3f}  1.00 90.00           C'
                             for i in range(1, 66)] + ligand + ['END']
                    (backbones / f'design_{index:04d}.pdb').write_text('\n'.join(lines) + '\n')
            with patch.object(rfd3_initial, 'run', side_effect=child):
                with self.assertRaisesRegex(RuntimeError, 'injected generation'):
                    backend.initial_backbones(cfg['smiles'], directory, None)
                result = backend.initial_backbones(cfg['smiles'], directory, None)
                self.assertEqual(set(result), {'L000', 'L001'})
                self.assertEqual(len(calls), 4)  # ligand, fixtures, interrupted generation, resumed generation
                self.assertEqual(backend.initial_backbones(cfg['smiles'], directory, None), result)
                self.assertEqual(len(calls), 4)
                document = json.loads((directory / 'rfd3_initial/design.yaml').read_text())['nise_initial']
                self.assertNotIn('contig', document)
                self.assertNotIn('select_buried', document)
                self.assertEqual(document['select_fixed_atoms'], {'NIS': 'ALL'})
                if conditioned:
                    translation = json.loads((directory / 'rfd3_initial/atom_translation.json').read_text())
                    self.assertEqual(translation[document['select_hotspots']['NIS']], cfg['hotspot_atoms'][0])
                    self.assertEqual(translation[document['select_exposed']['NIS']], cfg['exposed_atoms'][0])
                    ligand = json.loads((directory / 'rfd3_initial/assets/atom_selections.json').read_text())
                    self.assertEqual(ligand['smiles'], 'CCN')
                else:
                    self.assertNotIn('select_hotspots', document)
                    self.assertNotIn('select_exposed', document)
                Path(result['L000']).write_text('corrupted')
                with self.assertRaisesRegex(RuntimeError, 'missing or changed'):
                    backend.initial_backbones(cfg['smiles'], directory, None)

    def test_generator_keeps_weights_across_batches_and_skips_loading_on_replay(self):
        module = load_writer()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = root / 'fixture.npz'; fixture.write_bytes(b'fixed input')
            output = root / 'queue'
            def write_pdb(coords, path):
                path.write_text('fixture backbone\n'); return {}
            fake_fixture = SimpleNamespace(path=fixture, feats={}, coord=np.zeros((1, 3)), n_tokens=65,
                n_atoms=263, design_tokens=np.arange(65), target_protein_tokens=np.array([]),
                ligand_tokens=np.arange(3), write_pdb=write_pdb, metrics=lambda _: {})
            loads, seeds = [], []
            interrupt = [True]
            class Sampler:
                def __init__(self, weights, **kwargs):
                    seeds.append(kwargs['seed'])
                def generate(self, feats, D, coord_to_be_noised):
                    if len(seeds) == 2 and interrupt[0]:
                        interrupt[0] = False
                        raise RuntimeError('injected sampler death')
                    return {'X_L': np.zeros((D, 1, 3)), 'sequence_indices_I': np.zeros(D)}
            argv = ['generate_backbones.py', '--fixture', str(fixture), '--output', str(output),
                    '--num-designs', '5', '--batch-size', '2', '--seed-start', '42']
            mx = SimpleNamespace(gpu='gpu', set_default_device=lambda _: None,
                set_cache_limit=lambda _: None, load=lambda _: loads.append('weights') or {}, eval=lambda *args: None)
            with patch.object(module, 'ROOT', root), patch.object(module, 'Fixture', return_value=fake_fixture), patch.object(
                    module, 'mx', mx), patch.object(module, 'rfd3', SimpleNamespace(to_bf16=lambda weights: weights)), patch.object(module, 'Sampler', Sampler), patch.object(
                    module, 'assert_ema_artifact', return_value={'weight_set': 'shadow', 'which': 'shadow (EMA)'}), patch.object(
                    module, 'output_geometry_failures', return_value=[]), patch.object(sys, 'argv', argv), patch.dict(
                    os.environ, STUDIO_RFD3_AUDIT_RESUME='1'):
                with self.assertRaisesRegex(RuntimeError, 'sampler death'):
                    module.main()
                state = json.loads((output / 'batch_state.json').read_text())
                self.assertEqual((state['accepted'], state['attempted']), (2, 2))
                module.main()
                self.assertEqual(seeds, [42, 44, 44, 46])
                self.assertEqual(len(loads), 2)  # one load per live queue, not per batch
                module.main()
                self.assertEqual(len(loads), 2)
                self.assertEqual(len(seeds), 4)
                (output / 'backbones/design_0001.pdb').write_text('changed')
                with self.assertRaisesRegex(RuntimeError, 'missing or changed'):
                    module.main()
                self.assertEqual(len(loads), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
