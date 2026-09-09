"""Regression fixtures for paired statistical units and completed-cohort gates."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("seed_mask_summary", Path(__file__).with_name("summary.py"))
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


def fixture():
    manifest = {"phase": "full", "config": {"arms": {arm: {} for arm in summary.ARMS}, "campaign": {"full_trajectories": 10, "design_cycles": 5}}}
    report = {"passed": True, "all_complete": True, "audited_structures": 120, "expected_structures": 120, "arms": {}, "arm_audits": {}, "decision_rule_evaluation": {"at_least_one_arm_meets_declared_rule": False, "arms": {arm: {"meets_declared_rule": False, "sheet_mean": .2, "helix_mean": .5} for arm in summary.ARMS}}}
    trajectories, structures = [], []
    for index, arm in enumerate(summary.ARMS):
        values = {metric: .2 + index * .1 for metric in summary.METRICS}
        values["max_identical_residue_run"] = 2 + index
        for run_number in range(1, 11):
            run = f"run_{run_number:03d}"
            trajectories.append({"arm": arm, "run": run, **{f"{prefix}_{metric}": value for prefix in ("optimized_mean", "final") for metric, value in values.items()}})
            for cycle in range(6):
                structures.append({"arm": arm, "run": run, "cycle": cycle, "sequence": "ACDEFGHIKL" * 9, **values})
        diversity = {"unique_sequences": 1, "sequences": 50, "mean_pairwise_identity": 1}
        report["arms"][arm] = {"endpoints": {endpoint: values for endpoint in ("optimized_cycle_mean", "final_cycle")}, "sequence_diversity": {"all_optimized_cycles": diversity, "final_cycle_across_trajectories": diversity}}
        report["arm_audits"][arm] = {"audit_status": "audited_complete", "seed_plans": {f"run_{i:03d}": {"unmasked_composition": {}, "visible_seed_composition": {}} for i in range(1, 11)}}
    return report, manifest, trajectories, structures


class SummaryTests(unittest.TestCase):
    def test_constant_paired_difference_has_exact_interval(self):
        value = summary.paired_bootstrap([.125] * 10, replicates=100)
        self.assertEqual(value["mean_difference"], .125)
        self.assertEqual(value["paired_bootstrap_95_ci"], [.125, .125])
        self.assertEqual(value["pairs_increased"], 10)

    def test_bootstrap_reproducible_and_resamples_pairs(self):
        differences = [-1, 1] * 5
        first = summary.paired_bootstrap(differences, replicates=1000)
        self.assertEqual(first, summary.paired_bootstrap(differences, replicates=1000))
        self.assertLess(first["paired_bootstrap_95_ci"][0], 0)
        self.assertGreater(first["paired_bootstrap_95_ci"][1], 0)
        with self.assertRaisesRegex(ValueError, "ten trajectory pairs"):
            summary.paired_bootstrap(differences * 5, replicates=100)

    def test_valid_operational_campaign_can_miss_scientific_goal(self):
        original = summary.paired_bootstrap
        with patch.object(summary, "paired_bootstrap", side_effect=lambda values: original(values, replicates=100)):
            result = summary.build_comparison(*fixture())
        self.assertTrue(result["operational_passed"])
        self.assertFalse(result["scientific_decision"]["at_least_one_arm_meets_declared_rule"])
        self.assertAlmostEqual(result["endpoints"]["optimized_cycle_mean"]["mixed_minus_beta"]["sheet_fraction"]["mean_difference"], .1)
        self.assertIn("not met", summary.markdown(result))

    def test_duplicate_trajectory_rejected(self):
        args = fixture()
        args[2][1]["run"] = args[2][0]["run"]
        with self.assertRaisesRegex(ValueError, "missing/duplicate"):
            summary.build_comparison(*args)

    def test_changed_trajectory_value_rejected(self):
        args = fixture()
        args[2][0]["optimized_mean_sheet_fraction"] = .99
        with self.assertRaisesRegex(ValueError, "trajectory CSV differs"):
            summary.build_comparison(*args)

    def test_initial_cycle_cannot_enter_primary_endpoint(self):
        args = fixture()
        for row in args[3]:
            if row["cycle"] == 0:
                row["sheet_fraction"] = .99
        original = summary.paired_bootstrap
        with patch.object(summary, "paired_bootstrap", side_effect=lambda values: original(values, replicates=100)):
            result = summary.build_comparison(*args)
        self.assertEqual(result["endpoints"]["optimized_cycle_mean"]["arms"][summary.ARMS[0]]["mean"]["sheet_fraction"], .2)

    def test_incomplete_audit_rejected(self):
        args = fixture()
        args[0]["all_complete"] = False
        with self.assertRaisesRegex(ValueError, "operational audit"):
            summary.build_comparison(*args)


if __name__ == "__main__":
    unittest.main()
