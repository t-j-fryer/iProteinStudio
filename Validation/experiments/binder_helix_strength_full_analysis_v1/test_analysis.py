#!/usr/bin/env python3
"""Tests for the complete v7 binder helix-control analysis."""
import json
import unittest

import numpy as np

import analyse


class AnalysisTests(unittest.TestCase):
    def test_bootstrap_unit_is_ten_paired_trajectories(self):
        self.assertEqual(analyse.bounds(np.ones(10)), [1.0, 1.0])
        with self.assertRaisesRegex(RuntimeError, "ten trajectories"):
            analyse.bounds(np.arange(5))

    def test_pairing_reproduces_frozen_campaign_report(self):
        generated = json.loads((analyse.OUT / "paired_contrasts.json").read_text())
        frozen = json.loads((analyse.STUDY / "analysis/report.json").read_text())["paired_contrasts"]
        for engine in analyse.ENGINES:
            for metric in analyse.ALL_METRICS:
                self.assertEqual(generated[engine + ":0->1"][metric], frozen[engine + "_h1"][metric])

    def test_complete_output_contract(self):
        required = {"REPORT.md", "GALLERY.html", "FIGURES.pdf", "summary.csv", "structures.csv",
                    "trajectories.csv", "geometry_events.csv", "paired_contrasts.json", "integrity.json",
                    "artifact_sha256.json", "helix_control_complete.zip"}
        required |= {f"{index:02d}_{name}.{extension}"
                     for index, name in enumerate(("overview", "paired_effects", "cycle_dynamics",
                                                   "final_outcomes", "geometry_recovery"), 1)
                     for extension in ("svg", "png", "pdf")}
        self.assertTrue(required <= {path.name for path in analyse.OUT.iterdir()})


if __name__ == "__main__":
    unittest.main()
