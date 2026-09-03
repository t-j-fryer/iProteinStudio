#!/usr/bin/env python3
"""Executable contracts for protein-surface ORI placement and quota wiring."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RFD3 = ROOT / "Sources/iProteinStudio/Resources/rfd3"
OVERLAY = ROOT / "Sources/iProteinStudio/Resources/rfd3_overlay/scripts"
EXAMPLE = ROOT / "Sources/iProteinStudio/Resources/examples/p53_mdm2/1YCR.pdb"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


try:
    import biotite  # noqa: F401 - runtime capability probe
    import yaml  # noqa: F401
    HAVE_RFD3_DEPS = True
except ImportError:
    HAVE_RFD3_DEPS = False


@unittest.skipUnless(HAVE_RFD3_DEPS, "run with the managed RFdiffusion3 Python environment")
class SurfaceOriginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(RFD3))
        cls.surface = load("surface_origins_contract", RFD3 / "surface_origins.py")
        cls.prepare = load("prepare_surface_contract", RFD3 / "prepare_campaign.py")
        cls.design = load("design_from_yaml_contract", OVERLAY / "design_from_yaml.py")

    def test_policy_defaults_to_surface_and_keeps_positioning_distinct(self):
        scan = {"conditions": {}}
        self.prepare._validate_binding_site_mode(scan, ["A"])
        self.assertEqual(scan["binding_site_mode"], "surface_scan")
        self.assertNotIn("infer_ori_strategy", scan)

        targeted = {"conditions": {"A50": ["hotspot"]}}
        self.prepare._validate_binding_site_mode(targeted, ["A"])
        self.assertEqual(targeted["binding_site_mode"], "targeted_epitope")
        self.assertEqual(targeted["infer_ori_strategy"], "hotspots")

        broad = {
            "binding_site_mode": "surface_patch",
            "surface_patch_residues": ["A50", "A54"],
            "conditions": {},
        }
        self.prepare._validate_binding_site_mode(broad, ["A"])
        self.assertNotIn("infer_ori_strategy", broad)
        self.assertFalse(any("hotspot" in values for values in broad["conditions"].values()))

    def test_whole_surface_is_deterministic_external_and_budget_bounded(self):
        first = self.surface.plan_surface_scan(EXAMPLE, ["A"], 8)
        second = self.surface.plan_surface_scan(EXAMPLE, ["A"], 8)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)
        self.assertTrue(all(item["target_clearance_a"] >= 4.0 for item in first))
        self.assertTrue(all(item["placement_mode"] == "surface-scan" for item in first))
        self.assertTrue(all(item["anchor_residues"] for item in first))

    def test_broad_region_is_geometric_not_hotspot_conditioning(self):
        origin = self.surface.plan_surface_patch(EXAMPLE, ["A"], ["A50", "A54"])[0]
        self.assertEqual(origin["placement_mode"], "surface-patch")
        self.assertEqual(origin["anchor_residues"], ["A50", "A54"])
        self.assertGreaterEqual(origin["target_clearance_a"], 4.0)
        self.assertNotIn("hotspot", json.dumps(origin).lower())

    def test_origin_variants_get_exact_reproducible_quotas_and_fixtures(self):
        origins = [
            {"label": "one", "xyz": [1.0, 2.0, 3.0]},
            {"label": "two", "xyz": [4.0, 5.0, 6.0]},
            {"label": "three", "xyz": [7.0, 8.0, 9.0]},
        ]
        with tempfile.TemporaryDirectory() as raw:
            campaign = Path(raw)
            fixtures = campaign / "rfd3" / "fixtures"
            fixtures.mkdir(parents=True)
            for oi in range(1, 4):
                (fixtures / f"oracle_demo_O{oi:02d}.npz").touch()
            manifest_path = self.design.build_fixtures(
                {"input": str(EXAMPLE), "contig": "60-70,/0,A25-109"},
                {"num_designs": 7, "timesteps": 20, "n_recycle": 1, "seed_base": 10},
                "demo", [60, 70], campaign, {}, False, origins=origins,
            )
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(sum(item["quota"] for item in manifest["bins"]), 7)
            self.assertEqual(len(manifest["bins"]), 3)
            self.assertEqual(manifest["origin_plan"], origins)
            specs = [json.loads(Path(item["input_json"]).read_text()) for item in manifest["bins"]]
            flattened = [next(iter(value.values())) for value in specs]
            self.assertTrue(all("ori_token" in value for value in flattened))
            self.assertTrue(all("select_hotspots" not in value for value in flattened))


if __name__ == "__main__":
    unittest.main()
