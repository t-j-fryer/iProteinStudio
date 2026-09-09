#!/usr/bin/env python3
"""Initialization lifecycle contracts using synthetic, explicitly labelled assessments."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Sources/iProteinStudio/Resources/pipeline/scripts"))
import initialization_refinement as refinement
from initialization_assessment import assess, validate_policy
from secondary_structure_control import generate_sequence, per_residue_bias


class AssessmentTests(unittest.TestCase):
    policy = dict(max_attempts=3, min_uncertain_coil_length=4, confidence_threshold=50)

    def test_short_loops_and_long_confident_coil_do_not_trigger_refinement(self):
        for codes, confidence in (("aaacccbbb", [20] * 9), ("c" * 12, [90] * 12)):
            result = assess(codes, confidence, self.policy)
            self.assertTrue(result["eligible"])
            self.assertEqual(result["reconsider_regions"], [])

    def test_only_contiguous_individually_uncertain_coil_is_selected(self):
        result = assess("aaccccccccbb", [90, 90, 20, 20, 20, 20, 90, 20, 20, 20, 90, 90], self.policy)
        self.assertEqual(result["reconsider_regions"], [{"start": 3, "end": 6, "mean_confidence": 20}])
        self.assertFalse(result["eligible"])
        self.assertFalse(result["coil_segments"][0]["terminal"])
        self.assertTrue(assess("c" * 5, [50] * 5, self.policy)["eligible"])

    def test_invalid_or_missing_data_never_pass(self):
        for codes, confidence in (("", []), ("cx", [20, 20]), ("cc", [30]),
                                  ("cc", [float("nan"), 40]), ("cc", [True, 40]),
                                  ("cc", [101, 40]), ("cc", [float("inf"), 40])):
            with self.assertRaises(ValueError):
                assess(codes, confidence, self.policy)
        for key, value in (("max_attempts", True), ("max_attempts", 0),
                           ("min_uncertain_coil_length", 1.2), ("confidence_threshold", float("nan"))):
            with self.assertRaises(ValueError):
                validate_policy({**self.policy, key: value})


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.journal = refinement.Refinement(self.root / "journal")
        sequence, plan = generate_sequence(24, 24, 50, "boltz", 7, "mixed", .5, .5, .5, .5, 0,
                                           "seed-only", "sample-then-mask")
        self.config = dict(sequence=sequence, plan=plan, predictor="boltz",
                           policy=dict(max_attempts=3, min_uncertain_coil_length=4, confidence_threshold=50))
        self.journal.configure(self.config)

    def predict(self):
        structure = self.root / "synthetic.pdb"
        structure.write_text("SYNTHETIC PREDICTOR ARTIFACT; parsed only by the mocked assessor\n")
        confidence = self.root / "confidence.json"
        confidence.write_text('{"synthetic":true}')
        yaml = self.root / "input.yaml"
        yaml.write_text("synthetic: true\n")
        return self.journal.preserve_prediction(structure, confidence, yaml)

    def assessment(self, eligible):
        codes = "a" * 4 + "c" * 8 + "b" * 12
        result = assess(codes, [90 if eligible else 20] * 24, self.config["policy"])
        result["provenance"] = {"assignment": "synthetic test fixture"}
        with patch.object(refinement, "assess_structure", return_value=result):
            return self.journal.assess()

    def test_original_can_be_selected_and_terminal_actions_fail(self):
        self.assertEqual(self.predict()["state"], "awaiting_assessment")
        self.assertEqual(self.assessment(True)["state"], "acceptable")
        self.assertFalse(self.journal.status()["eligible_for_normal_cycling"])
        self.assertEqual(self.journal.select()["selected_attempt"], 0)
        self.assertTrue(self.journal.status()["eligible_for_normal_cycling"])
        for action in (self.journal.propose, self.journal.assess, self.journal.select, self.predict):
            with self.assertRaises(ValueError):
                action()

    def test_reassessment_and_selection_preserve_original_and_scope(self):
        original = (self.journal.root / "attempt_000000/input.json").read_bytes()
        self.predict()
        self.assessment(False)
        self.assertEqual(self.journal.propose()["index"], 1)
        proposal = refinement.read_json(self.journal.root / "attempt_000001/input.json")
        self.assertEqual(proposal["reconsider_positions"], list(range(5, 13)))
        self.assertTrue(all(change["position"] in range(5, 13) for change in proposal["changes"]))
        self.assertEqual(proposal["sequence"].count("X"), self.config["sequence"].count("X"))
        self.assertEqual(proposal["plan"]["positions"], self.config["plan"]["positions"])
        self.assertEqual(per_residue_bias(proposal["plan"]), {})
        self.predict()
        self.assessment(True)
        self.assertEqual(self.journal.select()["selected_attempt"], 1)
        self.assertEqual((self.journal.root / "attempt_000000/input.json").read_bytes(), original)
        self.assertTrue((self.journal.root / "attempt_000000/prediction/model_0.pdb").exists())

    def test_budget_includes_original_and_exhaustion_is_an_explicit_failure(self):
        for index in range(3):
            self.predict()
            state = self.assessment(False)
            if index < 2:
                self.journal.propose()
        self.assertEqual(state["state"], "budget_exhausted")
        self.assertEqual(state["remaining_attempts"], 0)
        self.assertIsNone(state["selected_attempt"])
        decision = refinement.read_json(self.journal.root / "attempt_000002/assessment/decision.json")
        self.assertEqual(decision["state"], "budget_exhausted")
        with self.assertRaises(ValueError):
            self.journal.select()
        with self.assertRaises(ValueError):
            self.journal.propose()

    def test_resuming_every_stage_keeps_state_without_new_attempts(self):
        for action in (lambda: None, self.predict, lambda: self.assessment(False), self.journal.propose,
                       self.predict, lambda: self.assessment(True), self.journal.select):
            action()
            expected = self.journal.status()
            self.journal = refinement.Refinement(self.journal.root)
            self.assertEqual(self.journal.configure(self.config), expected)

    def test_configuration_changes_fail_on_resume(self):
        for key, value in (("predictor", "intellifold"), ("sequence", "A" * 24)):
            with self.assertRaises(ValueError):
                self.journal.configure({**self.config, key: value})
        changed = copy.deepcopy(self.config)
        changed["policy"]["max_attempts"] += 1
        with self.assertRaises(ValueError):
            self.journal.configure(changed)

    def test_artifact_mutation_and_gaps_are_detected(self):
        self.predict()
        path = self.journal.root / "attempt_000000/prediction/model_0.pdb"
        original = path.read_bytes()
        path.write_text("altered")
        with self.assertRaises(ValueError):
            self.journal.status()
        path.write_bytes(original)
        (self.journal.root / "attempt_000000").rename(self.journal.root / "attempt_000001")
        with self.assertRaises(ValueError):
            self.journal.status()

    def test_failed_assessment_preserves_prediction_and_can_resume(self):
        self.predict()
        with patch.object(refinement, "assess_structure", side_effect=ValueError("invalid coordinates")):
            with self.assertRaisesRegex(ValueError, "invalid coordinates"):
                self.journal.assess()
        self.assertEqual(self.journal.status()["state"], "awaiting_assessment")
        self.assertEqual(self.assessment(True)["state"], "acceptable")

    def test_interrupted_publication_does_not_consume_another_attempt(self):
        self.predict()
        self.assessment(False)
        with patch.object(refinement.os, "rename", side_effect=OSError("interrupted publication")):
            with self.assertRaises(OSError):
                self.journal.propose()
        self.assertEqual(self.journal.status()["recorded_attempts"], 1)
        self.assertEqual(list(self.journal.root.glob(".staging-*")), [])
        self.assertEqual(self.journal.propose()["recorded_attempts"], 2)

    def test_unassessed_prediction_cannot_generate_or_select(self):
        self.predict()
        with self.assertRaises(ValueError):
            self.journal.propose()
        with self.assertRaises(ValueError):
            self.journal.select()

    def test_retired_cli_proposals_leave_historical_journal_unchanged(self):
        self.predict()
        self.assessment(False)
        command = [sys.executable, refinement.__file__, "propose", "--root", str(self.journal.root)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(subprocess.run, command, capture_output=True, text=True) for _ in range(2)]
            results = [future.result() for future in futures]
        self.assertTrue(all(result.returncode != 0 for result in results))
        self.assertEqual(self.journal.status()["recorded_attempts"], 1)


class RegionalSamplingTests(unittest.TestCase):
    def test_both_sampling_orders_preserve_unselected_residues_masks_and_position_plan(self):
        for order in ("mask-first", "sample-then-mask"):
            args = (30, 30, 50, "boltz", 71, "mixed", .5, .5, .5, .5, .2, "seed-only", order)
            original, plan = generate_sequence(*args)
            def sample():
                return generate_sequence(*args[:4], 72, *args[5:], position_plan=plan,
                                         previous_sequence=original, reconsider_positions=list(range(8, 20)))
            sequence, proposal = sample()
            self.assertEqual((sequence, proposal), sample())
            self.assertEqual((sequence[:7], sequence[19:]), (original[:7], original[19:]))
            self.assertEqual(sequence.count("X"), original.count("X"))
            self.assertEqual(proposal["positions"], plan["positions"])
            self.assertEqual(proposal["blocks"], plan["blocks"])
            self.assertEqual(per_residue_bias(proposal), {})


if __name__ == "__main__":
    unittest.main()
