from pathlib import Path
import tempfile
import unittest
from unittest import mock

import campaign as study
import audit


class CampaignContracts(unittest.TestCase):
    def test_two_strengths_across_seven_variants(self):
        self.assertEqual(len(study.CONFIG["arms"]), 14)
        variants = {(arm["predictor"], arm["model"]) for arm in study.CONFIG["arms"].values()}
        self.assertEqual(len(variants), 7)
        for variant in variants:
            strengths = {arm["strength"] for arm in study.CONFIG["arms"].values()
                         if (arm["predictor"], arm["model"]) == variant}
            self.assertEqual(strengths, {0, 1})

    def test_paired_seeds_and_required_msa(self):
        for arm in study.CONFIG["arms"].values():
            for phase, count, offset in (("pilot", 1, 0), ("remaining", 9, 1)):
                arguments = study.arguments_for(arm, phase)
                value = lambda flag: arguments[arguments.index(flag) + 1]
                self.assertEqual(value("--num-runs"), str(count))
                self.assertEqual(value("--num-opt-cycles"), "5")
                self.assertEqual(value("--binder-min-len"), "90")
                self.assertEqual(value("--binder-max-len"), "90")
                self.assertEqual(value("--binder-random-seed"), str(907000 + offset))
                self.assertEqual(value("--mpnn-seed"), str(1907000 + 1000 * offset))
                self.assertEqual(value("--negative-helix-constant"), str(arm["strength"]))
                self.assertIn("--require-target-msa", arguments)
                self.assertEqual(value("--target-msa-mode"), "auto")
                self.assertEqual(value("--sequence-designer"), "solublempnn")

    def test_target_fasta_and_a3m_are_query_matched(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sequence = root / "target.fasta"
            msa = root / "target.a3m"
            sequence.write_text(">target\nACDEFGHIK\n")
            msa.write_text(">query\nACDxxEFGHIK-\n>homolog\nACDEYGHIK--\n")
            target = study.validate_target("clean_target", sequence, msa)
            self.assertEqual(target["sequence"], "ACDEFGHIK")
            self.assertEqual(target["msa_records"], 2)
            self.assertEqual(target["msa_format"], "a3m")

    def test_target_fasta_and_stockholm_are_query_matched(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sequence = root / "target.fasta"
            msa = root / "target.sto"
            sequence.write_text(">target\nACDEFGHIK\n")
            msa.write_text("# STOCKHOLM 1.0\nquery ACDE-\nother ACDE-\nquery FGHIK\nother YGHIK\n//\n")
            target = study.validate_target("clean_target", sequence, msa)
            self.assertEqual(target["sequence"], "ACDEFGHIK")
            self.assertEqual(target["msa_records"], 2)
            self.assertEqual(target["msa_format"], "stockholm")

    def test_mismatched_msa_fails_loudly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sequence = root / "target.fasta"
            msa = root / "target.a3m"
            sequence.write_text("ACDEFGHIK\n")
            msa.write_text(">query\nACDEYGHIK\n>homolog\nACDEYGHIK\n")
            with self.assertRaisesRegex(RuntimeError, "does not exactly match"):
                study.validate_target("clean_target", sequence, msa)

    def test_prepare_freezes_target_and_reopens_without_source_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            sequence = root / "target.fasta"
            msa = root / "target.a3m"
            sequence.write_text(">target\nACDEFGHIK\n")
            msa.write_text(">query\nACDEFGHIK\n>homolog\nACDEYGHIK\n")
            output.mkdir()
            study.atomic(output / "stage_receipt.json", {"test": True})
            with mock.patch.object(study, "OUTPUT", output), \
                 mock.patch.object(study, "RUNTIME", root / "runtime"), \
                 mock.patch.object(study, "MANAGED_INPUTS", root / "runtime/validation_inputs/test"), \
                 mock.patch.object(study, "verify_stage", return_value={"test": True}):
                manifest = study.prepare("clean_target", sequence, msa)
                reopened = study.prepare()
            self.assertEqual(manifest, reopened)
            self.assertEqual(manifest["target"]["sequence"], "ACDEFGHIK")
            self.assertEqual(manifest["msa"]["records"], 2)
            template = Path(manifest["template"]["path"]).read_text()
            self.assertIn("id: A", template)
            self.assertIn("sequence: " + "X" * 90, template)
            self.assertIn("id: B", template)
            self.assertIn("sequence: ACDEFGHIK", template)

    def test_paired_contrast_uses_available_trajectory_pairs(self):
        left = {
            1: {"mean_helix": 0.40},
            2: {"mean_helix": 0.50},
            3: {"mean_helix": None},
        }
        right = {
            1: {"mean_helix": 0.20},
            2: {"mean_helix": 0.30},
            3: {"mean_helix": 0.10},
        }
        result = audit.paired(left, right, "helix")
        self.assertEqual(result["n_pairs"], 2)
        self.assertAlmostEqual(result["mean_difference"], -0.20)

    def test_native_cardinality_follows_resident_prediction_link(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            native = root / "_cycle_wave/cycle_00/batch_01/predictions/request/model_0.cif"
            native.parent.mkdir(parents=True)
            native.write_text("native structure\n")
            normalized = root / "run_001/cycle_00/pred_min/model_0.cif"
            normalized.parent.mkdir(parents=True)
            normalized.symlink_to(native)
            found = audit.native_structures(normalized.parents[1], "boltz", normalized)
            self.assertEqual(found, [native.resolve()])


if __name__ == "__main__":
    unittest.main()
