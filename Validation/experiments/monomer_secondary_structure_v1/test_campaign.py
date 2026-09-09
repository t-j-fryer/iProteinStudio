"""Contract checks for the declared experiment; no model inference."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

import campaign
import audit

sys.path.insert(0, str(campaign.SOURCE / "mcp"))
from iprotein_mcp.plans import _normalize_iterative_arguments


class CampaignTests(unittest.TestCase):
    def test_budget_and_public_arguments(self):
        self.assertEqual(len(campaign.CONFIG["arms"]), 22)
        predictions = 0
        for arm in campaign.CONFIG["arms"].values():
            for phase, count in (("pilot", 1), ("remaining", 9)):
                args = campaign.arguments_for(arm, phase)
                normalized, _ = _normalize_iterative_arguments(args)
                self.assertEqual(normalized, args)
                self.assertEqual(int(audit.option(args, "--num-runs")), count)
                self.assertEqual(audit.option(args, "--num-opt-cycles"), "5")
                self.assertEqual(audit.option(args, "--binder-min-len"), "90")
                self.assertEqual(audit.option(args, "--binder-max-len"), "90")
                predictions += count * (5 + arm.get("inspection", {}).get("max_attempts", 1))
        self.assertEqual(predictions, 1380)

    def test_phase_split_preserves_pairing_without_duplicate_seeds(self):
        c = campaign.CONFIG["campaign"]
        for arm in campaign.CONFIG["arms"].values():
            binder_seeds, mpnn_seeds = [], []
            for phase in ("pilot", "remaining"):
                args = campaign.arguments_for(arm, phase)
                for local_index in range(1, int(audit.option(args, "--num-runs")) + 1):
                    binder_seeds.append(int(audit.option(args, "--binder-random-seed")) + local_index)
                    mpnn_seeds.append(int(audit.option(args, "--mpnn-seed")) + 1000 * local_index)
            self.assertEqual(binder_seeds, [c["binder_seed"] + i for i in range(1, 11)])
            self.assertEqual(mpnn_seeds, [c["mpnn_seed"] + 1000 * i for i in range(1, 11)])

    def test_references_change_one_declared_factor(self):
        for name, arm in campaign.CONFIG["arms"].items():
            if not arm["reference"]:
                continue
            left = copy.deepcopy(campaign.CONFIG["arms"][arm["reference"]])
            right = copy.deepcopy(arm)
            left.pop("reference"); right.pop("reference")
            changed = [key for key in left.keys() | right.keys() if left.get(key) != right.get(key)]
            self.assertEqual(len(changed), 1, (name, changed))
            if "inspection" in right:
                self.assertEqual(right["mode"], "beta")
                self.assertEqual(right["scope"], "seed-only")
                if "inspection" in left:
                    self.assertEqual(sum(left["inspection"][key] != value for key, value in right["inspection"].items()), 1)

    def test_inspection_reuses_beta_original_and_mask(self):
        beta = campaign.CONFIG["arms"]["beta"]
        common = lambda a: {k: v for k, v in a.items() if k not in {"reference", "inspection"}}
        for arm in campaign.CONFIG["arms"].values():
            if "inspection" in arm:
                self.assertEqual(common(arm), common(beta))

    def test_paired_statistics_keep_only_matched_completion(self):
        result = audit.paired_summary({1: {"x": 1}, 2: {"x": 100}}, {1: {"x": 3}, 3: {"x": 50}}, "x", replicates=100)
        self.assertEqual(result["n_pairs"], 1)
        self.assertEqual(result["mean_difference"], 2)
        self.assertEqual(result["bootstrap_95_ci"], [2, 2])
        self.assertIsNone(audit.paired_summary({}, {}, "x")["mean_difference"])

    def test_mps_gate_rejects_absence_and_forbidden_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "predict.log"
            with self.assertRaises(RuntimeError):
                audit.check_prediction_logs(root)
            log.write_text("GPU available: False, used: False\n")
            with self.assertRaises(RuntimeError):
                audit.check_prediction_logs(root)
            prefix = "GPU available: True (mps), used: True\n"
            log.write_text(prefix + "aten::linalg_svd will fall back to CPU\n")
            self.assertEqual(len(audit.check_prediction_logs(root)), 1)
            log.write_text(prefix + "unsupported operation will fall back to CPU\n")
            with self.assertRaises(RuntimeError):
                audit.check_prediction_logs(root)


if __name__ == "__main__":
    unittest.main()
