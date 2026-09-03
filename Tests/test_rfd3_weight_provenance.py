#!/usr/bin/env python3
"""Regression tests for the raw-vs-EMA RFdiffusion3 deployment boundary."""

from __future__ import annotations

import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "Sources/iProteinStudio/Resources/rfd3_overlay"


def load_helper():
    spec = importlib.util.spec_from_file_location("rfd3_weight_set_test", OVERLAY / "rfd3_weight_set.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def fake_safetensors(path: Path, metadata: dict[str, str]) -> None:
    header = json.dumps({"__metadata__": metadata}, separators=(",", ":")).encode()
    path.write_bytes(struct.pack("<Q", len(header)) + header)


class WeightProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.weights = load_helper()

    def test_default_selects_shadow_even_when_model_appears_first(self):
        raw = SimpleNamespace(diffusion_module=object())
        shadow = SimpleNamespace(diffusion_module=object())
        ema = SimpleNamespace(model=raw, shadow=shadow)
        wrapped = SimpleNamespace(module=ema)
        core, which = self.weights.select_core(wrapped)
        self.assertIs(core, shadow)
        self.assertEqual(which, "shadow (EMA)")

    def test_explicit_raw_is_available_only_as_an_opt_in(self):
        raw = SimpleNamespace(diffusion_module=object())
        shadow = SimpleNamespace(diffusion_module=object())
        core, which = self.weights.select_core(
            SimpleNamespace(model=raw, shadow=shadow), "model"
        )
        self.assertIs(core, raw)
        self.assertEqual(which, "model (raw)")
        with self.assertRaises(self.weights.WeightSetError):
            self.weights.resolve_weight_set("ema_typo")

    def test_artifact_gate_accepts_only_explicit_ema_metadata(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            valid = directory / "valid.safetensors"
            fake_safetensors(valid, {
                "source": "rfd3_latest.ckpt",
                "weight_set": "shadow",
                "which": "shadow (EMA)",
            })
            self.assertEqual(self.weights.assert_ema_artifact(valid)["weight_set"], "shadow")

            for name, metadata in (
                ("raw", {"weight_set": "model", "which": "model (raw)"}),
                ("legacy", {"which": "shadow (EMA)"}),
                ("unlabelled", {}),
            ):
                artifact = directory / f"{name}.safetensors"
                fake_safetensors(artifact, metadata)
                with self.assertRaises(self.weights.WeightSetError):
                    self.weights.assert_ema_artifact(artifact)

    def test_shipped_install_and_runtime_all_share_the_gate(self):
        installer = (OVERLAY / "install_rfd3.sh").read_text()
        setup = (ROOT / "Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh").read_text()
        runner = (OVERLAY / "scripts/generate_backbones.py").read_text()
        sync = (ROOT / "tools/sync_rfd3.sh").read_text()
        controller = (ROOT / "Sources/iProteinStudio/Core/RFD3Controller.swift").read_text()
        expected = "736e6f5e11ec70dea58903deb2290031e366d2b0b2478e63208a2541650a04d6"
        stale = "0beb87ff872d946a8af58428ae7c679eb364057bf12df77dba5994f6a0f1271b"
        self.assertIn(expected, installer)
        self.assertIn(expected, setup)
        self.assertNotIn(stale, installer)
        self.assertNotIn(stale, setup)
        self.assertIn("assert_ema_artifact(weights_path)", runner)
        self.assertIn("rfd3_ema_weights_current", setup)
        self.assertIn("rfd3_weight_set.py", sync)
        self.assertIn('metadata["weight_set"] == "shadow"', controller)
        self.assertIn('metadata["which"] == "shadow (EMA)"', controller)


if __name__ == "__main__":
    unittest.main()
