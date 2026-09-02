#!/usr/bin/env python3
"""Offline contracts for Apple-GPU predictor correctness safeguards."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "Sources/iProteinStudio/Resources/pipeline/scripts"
RESOURCES = ROOT / "Sources/iProteinStudio/Resources"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PredictorSafetyTests(unittest.TestCase):
    def test_intellifold_patch_is_atomic_and_idempotent(self):
        compatibility = load("intellifold_mps_compat", SCRIPTS / "intellifold_mps_compat.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            openfold = root / "src/IntelliFold/intellifold/openfold"
            diffusion = openfold / "model/diffusion.py"
            conversion = openfold / "utils/atom_token_conversion.py"
            diffusion.parent.mkdir(parents=True)
            conversion.parent.mkdir(parents=True)
            diffusion.write_text("before\n" + compatibility.PAIR_OLD + "after\n")
            conversion.write_text(
                "def aggregate_fn_advanced(original_seqs, attention_mask):\n"
                "    aggregated_seqs[i][output_attention_mask] = original_seqs[i][attention_mask]\n"
                "    original_seq[attention_mask] = aggregated_seq[output_attention_mask]\n\n"
                "def slice_at_dim(t):\n    pass\n\n"
                "def repeat_consecutive_with_lens_advanced(feats, lens):\n"
                "    output_indices = output_indices.scatter(1, indices, values)\n"
                "    output = torch.gather(feats, dim=1, index=indices)\n\n"
                "def pad_and_window(t):\n    pass\n"
            )
            self.assertEqual(compatibility.patch_source(root), "applied")
            self.assertEqual(compatibility.patch_source(root), "already applied")
            diffusion_text = diffusion.read_text()
            conversion_text = conversion.read_text()
            self.assertNotIn(compatibility.PAIR_OLD, diffusion_text)
            self.assertEqual(diffusion_text.count(compatibility.PAIR_NEW), 1)
            self.assertIn("Compact valid atoms without MPS boolean advanced indexing", conversion_text)
            self.assertIn("Repeat token features by atom counts without MPS scatter/gather", conversion_text)
            self.assertNotIn("output_indices.scatter", conversion_text)
            self.assertNotIn("torch.gather(feats", conversion_text)

    def test_boltz_routes_use_the_managed_mps_launcher(self):
        launchers = {
            "plain prediction": RESOURCES / "rfd3/predict_batch.py",
            "RFD3 target prep": RESOURCES / "rfd3/rfd3_protein_campaign.py",
            "RFD3 predictor": RESOURCES / "rfd3_overlay/scripts/run_predictors.py",
            "RFD3 affinity": RESOURCES / "rfd3_overlay/scripts/studio_runtime.py",
            "iterative design": RESOURCES / "pipeline/nanohunter_run.sh",
            "resident design": SCRIPTS / "resident_predictor.py",
        }
        for label, path in launchers.items():
            with self.subTest(label=label):
                text = path.read_text()
                self.assertIn("boltz_mps.py", text)
                self.assertNotIn('"bin" / "boltz"', text)
        wrapper = (SCRIPTS / "boltz_mps.py").read_text()
        self.assertIn('kwargs["precision"] = 32', wrapper)
        self.assertIn("MPSCorrectnessBoundary", wrapper)
        self.assertIn("torch.mps.empty_cache()", wrapper)
        self.assertIn("CPU execution is forbidden", wrapper)
        self.assertIn("managed_assets", wrapper)
        self.assertNotIn("urlretrieve", wrapper)

    def test_all_two_pytorch_launchers_gate_output_geometry(self):
        boltz = (SCRIPTS / "boltz_mps.py").read_text()
        intellifold = (SCRIPTS / "intellifold_predict.py").read_text()
        resident = (SCRIPTS / "resident_predictor.py").read_text()
        for text in (boltz, intellifold, resident):
            self.assertIn("validate_prediction_geometry.py", text)
        validator = (SCRIPTS / "validate_prediction_geometry.py").read_text()
        self.assertIn("MAX_CA_CA = 4.5", validator)
        self.assertIn("MAX_PEPTIDE_CN = 2.2", validator)
        self.assertNotIn("import gemmi", validator)


if __name__ == "__main__":
    unittest.main()
