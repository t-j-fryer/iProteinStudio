"""Screening, installation provenance and interruption contracts; no model inference."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path.insert(0, str(SCRIPTS / 'nise'))
import contract
import nesso_contract as nc
import nesso_screen as ns
RealClient = ns.NessoClient
from runtime import Journal, atomic


def scores(probability):
    return {**dict.fromkeys(nc.SCALARS, 0.0), 'entropy_crop_pl': .2, 'affinity_probability_binary': probability}


class FakeClient:
    calls = 0
    loads = 0
    closes = 0
    fail_at = None
    def __init__(self, *args):
        type(self).loads += 1
    def score(self, sequence, smiles, directory):
        cls = type(self)
        if cls.calls == cls.fail_at:
            raise RuntimeError('injected screening interruption')
        cls.calls += 1
        value = scores(int(directory.name.rsplit('_s', 1)[1]) / 10)
        atomic(directory / 'affinity.json', value)
        return {'scores': value}
    def close(self):
        type(self).closes += 1


class NessoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = nc.installation(self.root); self.base.mkdir(parents=True)
        (self.base / 'receipt.json').write_text('fixture installation fingerprint')
        self.backend = SimpleNamespace(root=self.root, output=self.root / 'campaign', scripts=SCRIPTS,
            settings=dict(seed=0, nesso_top_k=2, scheduler='cycle-wave'),
            nesso_worker=None, nesso_scores={})
        self.backend.output.mkdir()
        self.backend.journal = Journal(self.backend.output)
        self.sequence_map = {f'c01_t{tid}_n0_s{k}': 'ACDE' for tid in range(2) for k in range(4)}
        FakeClient.calls = FakeClient.loads = FakeClient.closes = 0
        FakeClient.fail_at = None
        self.mock = patch.object(ns, 'NessoClient', FakeClient); self.mock.start()
    def tearDown(self):
        self.mock.stop(); self.temp.cleanup()
    def screen(self):
        return ns.screen(self.backend, self.sequence_map, 'CCO', self.backend.output / 'cycle01/nesso')

    def test_shortlist_is_per_trajectory_with_stable_ties_and_no_score_substitution(self):
        s = {k: scores(0.9 if '_t0_' in k else 0.1) for k in self.sequence_map}
        selected = nc.shortlist(self.sequence_map, s, 2)
        self.assertEqual(selected, ['c01_t0_n0_s0', 'c01_t0_n0_s1', 'c01_t1_n0_s0', 'c01_t1_n0_s1'])
        self.assertNotIn('ligand_plddt', s[selected[0]])
        with self.assertRaisesRegex(ValueError, 'every sampled'):
            nc.shortlist(self.sequence_map, {}, 2)
        s[selected[0]]['affinity_pred_value'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'non-finite'):
            nc.shortlist(self.sequence_map, s, 2)

    def test_interrupted_screen_replays_completed_scores_and_retains_rejected_candidates(self):
        FakeClient.fail_at = 3
        with self.assertRaisesRegex(RuntimeError, 'interruption'):
            self.screen()
        self.assertEqual(FakeClient.closes, 1)
        FakeClient.fail_at = None
        selected = self.screen()
        self.assertEqual(FakeClient.calls, 8)
        self.assertEqual(len(selected), 4)
        self.assertEqual(len(self.backend.nesso_scores), 8)
        import csv
        with (self.backend.output / "nesso_screening.csv").open() as stream:
            report = list(csv.DictReader(stream))
        self.assertEqual(len(report), 8)
        self.assertEqual(sum(row["selected_for_boltz"] == "True" for row in report), 4)
        self.assertEqual(self.screen(), selected)
        self.assertEqual(FakeClient.calls, 8)
        self.assertEqual(FakeClient.loads, 2, 'All-cached replay must not start another model worker')

    def test_selection_and_raw_artifact_corruption_fail_instead_of_rescoring(self):
        self.screen()
        saved = self.backend.output / 'cycle01/nesso/c01_t0_n0_s0/affinity.json'
        saved.write_text('{}')
        with self.assertRaisesRegex(RuntimeError, 'artifact is missing or changed'):
            self.screen()
        self.assertEqual(FakeClient.calls, 8)

    def test_changed_requested_shortlist_fails_on_resume(self):
        self.screen()
        self.backend.settings['nesso_top_k'] = 1
        with self.assertRaisesRegex(RuntimeError, 'inputs changed'):
            self.screen()

    def test_changed_installation_fails_on_resume(self):
        self.screen()
        (self.base / 'receipt.json').write_text('changed installation')
        with self.assertRaisesRegex(RuntimeError, 'inputs changed'):
            self.screen()

    def test_experimental_residency_reuses_models_across_later_cycle_inputs(self):
        self.backend.settings['scheduler'] = 'resident'
        self.screen()
        later = {k.replace('c01', 'c02'): v for k, v in self.sequence_map.items()}
        ns.screen(self.backend, later, 'CCO', self.backend.output / 'cycle02/nesso')
        self.assertEqual(FakeClient.loads, 1)
        self.assertEqual(FakeClient.closes, 0)
        self.backend.nesso_worker.close()

    def test_initial_selection_caps_original_lineages_before_global_pooling(self):
        names = ['L0_c3_0_e0', 'L0_c3_1_e0', 'L1_c3_0_e0', 'L2_c3_0_e0']
        sequences = dict.fromkeys(names, 'ACDE')
        owners = dict(zip(names, ['L0', 'L0', 'L1', 'L2']))
        values = {n: scores(p) for n, p in zip(names, [.99, .98, .8, .7])}
        self.assertEqual(nc.shortlist_by_lineage(sequences, values, owners, 1, 2), [names[0], names[2]])
        self.assertEqual(len(nc.shortlist_by_lineage(sequences, values, owners, 1, 20)), 3)
        with self.assertRaisesRegex(ValueError, 'every sampled'):
            nc.shortlist_by_lineage(sequences, values, {}, 1, 2)

    def test_initial_screen_is_durable_and_reports_lineages_without_optimization_ids(self):
        # Deliberately use IDs outside the optimization grammar.
        names = ['L0_gate0_s0', 'L0_gate1_s1', 'L1_gate0_s2', 'L2_gate0_s3']
        seqs = dict.fromkeys(names, 'ACDE')
        owners = dict(zip(names, ['L0', 'L0', 'L1', 'L2']))
        directory = self.backend.output / 'phase0/cycle04/nesso'
        def run():
            return ns.screen(self.backend, seqs, 'CCO', directory, owners=owners, per_lineage=1, total=2)
        FakeClient.fail_at = 2
        with self.assertRaisesRegex(RuntimeError, 'interruption'):
            run()
        FakeClient.fail_at = None
        selected = run()
        self.assertEqual(set(selected), set(names[2:]))
        self.assertEqual(FakeClient.calls, 4)
        self.assertEqual(run(), selected)
        self.assertEqual(FakeClient.calls, 4)
        import csv
        with (self.backend.output / 'nesso_screening.csv').open() as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 4)
        self.assertEqual({r['stage'] for r in rows}, {'initial'})
        self.assertEqual({r['lineage'] for r in rows}, {'L0', 'L1', 'L2'})
        owners[names[0]] = 'different'
        with self.assertRaisesRegex(RuntimeError, 'inputs changed'):
            run()

    def test_initial_screen_budgets_and_dependency_are_independent(self):
        cfg = contract.normalize(dict(smiles='CCO', phase0_nesso_screen=True))
        self.assertFalse(cfg['nesso_screen'])
        self.assertEqual(contract.prediction_budget(cfg)['initial_boltz_max'], 620)
        self.assertEqual(contract.prediction_budget({**cfg, 'backbone_method': 'rfdiffusion3'})['initial_boltz_max'], 520)
        self.assertEqual(contract.normalize(dict(smiles='CCO', phase0_seqs1=7))['phase0_gate_seqs'], 7)
        with patch.object(contract, 'nesso_contract', return_value=SimpleNamespace(installation_files=lambda r: [r / 'nesso-required'])):
            self.assertIn(self.root / 'nesso-required', contract.required_files(self.root, cfg))
        for change in ({'phase0_nesso_screen': 1}, {'phase0_nesso_refine_top_k': 4},
                       {'phase0_nesso_expand_top_k': 5}, {'phase0_gate_seqs': 0},
                       {'phase0_sc_ca': float('nan')}, {'nise_sc_lig': 0}, {'nise_ligand_sc_from_cycle': True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                contract.normalize({**cfg, **change})

    def test_placement_confidence_changes_both_rankings_and_caps_follow_rejection(self):
        names = ['c01_t0_n0_s0', 'c01_t0_n0_s1', 'c01_t0_n0_s2', 'c01_t1_n0_s0']
        seqs = dict.fromkeys(names, 'ACDE')
        values = {n: scores(p) for n,p in zip(names, [.99,.8,1,.7])}
        values[names[0]]['entropy_crop_pl'] = .9  # score 1.09
        values[names[1]]['entropy_crop_pl'] = .2  # score 1.60 despite lower P(bind)
        values[names[2]]['entropy_crop_pl'] = 0   # would incorrectly win without guard
        values[names[1]]['entropy_pl'] = .95  # full entropy must not replace cropped interface entropy
        self.assertAlmostEqual(nc.placement_score(values[names[1]])['score'], 1.6)
        self.assertEqual(nc.shortlist(seqs, values, 1), [names[1], names[3]])
        owners = dict(zip(names, ['L0','L0','L0','L1']))
        self.assertEqual(nc.shortlist_by_lineage(seqs, values, owners, 1, 1), [names[1]])
        for entropy in [None, float('nan'), float('inf'), -0.1, 1.01, 0, 1e-12, 1e-6, True, '0.2']:
            with self.subTest(entropy=entropy):
                result = nc.placement_score({**scores(.9), 'entropy_crop_pl': entropy})
                self.assertFalse(result['eligible'])
                self.assertIsNone(result['score'])
                self.assertTrue(result['rejection_reason'])
        missing = scores(.9); del missing['entropy_crop_pl']
        self.assertFalse(nc.placement_score(missing)['eligible'])
        for entropy in [1.000001e-6, .5, 1.0]:
            self.assertTrue(nc.placement_score({**scores(.9), 'entropy_crop_pl': entropy})['eligible'])
        self.assertIsNone(nc.validate_scores({**scores(.9), 'entropy_crop_pl': float('nan')})['entropy_crop_pl'])

    def test_rejected_placements_are_reported_and_cached_without_rescoring(self):
        original = FakeClient.score
        def with_missing_placement(client, sequence, smiles, directory):
            result = original(client, sequence, smiles, directory)
            if directory.name.endswith('_s3'):
                result['scores']['entropy_crop_pl'] = 0
            return result
        with patch.object(FakeClient, 'score', with_missing_placement):
            selected = self.screen()
            self.assertEqual(len(selected), 4)
            self.assertFalse(any(n.endswith('_s3') for n in selected))
            self.assertEqual(self.screen(), selected)
        self.assertEqual(FakeClient.calls, 8)
        import csv
        with (self.backend.output / 'nesso_screening.csv').open() as f:
            rows = list(csv.DictReader(f))
        rejected = [r for r in rows if r['nesso_eligible']=='False']
        self.assertEqual(len(rejected), 2)
        self.assertTrue(all(r['nesso_screening_score']=='' and 'near zero' in r['nesso_rejection_reason'] for r in rejected))
        self.assertEqual({r['nesso_ranking_policy'] for r in rows}, {'nesso-pbind-placement-v2'})

    def test_all_invalid_writes_audited_report_then_stops_without_fallback(self):
        original = FakeClient.score
        def invalid(client, sequence, smiles, directory):
            result = original(client, sequence, smiles, directory)
            result['scores']['entropy_crop_pl'] = 0
            return result
        with patch.object(FakeClient, 'score', invalid):
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, 'rejected every candidate'):
                    self.screen()
        self.assertEqual(FakeClient.calls, 8)
        saved = json.loads((self.backend.output / 'cycle01/nesso/selection.json').read_text())
        self.assertEqual(saved['result'], [])
        self.assertTrue(all(not a['eligible'] for a in saved['input']['assessments'].values()))
        self.assertTrue((self.backend.output / 'nesso_screening.csv').exists())

    def test_old_or_changed_ranking_policy_cannot_reuse_shortlist(self):
        self.screen()
        path = self.backend.output / 'cycle01/nesso/selection.json'
        saved = json.loads(path.read_text())
        saved['input']['ranking'] = 'NESSO affinity_probability_binary descending; candidate name breaks ties'
        saved['input'].pop('assessments')
        atomic(path, saved)
        # Historical tables retain the original policy; they never fabricate the new score.
        ns.write_report(self.backend.output)
        import csv
        with (self.backend.output / 'nesso_screening.csv').open() as f:
            self.assertTrue(all(r['nesso_screening_score']=='' for r in csv.DictReader(f)))
        with self.assertRaisesRegex(RuntimeError, 'inputs changed'):
            self.screen()
        self.assertEqual(FakeClient.calls, 8)

    def test_esm_reuses_only_exact_cached_assets_and_keeps_an_owned_copy(self):
        from setup_nesso import reuse_esm_asset
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            cache = root / 'hub'
            source = cache / 'models--facebook--esm2_t33_650M_UR50D/snapshots/fixture/config.json'
            source.parent.mkdir(parents=True); source.write_text('wrong architecture')
            target = root / 'nesso/esm/config.json'
            import hashlib
            checksum = hashlib.sha256(b'exact asset').hexdigest()
            with patch.dict(os.environ, HF_HUB_CACHE=str(cache)):
                self.assertFalse(reuse_esm_asset(root, 'config.json', checksum, target))
                self.assertFalse(target.exists())
                source.write_text('exact asset')
                self.assertTrue(reuse_esm_asset(root, 'config.json', checksum, target))
                source.write_text('changed cache')
                self.assertEqual(target.read_text(), 'exact asset')
                self.assertTrue(reuse_esm_asset(root, 'config.json', checksum, target))

    def test_large_budget_and_stage_settings_are_typed_and_constrained(self):
        cfg = contract.normalize(dict(smiles='CCO', num_starts=500, trajectories=100, beam=3,
            nise_seqs=1000, nesso_screen=True, nesso_top_k=20, phase0_refine_cycles=0))
        self.assertEqual(cfg['beam'], 3)
        for changes in ({'beam': 0}, {'beam': 65}, {'nesso_screen': 1}, {'nesso_top_k': 2},
                        {'nesso_top_k': 1001}, {'phase0_refine_cycles': -1}, {'phase0_seqs1': True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                contract.normalize({**cfg, **changes})
        old = contract.normalize(dict(smiles='CCO'))
        self.assertEqual((old['beam'], old['phase0_refine_cycles'], old['phase0_seqs1'], old['phase0_seqs2']), (1,2,3,5))
        self.assertFalse(old['nesso_screen'])
        budget = contract.prediction_budget(old)
        self.assertEqual((budget['initial_boltz_max'], budget['optimization_boltz_max']), (2500, 11520))
        budget = contract.prediction_budget(cfg)
        self.assertEqual((budget['first_cycle_boltz_max'], budget['later_cycle_boltz_max']), (2000, 2000))

    def test_queue_client_reuses_one_process_and_surfaces_worker_death(self):
        import subprocess
        executable = self.base / "venv/bin/python"
        executable.parent.mkdir(parents=True)
        executable.symlink_to(sys.executable)
        fake_scripts = self.root / "fixture-scripts/nise"
        fake_scripts.mkdir(parents=True)
        helper = fake_scripts / "nesso_worker.py"
        helper.write_text("""import hashlib,json,os,pathlib,sys,time
