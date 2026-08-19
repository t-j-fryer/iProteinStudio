#!/usr/bin/env python3
"""Optional live-RCSB acceptance for generic exact-ligand matching.

Unlike the deterministic unit contracts, this requires network access and live
external data. It deliberately uses chemically unrelated ligands and asserts
identities rather than exact entry counts, which can grow over time.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from rdkit import Chem, RDLogger


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "Sources/iProteinStudio/Resources/rfd3/ligand_intelligence.py"
spec = importlib.util.spec_from_file_location("live_ligand_intelligence", MODULE)
assert spec and spec.loader
intelligence = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = intelligence
spec.loader.exec_module(intelligence)
RDLogger.DisableLog("rdApp.*")

LIGANDS = {
    "caffeine": ("Cn1c(=O)c2c(ncn2C)n(C)c1=O", "CFF"),
    "aspirin": ("CC(=O)Oc1ccccc1C(=O)O", "AIN"),
    "(S)-ibuprofen": ("CC(C)Cc1ccc(cc1)[C@@H](C)C(=O)O", "IZP"),
    "beta-D-glucose": (
        "C([C@@H]1[C@H]([C@@H]([C@H]([C@H](O1)O)O)O)O)O", "GLC"
    ),
    "acetate": ("CC(=O)[O-]", "ACT"),
}


def identity_matrix() -> None:
    for name, (smiles, expected_ccd) in LIGANDS.items():
        molecule = Chem.MolFromSmiles(smiles)
        candidates = intelligence.rcsb_chemical_search(smiles, 30)
        exact = intelligence.confirm_identical_ccds(candidates, molecule, 30)
        assert expected_ccd in exact, f"{name}: expected {expected_ccd}, got {exact}"
        entries = intelligence.rcsb_entries_for_ccd(expected_ccd, 10, 30)
        assert entries, f"{name}: {expected_ccd} had no PDB entries"
        print(f"{name}: {len(candidates)} candidates -> {exact}; {len(entries)} sampled entries")


def conformer_matching() -> None:
    for name in ("caffeine", "aspirin"):
        smiles, expected_ccd = LIGANDS[name]
        molecule = Chem.MolFromSmiles(smiles)
        core = set(range(molecule.GetNumAtoms()))
        ensemble, energies, _ = intelligence.generate_ensemble(molecule, 20)
        kept, _ = intelligence.filter_by_strain(energies, 30)
        conformers = [conformer for conformer, _, _ in kept]
        matrix = intelligence.core_rmsd_matrix(ensemble, conformers, core)
        clusters, cutoff = intelligence.cluster_adaptively(matrix, max_states=4)
        pdb = intelligence.experimental_conformers(smiles, {
            "network_timeout": 30,
            "max_pdb_entries": 10,
        })
        assert expected_ccd in pdb["ccd_codes"]
        assert pdb["instances"], f"{name}: no experimental coordinates retrieved"
        support = intelligence.match_experimental_to_clusters(
            ensemble, conformers, clusters, core, pdb["instances"],
            match_cutoff=max(1.5, cutoff),
        )
        assert support.get("_matched", 0) > 0, f"{name}: no coordinates matched"
        print(
            f"{name}: {support.get('_matched', 0)}/{len(pdb['instances'])} "
            "experimental coordinates matched"
        )


def main() -> None:
    identity_matrix()
    conformer_matching()
    print("PASS live generic ligand PDB acceptance")


if __name__ == "__main__":
    main()
