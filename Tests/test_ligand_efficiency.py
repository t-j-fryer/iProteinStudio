"""Release contracts for affinity budgets and bounded proposal scheduling."""
import json
import os
from pathlib import Path
import sys
import threading
import importlib.util
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path[:0] = [str(SCRIPTS), str(SCRIPTS / 'nise')]
import prediction_profiles as profiles
from proposal_pipeline import run


class EfficiencyTests(unittest.TestCase):
    def test_portable_rfd3_uses_bundled_laser_adapter(self):
        overlay = SCRIPTS.parent.parent / 'rfd3_overlay/scripts'
        sys.path.insert(0, str(overlay))
        try:
            spec = importlib.util.spec_from_file_location('release_rfd3_campaign', overlay / 'run_rfd3_nise_campaign.py')
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            cfg = dict(sequence_design_model='lasermpnn', nanohunter_root='/managed/view',
                       smiles_file='ligand.smi', sequences_per_backbone=4, mpnn_max_parallel=2,
                       seed_base=7)
            class Captured(Exception): pass
            with patch.object(module, 'read_smiles', return_value='CC'), patch.object(module, 'run', side_effect=Captured) as launch:
                with self.assertRaises(Captured): module.stage_mpnn(cfg, Path('/campaign'), Path('/logs'))
            command = launch.call_args.args[0]
            self.assertEqual(command[1], '/managed/view/rfd3_overlay/scripts/run_lasermpnn.py')
            self.assertEqual(command[command.index('--seed')+1], '7')
        finally:
            sys.path.remove(str(overlay))

    def test_affinity_defaults_native_override_and_recorded_effective_settings(self):
        with patch.dict(os.environ, {profiles.ENV: '{}'}):
            args = profiles.arguments('boltz', ['predict', 'input'])
            effective = profiles.effective('boltz', args)
            self.assertEqual((effective['affinity_steps'], effective['affinity_samples']), (50, 1))
            args = profiles.arguments('boltz', ['--sampling_steps_affinity=200', '--diffusion_samples_affinity', '5'])
            self.assertEqual(profiles.effective('boltz', args)['affinity_steps'], 200)
            self.assertEqual(profiles.effective('boltz', args)['affinity_samples'], 5)
            self.assertNotIn('--sampling_steps_affinity', args)
        for overrides in ({'boltz': {'affinity_samples': 0}}, {'intellifold': {'affinity_steps': 50}}):
            with self.assertRaises(ValueError): profiles.normalize(overrides)

    def test_prefetch_overlaps_gpu_without_changing_candidate_identity(self):
        prepared = threading.Event()
        items = [dict(names=[str(i)], pdb='p'+str(i), owner=i) for i in range(4)]
        def design(item):
            if item['owner'] == 2: prepared.set()
            return ['SEQ'+str(item['owner'])]
        calls = []
        def fold(values):
            if not calls: self.assertTrue(prepared.wait(2), 'next chunk was not prepared during folding')
            calls.append(dict(values)); return {k: 'fold:'+v for k,v in values.items()}
        result = run(items, design, fold, overlap=True, chunk_size=2)
        self.assertEqual(list(result[0]), ['0','1','2','3'])
        self.assertEqual(result[2], {str(i): i for i in range(4)})
        self.assertEqual(len(result[3]), 4)
        self.assertEqual([len(c) for c in calls], [2,2])

    def test_screening_keeps_global_selection_barrier(self):
        items = [dict(names=[str(i)], pdb='p', owner=i) for i in range(17)]
        calls = []
        def screen(seqs, owners):
            self.assertEqual(len(seqs), 17)
            return {'16': seqs['16']}
        result = run(items, lambda i: ['SEQ'], lambda s: calls.append(s) or dict(s), overlap=True, screen=screen)
        self.assertEqual(calls, [{'16':'SEQ'}])
        self.assertEqual(result[0], {'16':'SEQ'})

    def test_failure_does_not_fold_incomplete_chunk(self):
        items = [dict(names=['a','b'], pdb='p', owner=1)]
        calls = []
        with self.assertRaisesRegex(RuntimeError, 'count'):
            run(items, lambda _: ['ONE'], lambda s: calls.append(s), overlap=True)
        self.assertEqual(calls, [])

    def test_duplicate_names_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            run([dict(names=['a'], pdb='p', owner=i) for i in range(2)], lambda _: ['SEQ'], lambda s: s)

    def test_pool_is_absent_from_product_entrypoints(self):
        repo = SCRIPTS.parents[4]
        for rel in ['Package.swift', 'Sources/iProteinStudio/iProteinStudioApp.swift',
                    'Sources/iProteinStudio/Views/RunNameField.swift']:
            text = (repo / rel).read_text()
            self.assertNotIn('StudioPool', text)
            self.assertNotIn('studio.pool', text)
        self.assertNotIn('"pool_submit"', (SCRIPTS.parent / 'mcp/server.py').read_text())


if __name__ == '__main__': unittest.main()
