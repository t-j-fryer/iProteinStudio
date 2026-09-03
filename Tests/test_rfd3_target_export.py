#!/usr/bin/env python3
"""Regression test for residue-specific target atom names in MLX PDB output."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Sources/iProteinStudio/Resources/rfd3_overlay/scripts/generate_backbones.py"


def load_writer():
    # The test exercises only the pure PDB writer.  Stub optional MLX runtime
    # modules so it also runs on source-checkout test hosts without Apple MLX.
    mlx = types.ModuleType("mlx")
    mlx_core = types.ModuleType("mlx.core")
    mlx.core = mlx_core
    sys.modules.setdefault("mlx", mlx)
    sys.modules.setdefault("mlx.core", mlx_core)
    sys.modules.setdefault("rfd3_mlx", types.ModuleType("rfd3_mlx"))
    sampler = types.ModuleType("sampler")
    sampler.Sampler = object
    sys.modules.setdefault("sampler", sampler)
    featurizer = types.ModuleType("featurizer")
    featurizer.DENSE = {
        "CYS": [("N", "N"), ("CA", "CA"), ("C", "C"),
                ("O", "O"), ("CB", "CB"), ("SG", "V1")]
    }
    sys.modules.setdefault("featurizer", featurizer)
    weights = types.ModuleType("rfd3_weight_set")
    weights.assert_ema_artifact = lambda _path: {}
    sys.modules.setdefault("rfd3_weight_set", weights)
    spec = importlib.util.spec_from_file_location("target_export_contract", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TargetExportTests(unittest.TestCase):
    def test_generic_atom14_slot_is_restored_to_real_target_atom(self):
        module = load_writer()
        fixture = module.Fixture.__new__(module.Fixture)
        fixture.names = ["N", "CA", "C", "O", "CB", "V1"]
        fixture.tok = np.zeros(6, dtype=int)
        fixture.asym_id = np.array([1], dtype=int)
        fixture.restype = np.array([4], dtype=int)  # CYS
        fixture.target_protein_tokens = np.array([0], dtype=int)
        fixture.design_tokens = np.array([], dtype=int)
        fixture.ligand_tokens = np.array([], dtype=int)
        fixture.unindexed_tokens = np.array([], dtype=int)
        fixture.fixed_atoms = np.ones(6, dtype=bool)
        fixture.motif_source_residues = []
        fixture.requested_motif_atoms = {}
        fixture.ligand_code = "LG1"
        coords = np.arange(18, dtype=float).reshape(6, 3)

        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "target.pdb"
            fixture.write_pdb(coords, output)
            atoms = [line[12:16].strip() for line in output.read_text().splitlines()
                     if line.startswith("ATOM")]

        self.assertEqual(atoms, ["N", "CA", "C", "O", "CB", "SG"])
        self.assertNotIn("V1", atoms)


if __name__ == "__main__":
    unittest.main()
