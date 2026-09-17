"""NISE job/request/checkpoint contracts, with no neural-network inference."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "Sources/iProteinStudio/Resources/pipeline"
sys.path.insert(0, str(PIPELINE / "scripts/nise"))
sys.path.insert(0, str(PIPELINE / "scripts"))
sys.path.insert(0, str(PIPELINE / "mcp"))
import contract
from runtime import Journal
from resident_predictor import BoltzCheckpointCache
from iprotein_mcp import catalog, common
from iprotein_mcp.nise import nise_plan
from iprotein_mcp.plans import load_plan
from server import MCPServer


class NISEContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.env = patch.dict(os.environ, NANOHUNTER_ROOT=str(self.root), IPROTEINSTUDIO_AGENT_ROOT=str(self.root / "agent"))
        self.env.start()

    def tearDown(self):
        self.env.stop(); self.temp.cleanup()

    def test_request_rejects_incompatible_budgets_and_implicit_resources(self):
        for change in ({"num_starts": 0}, {"num_starts": True}, {"trajectories": 1001},
                       {"num_starts": 1, "trajectories": 2}, {"binder_min_len": 151},
                       {"scheduler": "parallel"}, {"affinity": False}, {"smiles": "CC\nO"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                contract.normalize({"smiles": "CCO", **change})
        with self.assertRaisesRegex(ValueError, "Install Boltz"):
            contract.preflight(self.root, {"smiles": "CCO"})

    def test_defaults_separate_science_and_residency(self):
        cfg = contract.normalize({"smiles": "CCO"})
        self.assertEqual((cfg["num_starts"], cfg["trajectories"], cfg["nise_seqs"]), (1000, 8, 32))
        self.assertEqual(cfg["scheduler"], "cycle-wave")
        self.assertFalse(cfg["preorganisation"])

    def test_rfd3_is_optional_and_has_a_separate_initial_generation_budget(self):
        from rfd3_initial import lengths
        cfg = contract.normalize({'smiles': 'CCO', 'backbone_method': 'rfdiffusion3'})
        self.assertEqual(lengths(cfg), [65, 86, 108, 129, 150])
        self.assertEqual(lengths({**cfg, 'rfd3_num_bins': 1}), [107])
        self.assertEqual(lengths({**cfg, 'binder_max_len': 66}), [65, 66])
        self.assertEqual(contract.prediction_budget(cfg)['initial_boltz_max'], 24000)
        self.assertEqual(contract.prediction_budget(cfg)['initial_rfd3_backbones'], 1000)
        self.assertEqual(contract.prediction_budget({'smiles': 'CCO'})['initial_boltz_max'], 25000)
        paths = contract.required_files(self.root, cfg)
        self.assertIn(self.root / 'rfd3/checkpoints/rfd3_latest.ckpt', paths)
        self.assertNotIn(self.root / 'rfd3/checkpoints/rfd3_latest.ckpt', contract.required_files(self.root))
        with self.assertRaises(ValueError):
            contract.normalize({'smiles': 'CCO', 'backbone_method': 'unsupported'})

    def test_completed_sequences_replay_and_corruption_fails(self):
        artifact = self.root / "sample.fasta"; artifact.write_text(">sample\nACDEF\n")
        journal = Journal(self.root); receipt = self.root / "receipt.json"
        journal.save(receipt, {"n": 1}, ["ACDEF"], [artifact])
        self.assertEqual(journal.load(receipt, {"n": 1}), ["ACDEF"])
        with self.assertRaisesRegex(RuntimeError, "inputs changed"):
            journal.load(receipt, {"n": 2})
        artifact.write_text(">sample\nAAAAA\n")
        with self.assertRaisesRegex(RuntimeError, "artifact is missing or changed"):
            journal.load(receipt, {"n": 1})

    def test_boltz_affinity_loads_its_own_model_once_across_later_requests(self):
        conf = self.root / "structure.ckpt"; conf.touch()
        aff = self.root / "affinity.ckpt"; aff.touch()
        structure, affinity = Mock(), Mock()
        loader = Mock(return_value=affinity)
        cache = BoltzCheckpointCache(conf, structure, aff, loader, allow_affinity=True)
        for _ in range(3):
            self.assertIs(cache.load(conf), structure)
            self.assertIs(cache.load(aff, strict=True), affinity)
        loader.assert_called_once_with(aff, strict=True)
        self.assertEqual(cache.load_count, 2)
        with self.assertRaisesRegex(RuntimeError, "unexpected checkpoint"):
            cache.load(self.root / "wrong.ckpt")
        protein = BoltzCheckpointCache(conf, structure, aff, loader)
        with self.assertRaisesRegex(RuntimeError, "unexpected checkpoint"):
            protein.load(aff)

    def test_plan_freezes_settings_weights_and_snapshot_without_gpu_work(self):
        (self.root / "projects/demo").mkdir(parents=True)
        for p in contract.required_files(self.root):
            p.parent.mkdir(parents=True, exist_ok=True); p.write_text("fixture\n")
        (self.root / "models/boltz2/mols").mkdir()
        plan = nise_plan({"project": "demo", "request": {"smiles": "CCO"}})
        self.assertEqual(plan["kind"], "desktop_nise")
        output = Path(plan["normalized_request"]["output"])
        self.assertTrue((output / ".studio_runtime/pipeline/scripts/nise/campaign.py").is_file())
        self.assertFalse((output / "candidates").exists())
        self.assertEqual(load_plan(plan["id"], plan["sha256"]), plan)
        self.assertTrue((output / ".studio_runtime/pipeline/scripts/nise/partial_noising.py").is_file())
        self.assertEqual(plan["normalized_request"]["prediction_budget"]["later_cycle_boltz_max"], 8 * 96)
        settings = output / "nise_config.json"
        settings.write_text(settings.read_text() + "\n")
        with self.assertRaises(common.StudioError):
            load_plan(plan["id"], plan["sha256"])

    def test_agent_read_profile_cannot_plan_and_run_profile_can(self):
        self.assertNotIn("nise_plan", MCPServer("read").allowed)
        self.assertIn("nise_plan", MCPServer("run").allowed)
        self.assertNotIn("nise_plan", MCPServer("admin").allowed)
        self.assertEqual(catalog.workflow_guide("nise")["designer"], "lasermpnn")

    def test_rfd3_plan_freezes_the_generator_and_its_weights(self):
        (self.root / 'projects/demo').mkdir(parents=True)
        cfg = contract.normalize({'smiles': 'CCO', 'backbone_method': 'rfdiffusion3'})
        for path in contract.required_files(self.root, cfg):
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text('fixture\n')
        (self.root / 'models/boltz2/mols').mkdir()
        plan = nise_plan({'project': 'demo', 'request': cfg})
        self.assertEqual(plan['normalized_request']['prediction_budget']['initial_rfd3_backbones'], 1000)
        self.assertEqual(load_plan(plan['id'], plan['sha256']), plan)
        generator = self.root / 'rfd3/scripts/generate_backbones.py'
        generator.write_text('changed code\n')
        with self.assertRaises(common.StudioError):
            load_plan(plan['id'], plan['sha256'])

    def test_overview_preserves_candidate_identity_and_never_infers_binding_hit(self):
        output = self.root / "projects/demo/nise_runs/one"
        (output / "candidates").mkdir(parents=True)
        common.atomic_json(output / "nise_config.json", {})
        (output / "holo.pdb").write_text("fixture")
        for name in ("c01_t0_n0_s0", "c01_t0_n0_s1"):
            common.atomic_json(output / "candidates" / (name + ".json"), {
                "name": name, "trajectory": 0, "cycle": 1, "pdb": "holo.pdb", "sequence": "ACDE", "passed": True})
        result = catalog.results_overview("demo/nise_runs/one")
        self.assertEqual(result["workflow"], "nise")
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual(len(result["groups"][0]["variants"]), 2)
        self.assertIsNone(result["groups"][0]["is_hit"])
        self.assertEqual(catalog.results_overview("demo/nise_runs/one", hit_only=True)["groups"], [])
        common.atomic_json(output / "candidates/masked.json", {
            "name": "masked", "trajectory": 0, "cycle": 2, "pdb": "holo.pdb", "sequence": "AXA",
            "passed": False, "branch": "masked-backbone", "final_eligible": False})
        variants = catalog.results_overview("demo/nise_runs/one")["groups"][0]["variants"]
        masked = next(v for v in variants if v["id"] == "masked")
        self.assertFalse(masked["final_eligible"])
        self.assertEqual(masked["artifacts"][0]["role"], "masked_backbone")


if __name__ == "__main__":
    unittest.main(verbosity=2)
