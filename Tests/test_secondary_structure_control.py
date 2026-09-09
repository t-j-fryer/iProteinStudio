#!/usr/bin/env python3
"""Contracts for deterministic iterative-design secondary-structure priors."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "Sources/iProteinStudio/Resources/pipeline/scripts/secondary_structure_control.py"
SPEC = importlib.util.spec_from_file_location("secondary_structure_control", HELPER)
assert SPEC and SPEC.loader
CONTROL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTROL)


class SecondaryStructureControlTests(unittest.TestCase):
    def test_no_bias_preserves_released_seed_stream(self) -> None:
        sequence, plan = CONTROL.generate_sequence(
            90, 90, 0, "boltz", 101, "none", 0.5, 0.5, 0.5, 0.5, 0.0
        )
        self.assertEqual(
            sequence,
            "TEFTSVLVEYVIDNRIDHTDWGFEYWIDQVAQVLNTGHQNNIWHQVKDGDEEIKLQQRIQNENIQRGLLHAAYSLQHRYSLYWDKLHPES",
        )
        self.assertEqual(plan["scientific_status"], "experimental-sequence-prior-not-fold-guarantee")
        self.assertTrue(all(position["region"] == "unconstrained" for position in plan["positions"]))

        anti_sequence, _ = CONTROL.generate_sequence(
            90, 90, 0, "boltz", 101, "antihelix", 0.5, 0.5, 0.5, 0.5, 0.0
        )
        self.assertEqual(
            anti_sequence,
            "TFFTSWMWFYWIDPSIDHVDWHGEYWIFRWARVMRTGHRPPIWHSWLDGDFEIKMSSSIRPFPISSGMMHDDYSMRHSYTNYWDLMHRFT",
        )

    def test_beta_plan_has_bounded_blocks_and_protected_edges(self) -> None:
        first = CONTROL.build_plan(90, 101, "beta", 0.0, 0.5, 0.5, 0.5)
        second = CONTROL.build_plan(90, 101, "beta", 0.0, 0.5, 0.5, 0.5)
        self.assertEqual(first, second)
        self.assertEqual(len(first["positions"]), 90)
        self.assertEqual([p["index"] for p in first["positions"]], list(range(1, 91)))
        for block in first["blocks"]:
            length = block["end"] - block["start"] + 1
            if block["kind"] == "strand":
                self.assertGreaterEqual(length, 5)
                self.assertLessEqual(length, 8)
                start = first["positions"][block["start"] - 1]
                end = first["positions"][block["end"] - 1]
                self.assertEqual((start["face"], end["face"]), ("edge", "edge"))
            else:
                self.assertGreaterEqual(length, 2)
                self.assertLessEqual(length, 5)

        for binder_length in range(5, 401):
            candidate = CONTROL.build_plan(binder_length, binder_length, "beta", 0, 0.5, 0.5, 0.5)
            self.assertEqual(sum(block["end"] - block["start"] + 1 for block in candidate["blocks"]),
                             binder_length)

    def test_mpnn_bias_is_position_specific_and_localizes_proline(self) -> None:
        plan = CONTROL.build_plan(90, 101, "mixed", 0.4, 0.5, 0.6, 0.5)
        bias = CONTROL.per_residue_bias(plan)
        self.assertEqual(len(bias), 90)
        strand = next(p for p in plan["positions"] if p["region"] == "strand" and not p["edge"])
        turn_core = next(p for p in plan["positions"] if p["region"] == "turn" and p["turn_core"])
        self.assertLess(bias[f"A{strand['index']}"]["P"], 0)
        self.assertGreater(bias[f"A{turn_core['index']}"]["P"], 0)
        self.assertLess(bias[f"A{strand['index']}"]["A"], 0)

        edge = next(p for p in plan["positions"] if p["face"] == "edge")
        self.assertGreater(bias[f"A{edge['index']}"]["D"], 0)
        self.assertLess(bias[f"A{edge['index']}"]["W"], 0)

    def test_scope_changes_redesign_only_not_cycle00(self) -> None:
        common = (90, 90, 0, "boltz", 101, "beta", 0.0, 0.5, 0.5, 0.5, 0.0)
        seed_only_sequence, seed_only_plan = CONTROL.generate_sequence(
            *common, application_scope="seed-only"
        )
        all_cycles_sequence, all_cycles_plan = CONTROL.generate_sequence(
            *common, application_scope="seed-and-cycles"
        )
        self.assertEqual(seed_only_sequence, all_cycles_sequence)
        self.assertEqual(seed_only_plan["positions"], all_cycles_plan["positions"])
        self.assertEqual(seed_only_plan["blocks"], all_cycles_plan["blocks"])
        self.assertEqual(CONTROL.per_residue_bias(seed_only_plan), {})
        self.assertTrue(CONTROL.per_residue_bias(seed_only_plan, phase="seed"))
        self.assertTrue(CONTROL.per_residue_bias(all_cycles_plan))

    def test_saved_plan_round_trip_and_invalid_strength(self) -> None:
        plan = CONTROL.build_plan(30, 7, "beta", 0.0, 0.5, 0.5, 0.5)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            CONTROL.write_json(path, plan)
            self.assertEqual(CONTROL.read_plan(path), json.loads(path.read_text()))
        with self.assertRaises(ValueError):
            CONTROL.build_plan(30, 7, "beta", 0.0, 1.1, 0.5, 0.5)
        with self.assertRaises(ValueError):
            CONTROL.build_plan(30, 7, "beta", 0.0, 0.5, 0.5, 0.5, "everywhere")

    def test_complete_sequence_is_sampled_before_independent_mask(self) -> None:
        masks = []
        for mode in ("beta", "mixed"):
            def generate(percent):
                return CONTROL.generate_sequence(
                    90, 90, percent, "boltz", 155161, mode, .5, 1, 1, .5, 0,
                    application_scope="seed-only", sampling_order="sample-then-mask")
            full, full_plan = generate(0)
            masked, plan = generate(50)
            self.assertEqual((masked, plan), generate(50))
            self.assertEqual(plan["unmasked_sequence"], full)
            self.assertEqual(plan["unmasked_sequence"], full_plan["unmasked_sequence"])
            self.assertEqual(masked.count("X"), 45)
            self.assertEqual(masked, "".join("X" if i in plan["x_positions"] else aa
                                           for i, aa in enumerate(full, 1)))
            self.assertEqual(CONTROL.per_residue_bias(plan), {})
            masks.append(plan["x_positions"])
        self.assertEqual(masks[0], masks[1])

    def test_complete_sequence_mode_rejects_sustained_or_unbiased_usage(self) -> None:
        for mode, scope in (("beta", "seed-and-cycles"), ("none", "seed-only")):
            with self.assertRaises(ValueError):
                CONTROL.generate_sequence(90, 90, 50, "boltz", 1, mode, .5, 1, 1, .5, 0,
                                          scope, "sample-then-mask")


if __name__ == "__main__":
    unittest.main()
