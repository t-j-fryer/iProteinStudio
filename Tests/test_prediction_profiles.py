"""Functional scientific-profile, immutable-input and override contracts."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path.insert(0, str(SCRIPTS))
import prediction_profiles as profiles


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {profiles.ENV: '{}'})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_native_exceptions_and_reduced_profiles(self):
        self.assertEqual(profiles.profile('mini'), dict(msa_depth=128, diffusion_steps=5, recycles=4))
        self.assertEqual(profiles.profile('esmfold2-full-mlx'), dict(msa_depth=128, diffusion_steps=50, recycles=3))
        self.assertEqual(profiles.profile('esmfold2-fast-mlx'), dict(msa_depth=0, diffusion_steps=50, recycles=3))
        for engine in ('boltz', 'intellifold', 'intellifold-full', 'protenix-v2', 'protenix-constraint-v0.5', 'openfold-3-mlx'):
            self.assertEqual(profiles.profile(engine)['diffusion_steps'], 25)

    def test_overrides_are_typed_and_engine_specific(self):
        profiles.activate({'intellifold-full': {'diffusion_steps': 200, 'msa_depth': 0}})
        self.assertEqual(profiles.profile('intellifold', 'v2')['diffusion_steps'], 200)
        self.assertEqual(profiles.profile('intellifold', 'v2-flash')['diffusion_steps'], 25)
        for invalid in ({'wrong': {}}, {'boltz': {'diffusion_steps': True}},
                        {'boltz': {'diffusion_steps': 0}}, {'boltz': {'precision': 'bf16'}},
                        {'esmfold2-fast-mlx': {'msa_depth': 128}}):
            with self.assertRaises(ValueError): profiles.normalize(invalid)

    def test_full_budget_override_and_sequence_only_fast_remain_independent(self):
        profiles.activate({'esmfold2-full-mlx': {'diffusion_steps': 100, 'recycles': 20, 'msa_depth': 0}})
        self.assertEqual(profiles.profile('esmfold2-full-mlx'), dict(msa_depth=0, diffusion_steps=100, recycles=20))
        self.assertEqual(profiles.profile('esmfold2-fast-mlx'), dict(msa_depth=0, diffusion_steps=50, recycles=3))

    def test_mcp_and_cli_share_full_defaults_and_preserve_frozen_profiles(self):
        sys.path.insert(0, str(SCRIPTS.parent / 'mcp'))
        from iprotein_mcp.prediction_settings import normalize
        full = 'esmfold2-full-mlx'
        self.assertEqual(normalize()[full], profiles.profile(full))
        self.assertEqual(normalize()[full], dict(msa_depth=128, diffusion_steps=50, recycles=3))
        frozen = normalize({full: dict(msa_depth=128, diffusion_steps=100, recycles=20)})
        profiles.activate(frozen)
        self.assertEqual(profiles.profile(full), frozen[full])
        self.assertEqual(profiles.profile(full)['recycles'], 20)

    def test_native_cli_override_survives_and_is_recorded(self):
        args = profiles.arguments('boltz', ['predict', 'x', '--sampling_steps=200'])
        self.assertNotIn('--sampling_steps', args)
        self.assertEqual(profiles.effective('boltz', args)['diffusion_steps'], 200)
        self.assertEqual(args.count('--recycling_steps'), 1)
        args = profiles.arguments('boltz', ['predict', 'x', '--max_msa_seqs=512'])
        self.assertEqual(profiles.effective('boltz', args)['msa_depth'], 512)
        self.assertNotIn('--max_msa_seqs', args)

    def test_capped_alignment_preserves_query_and_original_bytes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            msa = root / 'full.a3m'
            content = '# metadata\n' + ''.join(f'>row{i}\nACdE\nFG\n' for i in range(256))
            msa.write_text(content)
            limited = profiles.cap_a3m(msa, 128, root / 'caps')
            self.assertEqual(limited.read_text().count('>row'), 128)
            self.assertTrue(limited.read_text().startswith('# metadata\n>row0\n'))
            self.assertEqual(msa.read_text(), content)
            self.assertEqual(profiles.cap_a3m(msa, 128, root / 'caps'), limited)
            self.assertEqual(profiles.cap_a3m(msa, 0, root / 'caps'), msa)
            self.assertNotEqual(profiles.cap_a3m(msa, 64, root / 'caps'), limited)

    def test_yaml_stage_preserves_binder_policy_and_rejects_settings_drift(self):
        import yaml
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source = root / 'input'; source.mkdir()
            msa = source / 'target.a3m'; msa.write_text(''.join(f'>r{i}\nAAAA\n' for i in range(130)))
            document = {'sequences': [{'protein': {'id': 'A', 'sequence': 'AAAA', 'msa': 'empty'}},
                                     {'protein': {'id': 'B', 'sequence': 'AAAA', 'msa': 'target.a3m'}}]}
            inp = source / 'test.yaml'; inp.write_text(yaml.safe_dump(document)); before = inp.read_bytes()
            prepared = profiles.prepare_inputs(source, root / 'out', 'boltz')
            result = yaml.safe_load((prepared / 'test.yaml').read_text())
            self.assertEqual(result['sequences'][0]['protein']['msa'], 'empty')
            self.assertEqual(Path(result['sequences'][1]['protein']['msa']).read_text().count('>'), 128)
            self.assertEqual(inp.read_bytes(), before)
            self.assertEqual(profiles.prepare_inputs(source, root / 'out', 'boltz'), prepared)
            with self.assertRaisesRegex(ValueError, 'changed'):
                profiles.prepare_inputs(source, root / 'out', 'boltz', dict(msa_depth=64, diffusion_steps=25, recycles=3))

    def test_openfold_cap_retains_native_parser_filename(self):
        from openfold_mps import prepare_query
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); msa = root / 'colabfold_main.a3m'
            msa.write_text(''.join(f'>r{i}\nAAAA\n' for i in range(130)))
            source = root / 'query.json'
            source.write_text(json.dumps({'queries': {'test': {'chains': [{'main_msa_file_paths': [str(msa)]}]}}}))
            prepared = prepare_query(source, root / 'out', profiles.profile('openfold-3-mlx'))
            capped = Path(json.loads(prepared.read_text())['queries']['test']['chains'][0]['main_msa_file_paths'][0])
            self.assertEqual(capped.name, 'colabfold_main.a3m')
            self.assertEqual(capped.read_text().count('>'), 128)
            self.assertEqual(msa.read_text().count('>'), 130)

    def test_protenix_native_options_preserve_full_mini_and_enable_constraint_cache(self):
        from protenix_predict import protenix_command, MODEL_NAMES
        for alias, cycles, steps, cache in [('mini', 4, 5, 'False'), ('v2', 10, 25, 'False'), ('constraint', 10, 25, 'True')]:
            cmd = protenix_command(Path('/runtime/bin/protenix'), Path('/input.json'), Path('/output'),
                                   MODEL_NAMES[alias], '42', 1, True)
            for flag, expected in [('-c', str(cycles)), ('-p', str(steps)), ('--enable_cache', cache),
                                   ('--use_default_params', 'False'), ('-d', 'fp32')]:
                self.assertEqual(cmd[cmd.index(flag) + 1], expected)


if __name__ == '__main__': unittest.main()
