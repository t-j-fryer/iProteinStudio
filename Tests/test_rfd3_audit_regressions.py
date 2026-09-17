"""Executable regression cases from the September RFdiffusion3 pipeline audit.

Only neural inference is replaced; numeric metrics, fixtures, checkpoint hashes,
selection and subprocess orchestration execute the shipped implementation.
"""
import csv
import importlib.util
import json
import os
import signal
from pathlib import Path
import sys
import tempfile
import subprocess
import textwrap
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'Sources/iProteinStudio/Resources/rfd3_overlay/scripts'
sys.path.insert(0, str(SCRIPTS))
from test_rfd3_target_export import load_writer
import design_from_yaml as design
import rfd3_resume as resume
import score_and_select as scoring
import score_binder_validation as validation
import run_rfd3_nise_campaign as ligand_campaign
import prepare_predictor_inputs as inputs
import run_backbone_bins as bins
import run_boltz_affinity as affinity


class MetricTests(unittest.TestCase):
    def fixture(self, fixed=(False, False, True, True), rasa=None):
        writer = load_writer()
        f = writer.Fixture.__new__(writer.Fixture)
        f.tok = np.arange(4)
        f.is_ca = np.array([True, True, False, False])
        f.design_tokens = np.array([0, 1])
        f.fixed_atoms = np.array(fixed)
        f.coord = np.array([[[0., 0., 0.], [3.8, 0., 0.], [0., 4., 0.], [3.8, 4., 0.]]])
        f.rasa = np.zeros((4, 3), int) if rasa is None else rasa
        f.ligand_tokens = np.array([2, 3])
        return f

    def test_every_optional_ligand_selection_combination(self):
        for buried, exposed in [(False, False), (True, False), (False, True), (True, True)]:
            with self.subTest(buried=buried, exposed=exposed):
                f = self.fixture()
                f.rasa[2, 0] = int(buried)
                f.rasa[3, 2] = int(exposed)
                result = f.metrics(f.coord[0])
                self.assertEqual(result['buried_atom_min'], 4.0 if buried else None)
                self.assertEqual(result['exposed_atom_min'], 4.0 if exposed else None)
                self.assertEqual(result['buried_ca_contacts_8A'], 2 if buried else 0)
                json.dumps(result, allow_nan=False)

    def test_monomer_and_single_residue_have_unavailable_not_fake_distances(self):
        f = self.fixture(fixed=(False,) * 4)
        f.ligand_tokens = np.array([], dtype=int)
        self.assertIsNone(f.metrics(f.coord[0])['interface_min'])
        f.design_tokens = np.array([0])
        result = f.metrics(f.coord[0])
        self.assertIsNone(result['ca_min'])
        self.assertEqual(result['binder_rg'], 0.0)
        json.dumps(result, allow_nan=False)

    def test_invalid_coordinates_and_no_designed_residues_fail(self):
        f = self.fixture()
        coords = f.coord[0].copy(); coords[2, 0] = np.nan
        with self.assertRaisesRegex(ValueError, 'non-finite'):
            f.metrics(coords)
        f.design_tokens = np.array([], dtype=int)
        with self.assertRaisesRegex(ValueError, 'no designed'):
            f.metrics(f.coord[0])

    def test_missing_atoms_cannot_pass_export_audit(self):
        writer = load_writer()
        with tempfile.TemporaryDirectory() as raw:
            p = Path(raw) / 'backbone.pdb'
            p.write_text('END\n')
            self.assertTrue(writer.output_geometry_failures(p))
            p.write_text('ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 90.00           C\n')
            self.assertTrue(any('missing backbone' in f for f in writer.output_geometry_failures(p)))