config_path=pathlib.Path(sys.argv[2]); c=json.loads(config_path.read_text()); q=pathlib.Path(c['queue'])
def write(p, data):
    p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix('.part'); t.write_text(json.dumps(data)); t.replace(p)
write(q/'ready.json',dict(device='mps',fallback=0,pid=os.getpid(),model_load_count=2,config_sha256=hashlib.sha256(config_path.read_bytes()).hexdigest(),startup_seconds=0.0))
while not (q/'stop.json').exists():
    for p in (q/'requests').glob('*.json'):
        response=q/'responses'/p.name
        if response.exists(): continue
        r=json.loads(p.read_text())
        result=dict(device='mps',precision='float32',recycling_steps=5,refine_protein_inference=True,model_load_count=2,scores=SCORES)
        write(response,dict(ok=True,request_id=r['request_id'],input_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),result=result))
    time.sleep(.01)
""".replace('SCORES', repr(scores(0.7))))
        client = RealClient(self.root, self.backend.output, fake_scripts.parent, 0)
        try:
            pid = client.process.pid
            for i in range(2):
                reply = client.score('ACDE', 'CCO', self.backend.output / str(i))
                self.assertEqual(reply['scores']['affinity_probability_binary'], 0.7)
                self.assertEqual(client.process.pid, pid)
            client.process.terminate(); client.process.wait(timeout=5)
            with self.assertRaisesRegex(RuntimeError, 'exited'):
                client.score('ACDE', 'CCO', self.backend.output / 'third')
        finally:
            client.close()

    def test_managed_detection_reports_missing_and_incomplete_without_installing(self):
        import subprocess
        helper = SCRIPTS / "nise/setup_nesso.py"
        empty = self.root / "empty"
        command = [sys.executable, str(helper), "--root", str(empty), "--detect"]
        self.assertIn("NHSTATE|nesso|missing|", subprocess.check_output(command, text=True))
        nc.installation(empty).mkdir(parents=True)
        self.assertIn("NHSTATE|nesso|incomplete|", subprocess.check_output(command, text=True))
        self.assertFalse((nc.installation(empty) / "venv").exists())

    def test_installation_requires_exact_pins_and_rejects_receipt_path_escape(self):
        with self.assertRaises(ValueError):
            nc.read_receipt(self.root)
        atomic(self.base / "receipt.json", [])
        with self.assertRaisesRegex(ValueError, "Invalid NESSO installation receipt"):
            nc.read_receipt(self.root)
        receipt = dict(version=nc.VERSION, protocol_sha256=nc.sha256(nc.ASSETS/'protocol.json'),
            lock_sha256=nc.sha256(nc.ASSETS/'requirements.lock'), patch_sha256=nc.sha256(nc.ASSETS/'nesso_mps.patch'),
            files={'../../elsewhere':{'sha256':'x','size':1}})
        atomic(self.base / 'receipt.json', receipt)
        with self.assertRaisesRegex(ValueError, 'receipt paths'):
            nc.read_receipt(self.root)
        receipt['files'] = {'model/model.safetensors': {'sha256':'wrong','size':1}}
        atomic(self.base / 'receipt.json', receipt)
        with self.assertRaisesRegex(ValueError, 'unexpected model assets'):
            nc.read_receipt(self.root)


if __name__ == '__main__':
    unittest.main(verbosity=2)
