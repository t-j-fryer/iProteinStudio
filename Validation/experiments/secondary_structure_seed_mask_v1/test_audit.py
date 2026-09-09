"""Targeted integrity regressions for the sample-then-mask audit (no model calls)."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import random
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("seed_mask_audit", Path(__file__).with_name("audit.py"))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class SeedMaskIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.arm = {"mode": "beta", "scope": "seed-only", "anti_helix_strength": 0.0}
        self.controls = {"anti_helix_strength": 0.0, "beta_strength": 1.0, "beta_pattern_strength": 1.0, "turn_strength": 0.5}
        indices = list(range(6))
        random.Random(123 ^ 0x584D4153).shuffle(indices)
        mask = sorted(index + 1 for index in indices[:3])
        sequence = "VTVTGS"
        self.masked = "".join("X" if index in mask else aa for index, aa in enumerate(sequence, 1))
        self.plan = {"sampling_order": "sample-then-mask", "sampling_algorithm": "complete-sequence-independent-mask-v1", "application_scope": "seed-only", "mode": "beta", "length": 6, "percent_x": 50, "seed": 123, "unmasked_sequence": sequence, "x_positions": mask, "masked_sequence": self.masked, "controls": self.controls}

    def validate(self, plan=None, actual=None):
        return audit.validate_seed_plan(plan or self.plan, self.masked if actual is None else actual, self.arm, self.controls, 6)

    def test_valid_saved_mask_reconstructs_actual_sequence(self):
        self.assertTrue(self.validate()["actual_cycle00_equals_reconstructed_mask"])

    def test_wrong_actual_sequence_rejected(self):
        with self.assertRaisesRegex(audit.shared.AuditError, "actual cycle00"):
            self.validate(actual="XXXXXX")

    def test_duplicate_mask_rejected(self):
        plan = deepcopy(self.plan)
        plan["x_positions"][1] = plan["x_positions"][0]
        with self.assertRaisesRegex(audit.shared.AuditError, "unique positions"):
            self.validate(plan)

    def test_edited_full_sequence_rejected(self):
        plan = deepcopy(self.plan)
        visible = next(index for index in range(6) if index + 1 not in plan["x_positions"])
        sequence = list(plan["unmasked_sequence"])
        sequence[visible] = "A"
        plan["unmasked_sequence"] = "".join(sequence)
        with self.assertRaisesRegex(audit.shared.AuditError, "cannot be reconstructed"):
            self.validate(plan)

    def test_wrong_rng_seed_rejected(self):
        plan = deepcopy(self.plan)
        plan["seed"] += 1
        with self.assertRaisesRegex(audit.shared.AuditError, "RNG seed"):
            self.validate(plan)

    def test_wrong_strength_rejected(self):
        plan = deepcopy(self.plan)
        plan["controls"]["beta_strength"] = 0.5
        with self.assertRaisesRegex(audit.shared.AuditError, "beta_strength"):
            self.validate(plan)

    def test_composition_excludes_x_without_bridging_runs(self):
        values = audit.composition("AAXAA")
        self.assertEqual(values["sequence_entropy_bits"], 0)
        self.assertEqual(values["max_residue_fraction"], 1)
        self.assertEqual(values["max_identical_residue_run"], 2)
        self.assertEqual(audit.composition("ACDE")["sequence_entropy_bits"], 2)

    def test_unexpected_mpnn_bias_file_rejected(self):
        args = ["--secondary-bias-scope", "seed-only", "--seed-sampling-order", "sample-then-mask", "--predictor", "boltz", "--sequence-designer", "solublempnn"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ligand = root / "run_001" / "cycle_00" / "ligandmpnn"
            ligand.mkdir(parents=True)
            (ligand / "ligandmpnn.log").write_text("Design completed\n")
            self.assertEqual(audit.validate_seed_only_runtime(root, args, 1)["redesign_log_files_checked"], 1)
            (ligand / "secondary_structure_bias.json").write_text("{}")
            with self.assertRaisesRegex(audit.shared.AuditError, "per-residue MPNN"):
                audit.validate_seed_only_runtime(root, args, 1)

    def test_missing_redesign_log_rejected(self):
        args = ["--secondary-bias-scope", "seed-only", "--seed-sampling-order", "sample-then-mask", "--predictor", "boltz", "--sequence-designer", "solublempnn"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "run_001").mkdir()
            with self.assertRaisesRegex(audit.shared.AuditError, "missing redesign log"):
                audit.validate_seed_only_runtime(root, args, 1)

    def test_global_redesign_bias_and_loopkill_rejected(self):
        args = ["--secondary-bias-scope", "seed-only", "--seed-sampling-order", "sample-then-mask", "--predictor", "boltz", "--sequence-designer", "solublempnn"]
        with tempfile.TemporaryDirectory() as temporary:
            for flag, value in (("--loopkill", "0.5"), ("--mpnn-bias-aa-cycle1", "A:-0.5"), ("--mpnn-bias-aa-other", "E:-0.5")):
                with self.subTest(flag=flag), self.assertRaises(audit.shared.AuditError):
                    audit.validate_seed_only_runtime(Path(temporary), args + [flag, value], 1)

    def test_scientific_failure_does_not_fail_operational_gate(self):
        seed = {"run_001": {"x_positions": [1, 3, 5], "positions": [], "blocks": []}}
        report = {"method": {}, "arm_audits": {arm: {"audit_status": "audited_complete", "seed_plans": seed} for arm in ("beta", "mixed")}}
        gate = {"all_complete": True, "checks": {"all_jobs_completed_and_declared_arms_audited": True, "declared_balanced_trajectory_mean_rule_met": False}}
        audit.enrich_report(report, gate, "smoke")
        self.assertTrue(gate["passed"])
        self.assertFalse(gate["scientific_checks"]["declared_balanced_trajectory_mean_rule_met"])


if __name__ == "__main__":
    unittest.main()