class CheckpointTests(unittest.TestCase):
    def test_failed_queue_stops_the_other_worker_and_exposes_traceback(self):
        with tempfile.TemporaryDirectory() as raw:
            p = Path(raw); scripts = p / 'scripts'; scripts.mkdir()
            (scripts / 'generate_backbones.py').write_text(textwrap.dedent('''\
                import argparse,os,time
                from pathlib import Path
                parser=argparse.ArgumentParser(); parser.add_argument('--output'); a,_=parser.parse_known_args()
                out=Path(a.output); marker=out.parent/'worker.pid'
                if out.name=='queue0':
                    marker.write_text(str(os.getpid()))
                    while True: time.sleep(.05)
                deadline=time.monotonic()+5
                while not marker.exists() and time.monotonic()<deadline: time.sleep(.01)
                raise ValueError('injected worker failure')
                '''))
            fixture = p / 'fixture.npz'; fixture.write_bytes(b'fixture boundary')
            manifest = p / 'bins.json'
            manifest.write_text(json.dumps({'num_designs': 2, 'bins': [dict(
                length=65, quota=2, name='test', bin_index=0, seed=0, fixture=str(fixture))]}))
            argv = ['runner', '--bin-manifest', str(manifest), '--output', str(p / 'out')]
            with patch.object(bins, 'ROOT', p), patch.object(sys, 'argv', argv):
                with self.assertRaisesRegex(SystemExit, 'injected worker failure'):
                    bins.main()
            pid = int((p / 'out/L65/worker.pid').read_text())
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
            self.assertFalse((p / 'out/L65/bin_done.json').exists())

    def test_affinity_chunks_verify_outputs_before_reuse(self):
        with tempfile.TemporaryDirectory() as raw:
            p = Path(raw); source = p / 'inputs'; source.mkdir()
            (source / 'design_1.yaml').write_text('version: 1\n')
            output = p / 'output'; calls = []
            def fold(library, paths, work, potentials, parallel):
                calls.append(work); work.mkdir(parents=True)
                pdb = work / 'design.pdb'; pdb.write_text('structure\n')
                return {'design_1': SimpleNamespace(pdb=str(pdb), ligand_plddt=80., pbind=.5)}
            argv = ['runner', '--inputs', str(source), '--output', str(output),
                    '--nanohunter-root', str(p), '--parallel', '1']
            with patch.object(sys, 'argv', argv), patch.object(affinity.studio_runtime, 'configure'), \
                 patch.object(affinity, 'shard_and_predict', side_effect=fold):
                affinity.main(); affinity.main()
                self.assertEqual(len(calls), 1)
                (output / 'chunk_0000/design.pdb').write_text('damaged')
                with self.assertRaisesRegex(RuntimeError, 'missing or changed'):
                    affinity.main()

    def test_mpnn_resumes_only_unfinished_backbones_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as raw:
            p = Path(raw); backbones = p / 'backbones'; backbones.mkdir()
            for name in ['design_0001', 'design_0002']:
                (backbones / f'{name}.pdb').write_text('\n'.join(
                    f'ATOM  {i:5d}  CA  ALA A{i:4d}    {i*3.8:8.3f}{0.:8.3f}{0.:8.3f}  1.00 90.00           C'
                    for i in range(1, 4)) + '\n')
            python = p / 'venvs/NanoHunter_ligandmpnn/bin/python'
            python.parent.mkdir(parents=True); python.symlink_to(sys.executable)
            model = p / 'src/LigandMPNN/run.py'; model.parent.mkdir(parents=True)
            model.write_text(textwrap.dedent('''\
                import argparse,json,time
                from pathlib import Path
                p=argparse.ArgumentParser(); p.add_argument('--pdb_path_multi'); p.add_argument('--out_folder')
                a,_=p.parse_known_args(); out=Path(a.out_folder); seqs=out/'seqs'; seqs.mkdir(exist_ok=True)
                marker=out/'calls.json'; calls=json.loads(marker.read_text()) if marker.exists() else []
                paths=list(json.loads(Path(a.pdb_path_multi).read_text())); calls.append(paths)
                marker.write_text(json.dumps(calls))
                for path in paths:
                    (seqs/(Path(path).stem+'.fa')).write_text('>native\\nAAA\\n>design_1\\nADE\\n')
                    if len(calls)==1: time.sleep(30); raise SystemExit(7)
                '''))
            output = p / 'mpnn'
            command = [sys.executable, str(SCRIPTS / 'run_mpnn.py'), '--backbones', str(backbones),
                       '--output', str(output), '--model-type', 'soluble_mpnn', '--nanohunter-root', str(p)]
            interrupted = subprocess.Popen(command, text=True, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, start_new_session=True)
            try:
                deadline = time.monotonic() + 5
                receipt = output / 'receipts/design_0001.json'
                while not receipt.exists() and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertTrue(receipt.exists(), 'per-backbone progress was not checkpointed while MPNN ran')
            finally:
                if interrupted.poll() is None:
                    os.killpg(interrupted.pid, signal.SIGTERM)
                interrupted.communicate(timeout=5)
            self.assertNotEqual(interrupted.returncode, 0)
            first = output / 'seqs/design_0001.fa'; original = first.read_bytes()
            resumed = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            self.assertEqual(first.read_bytes(), original)
            calls = json.loads((output / 'calls.json').read_text())
            self.assertEqual([len(c) for c in calls], [2, 1])
            replay = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(replay.returncode, 0, replay.stdout + replay.stderr)
            self.assertEqual(json.loads((output / 'calls.json').read_text()), calls)
            first.write_text('tampered')
            failed = subprocess.run(command, text=True, capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn('missing or changed', failed.stderr)

    def test_three_and_four_queues_do_not_reuse_next_bins_seed_range(self):
        for n in [1, 2, 3, 4]:
            specs = [{'quota': 100000}, {'quota': 100000}]
            queue_stride, bin_stride = bins.seed_strides(specs, n)
            ranges = [(b * bin_stride + q * queue_stride,
                       b * bin_stride + q * queue_stride + quota * 10)
                      for b in range(2) for q, quota in enumerate(bins.split_quota(100000, n))]
            for i, left in enumerate(ranges):
                for right in ranges[i + 1:]:
                    self.assertTrue(left[1] <= right[0] or right[1] <= left[0])
        self.assertEqual(bins.seed_strides([{'quota': 100}], 2), (500000, 1000000))

    def test_receipt_checks_input_and_artifact_content(self):
        with tempfile.TemporaryDirectory() as raw:
            p = Path(raw); artifact = p / 'a.pdb'; artifact.write_text('structure')
            receipt = p / 'receipt.json'; request = {'seed': 42}
            resume.save_receipt(receipt, request, [artifact])
            self.assertTrue(resume.verify_receipt(receipt, request))
            with self.assertRaisesRegex(RuntimeError, 'inputs changed'):
                resume.verify_receipt(receipt, {'seed': 43})
            artifact.write_text('corrupted')
            with self.assertRaisesRegex(RuntimeError, 'missing or changed'):
                resume.verify_receipt(receipt, request)

    def test_fixture_replay_and_changed_atom_selection_or_input(self):
        with tempfile.TemporaryDirectory() as raw:
            p = Path(raw); source = p / 'ligand.pdb'; source.write_text('original input')
            spec = {'input': str(source), 'ligand': 'LIG', 'select_exposed': {'LIG': 'O1'}}
            knobs = {'num_designs': 2, 'timesteps': 20, 'n_recycle': 1, 'seed_base': 0}
            calls = []
            def oracle(command, **kwargs):
                calls.append(command)
                out = Path(command[command.index('--output-dir') + 1])
                name = command[command.index('--name') + 1]
                np.savez(out / f'oracle_{name}.npz', coord_to_be_noised=np.zeros((1, 3)),
                         **{'feats/is_ca': np.ones(1)})
                return SimpleNamespace(returncode=0)
            with patch.object(design.subprocess, 'run', side_effect=oracle):
                for _ in range(2):
                    design.build_fixtures(spec, knobs, 'demo', [65], p / 'run', {}, False)
                self.assertEqual(len(calls), 1)
                with self.assertRaisesRegex(RuntimeError, 'inputs changed'):
                    design.build_fixtures({**spec, 'select_exposed': {'LIG': 'C1'}},
                                          knobs, 'demo', [65], p / 'run', {}, False)
                source.write_text('changed source')
                with self.assertRaisesRegex(RuntimeError, 'inputs changed'):
                    design.build_fixtures(spec, knobs, 'demo', [65], p / 'run', {}, False)

    def test_bad_fixture_is_not_checkpointed(self):
        with tempfile.TemporaryDirectory() as raw:
            p = Path(raw)
            with patch.object(design.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
                with self.assertRaises(FileNotFoundError):
                    design.build_fixtures({}, {'num_designs': 1, 'timesteps': 20,
                        'n_recycle': 1, 'seed_base': 0}, 'demo', [65], p, {}, False)
            self.assertFalse(list(p.rglob('*.receipt.json')))

    def test_binary_cif_uses_binary_reader_and_preserves_insertions(self):
        from biotite.structure.io.pdbx import BinaryCIFFile, set_structure
        from biotite.structure import AtomArray
        with tempfile.TemporaryDirectory() as raw:
            p = Path(raw) / 'structure.bcif'
            array = AtomArray(2)
            array.chain_id[:] = 'A'; array.res_id[:] = 1; array.ins_code[:] = ['', 'A']
            array.res_name[:] = 'ALA'; array.atom_name[:] = 'CA'; array.element[:] = 'C'
            array.coord[:] = [[0, 0, 0], [3.8, 0, 0]]
            binary = BinaryCIFFile(); set_structure(binary, array); binary.write(p)
            self.assertEqual(design.input_chain_length({'input': str(p)}, 'A'), 2)
            self.assertEqual(len(validation.load_array(str(p))), 2)
            design.preflight({'input': str(p), 'select_fixed_atoms': {'A1': 'CA'}})

    def test_stale_duplicate_or_unsafe_prediction_names_fail(self):
        with tempfile.TemporaryDirectory() as raw:
            p = Path(raw)
            for names in [[], ['a', 'a'], ['../escape']]:
                with self.assertRaises(ValueError):
                    resume.validate_input_names(p, names)
            (p / 'stale.yaml').write_text('old input')
            with self.assertRaisesRegex(ValueError, 'stale'):
                resume.validate_input_names(p, ['new'])


class RankingTests(unittest.TestCase):
    def test_nonfinite_scores_and_missing_checkers_cannot_be_hits(self):
        for value in ['nan', 'NaN', 'inf', '-inf', 'invalid']:
            self.assertIsNone(scoring.to_float(value, default=None))
        for values in [{'a': 0.1}, {'a': 0.1, 'b': None}, {'a': 0.1, 'b': float('nan')}]:
            self.assertIsNone(validation.complete_aggregate(values, ['a', 'b'], max))
        self.assertEqual(validation.complete_aggregate({'a': .1, 'b': .7}, ['a', 'b'], max), .7)

    def test_only_requested_predictors_contribute_to_rank(self):
        with tempfile.TemporaryDirectory() as raw:
            args = SimpleNamespace(predictors='boltz', sequences=None, output=Path(raw),
                                   top_n=1, require_top_n=True)
            rows = [dict(design='a', predictor='boltz', exit_code='0', structure='a.cif',
                         iptm='0.7', ipsae_min='0.6'),
                    dict(design='a', predictor='extra', exit_code='1', structure='', iptm='nan')]
            scoring.score_proteins(rows, args)
            with (Path(raw) / 'top100.csv').open() as stream:
                result = list(csv.DictReader(stream))
            self.assertEqual(float(result[0]['score']), .7)
            for bad in ['nan', 'inf', '1.5']:
                rows[0]['iptm'] = bad
                with self.assertRaisesRegex(SystemExit, 'No protein design'):
                    scoring.score_proteins(rows, args)

    def test_duplicate_checker_records_are_ambiguous(self):
        args = SimpleNamespace(predictors='boltz', sequences=None)
        row = dict(design='a', predictor='boltz', exit_code='0', structure='a.cif', iptm='.7', ipsae_min='.6')
        with self.assertRaisesRegex(SystemExit, 'Duplicate'):
            scoring.score_proteins([row, row], args)

    def test_ligand_sequence_designer_routes_exact_model(self):
        cfg = dict(sequence_model='proteinmpnn', num_backbones=1, sequences_per_backbone=1,
                   nanohunter_root='/fixture/root')
        with tempfile.TemporaryDirectory() as raw:
            commands = []
            with patch.object(ligand_campaign, 'run', side_effect=lambda cmd, log: commands.append(cmd)), \
                 patch.object(ligand_campaign, 'count_csv', return_value=1):
                ligand_campaign.stage_mpnn(cfg, Path(raw), Path(raw))
            cmd = commands[0]
            self.assertEqual(cmd[cmd.index('--model-type') + 1], 'protein_mpnn')
            with self.assertRaisesRegex(SystemExit, 'Unsupported'):
                ligand_campaign.stage_mpnn({**cfg, 'sequence_model': 'typo'}, Path(raw), Path(raw))

    def test_invalid_conformer_weights_fail_before_generation(self):
        for values in [[float('nan')], [float('inf')], [-1, 2], [0, 0]]:
            with self.assertRaises(SystemExit):
                design.allocate_weighted(5, values)


if __name__ == '__main__':
    unittest.main(verbosity=2)
