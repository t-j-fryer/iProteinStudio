#!/usr/bin/env python3
"""Scientific integrity contract for the bundled alpha-cobratoxin target."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "Sources/iProteinStudio/Resources/examples/acbx"
SWIFT = ROOT / "Sources/iProteinStudio/Models/ExampleTarget.swift"
APP_PATHS = ROOT / "Sources/iProteinStudio/Core/AppPaths.swift"
EXPECTED_DISULFIDES = {(3, 20), (14, 41), (26, 30), (45, 56), (57, 62)}
AA1 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}


class ACbxExampleIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.lines = (EXAMPLE / "target.pdb").read_text().splitlines()
        self.atoms = [line for line in self.lines if line.startswith("ATOM")]

    def test_exact_experimental_target_and_sequence(self):
        self.assertTrue(any("RCSB PDB 1CTX" in line for line in self.lines))
        self.assertEqual(len(self.atoms), 541)
        self.assertEqual({line[21] for line in self.atoms}, {"B"})
        residues = {}
        for line in self.atoms:
            residues.setdefault(int(line[22:26]), line[17:20].strip())
        structure_sequence = "".join(AA1[residues[index]] for index in range(1, 72))
        fasta_sequence = "".join(
            line.strip() for line in (EXAMPLE / "target.fasta").read_text().splitlines()
            if not line.startswith(">")
        )
        self.assertEqual(structure_sequence, fasta_sequence)

    def test_all_five_disulfides_are_present(self):
        sulfurs = {
            int(line[22:26]): np.array([
                float(line[30:38]), float(line[38:46]), float(line[46:54])
            ])
            for line in self.atoms if line[12:16].strip() == "SG"
        }
        self.assertEqual(set(sulfurs), {3, 14, 20, 26, 30, 41, 45, 56, 57, 62})
        close_pairs = {
            (left, right)
            for left, left_xyz in sulfurs.items()
            for right, right_xyz in sulfurs.items()
            if left < right and np.linalg.norm(left_xyz - right_xyz) < 2.3
        }
        self.assertEqual(close_pairs, EXPECTED_DISULFIDES)
        self.assertEqual(sum(line.startswith("SSBOND") for line in self.lines), 5)

    def test_rfd3_worked_example_uses_whole_surface_by_default(self):
        source = SWIFT.read_text()
        apply_start = source.index("extension RFD3Request")
        protein_case = source.index("case .protein:", apply_start)
        ligand_case = source.index("case .smallMolecule:", protein_case)
        block = source[protein_case:ligand_case]
        self.assertIn("originStrategy = .surfaceScan", block)
        self.assertIn("conditions = [:]", block)
        self.assertNotIn("originStrategy = .hotspots", block)

    def test_corrected_example_refreshes_existing_installations(self):
        source = APP_PATHS.read_text()
        start = source.index("static func stageExamples()")
        end = source.index("static func stageScaffoldMSAs()", start)
        block = source[start:end]
        self.assertIn("stageBundledItem(item, at: dest)", block)
        self.assertNotIn("if !fm.fileExists(atPath: dest.path)", block)


if __name__ == "__main__":
    unittest.main()
