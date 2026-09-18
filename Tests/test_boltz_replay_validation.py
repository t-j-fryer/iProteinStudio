"""Exercise RNG preservation/replay with real torch streams, without a model."""
import importlib.util
from pathlib import Path
import random
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
try:
    import numpy as np
    import torch
    from boltz.data.module.inferencev2 import PredictionDataset
    MPS_AVAILABLE = torch.backends.mps.is_available()
except ImportError:
    MPS_AVAILABLE = False

SCRIPTS = Path(__file__).resolve().parents[1] / "Sources/iProteinStudio/Resources/pipeline/scripts"
sys.path.insert(0, str(SCRIPTS))
from boltz_replay_validation import install_rng_replay, validate, checksum


class PreflightTests(unittest.TestCase):
    def test_requires_frozen_conformer_and_rejects_tampered_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            names = ["inputs/ligand_atom_map.json", "inputs/nise_config.json", "inputs/L000/L000.yaml",
                     "inputs/L000/completed.json"]
            names += [f"inputs/L000/processed/{folder}/L000.{ext}" for folder, ext in
                      (("records", "json"), ("structures", "npz"), ("constraints", "npz"), ("mols", "pkl"))]
            for name in names:
                path = out / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("fixture")
            receipt = dict(input=dict(phase="structure", seed=0, potentials=True, pocket=dict(force=True)),
                           result=dict(timing=dict(completed_jobs=1)))
            (out / "inputs/L000/completed.json").write_text(json.dumps(receipt))
            config = dict(schema=1, output=str(out), potentials=False, phase="structure", seed=0,
                          ids=["L000"], files={name: checksum(out / name) for name in names})
            self.assertEqual(len(validate(out, config)), len(names))
            missing = dict(config, files={k: v for k, v in config["files"].items() if not k.endswith(".pkl")})
            with self.assertRaisesRegex(ValueError, "required frozen"):
                validate(out, missing)
            for key, value in (("potentials", True), ("phase", "complete"), ("seed", 8), ("ids", ["L000", "L000"])):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    validate(out, dict(config, **{key: value}))
            v2 = dict(config, schema=2, potentials=True, fk_steering=False, trace_steps=[1, 50, 200])
            with self.assertRaisesRegex(ValueError, "required frozen"):
                validate(out, v2)
            for suffix in ("features.pt", "prediction.pt", "features.sha256"):
                name = f"inputs/rng/L000_{suffix}"
                path = out / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("fixture")
                names.append(name)
            v2["files"] = {name: checksum(out / name) for name in names}
            self.assertEqual(len(validate(out, v2)), len(names))
            for key, value in (("fk_steering", True), ("potentials", False),
                               ("trace_steps", [1, 50]), ("trace_steps", [1, 200, 200]),
                               ("trace_steps", [True, 200])):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    validate(out, dict(v2, **{key: value}))
            (out / "inputs/L000/processed/mols/L000.pkl").write_text("different conformer")
            with self.assertRaisesRegex(ValueError, "changed"):
                validate(out, config)


@unittest.skipUnless(MPS_AVAILABLE, "Managed Boltz environment and MPS required for the replay contract")
class ReplayTests(unittest.TestCase):
    def test_preserves_capture_and_replays_all_streams_and_checks_features(self):
        def draws():
            return [random.random(), float(np.random.rand()), float(torch.rand(1)),
                    float(torch.rand(1, device="mps").cpu())]
        def seed():
            random.seed(7); np.random.seed(7); torch.manual_seed(7); torch.mps.manual_seed(7)
        def item(dataset, index):
            return dict(record=[dataset.manifest.records[index]], x=torch.tensor(draws()))
        def step(batch, index, dataloader_idx=0):
            return draws()
        dataset = SimpleNamespace(manifest=SimpleNamespace(records=[SimpleNamespace(id="L000")]))
        seed()
        reference_features = item(dataset, 0)
        reference_result = step(reference_features, 0)
        with tempfile.TemporaryDirectory() as tmp:
            seed()
            capture = SimpleNamespace(model=SimpleNamespace(predict_step=step))
            with patch.object(PredictionDataset, "__getitem__", item):
                install_rng_replay(capture, "capture", tmp)
                features = PredictionDataset.__getitem__(dataset, 0)
                actual = capture.model.predict_step(features, 0)
            self.assertTrue(torch.equal(features["x"], reference_features["x"]))
            self.assertEqual(actual, reference_result)
            draws(); draws()  # Simulate random consumption by an earlier batch item.
            replay = SimpleNamespace(model=SimpleNamespace(predict_step=step))
            with patch.object(PredictionDataset, "__getitem__", item):
                install_rng_replay(replay, "replay", tmp)
                features2 = PredictionDataset.__getitem__(dataset, 0)
                actual2 = replay.model.predict_step(features2, 12)
            self.assertTrue(torch.equal(features["x"], features2["x"]))
            self.assertEqual(actual, actual2)
            features2["x"] += 1
            with self.assertRaisesRegex(ValueError, "features differ"):
                replay.model.predict_step(features2, 0)


if __name__ == "__main__":
    unittest.main()
