#!/usr/bin/env python3
"""Backbone + ligand RMSD: every holo fold vs. its design, and apo vs. holo vs. design for the top 100.

Backbone (binder) comparisons use Cα only: RFD3's exported backbone PDBs only
ever contain {N, CA, C, O} for the designed chain (no real sidechain
geometry, see ``generate_backbones.py``'s ``BINDER_ATOMS``), and since both
sides of every backbone comparison here are foldings/designs of the *same*
sequence, matching Cα by residue index (as written) is unambiguous.

Ligand comparisons match heavy atoms by *position* in the PDB file (verified
empirically, not assumed): RFD3's own exported backbone PDBs do NOT carry the
Boltz-convention atom names from the input CCD file through to their HETATM
records -- ``generate_backbones.py``'s ``Fixture.write_pdb`` emits bare
element symbols ("C", "O", ...) for every ligand atom, all identical within
an element, so name-based matching (as RFD3's own ``analyze_campaign.py``
does for its ligand-frame alignment, and as originally attempted here) always
finds zero matches against a design PDB. What *is* preserved is atom order:
both the design PDB (via the CCD file's own atom listing, in
``Chem.MolFromSmiles(smiles)`` order) and Boltz's predicted ligand chain
(same SMILES, same RDKit parse order -- see NanoHunter's
``lasermpnn_prepare_input.py`` comment confirming this for Boltz) enumerate
heavy atoms identically, confirmed by comparing element sequences on a real
fixture/fold pair. Positions are used to align coordinates, but the element
sequence is still checked first and comparisons are skipped (not silently
wrong) if it ever doesn't match -- the same safety net
``nise_lib.self_consistency`` relies on for its own (same-pipeline) case.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

import numpy as np
import studio_runtime


BACKBONE_ATOMS = {"N", "CA", "C", "O"}


def pdb_atom_records(pdb_path: str, chain: str, include_hetatm: bool = False) -> list[dict]:
    records = []
    for line in Path(pdb_path).read_text().splitlines():
        allowed = ("ATOM", "HETATM") if include_hetatm else ("ATOM",)
        if not line.startswith(allowed) or len(line) < 54 or line[21] != chain:
            continue
        element = line[76:78].strip() if len(line) >= 78 else ""
        atom = line[12:16].strip()
        if not element:
            element = atom.lstrip("0123456789")[:1]
        if element.upper() == "H":
            continue
        records.append({
            "residue": (int(line[22:26]), line[26].strip()),
            "atom": atom,
            "xyz": np.array([float(line[30:38]), float(line[38:46]), float(line[46:54])]),
        })
    return records


def apo_holo_preorganisation(nise_lib, holo_pdb: str, apo_pdb: str,
                             cutoff: float = 6.0) -> dict:
    """Measure apo pocket displacement after a *global* apo→holo alignment.

    Pocket residues are defined objectively from the holo prediction as any
    protein residue with a heavy atom within ``cutoff`` Å of a ligand heavy
    atom.  The pocket is not independently realigned: local rearrangement is
    therefore retained rather than fitted away.
    """
    holo_atoms = pdb_atom_records(holo_pdb, "A")
    apo_atoms = pdb_atom_records(apo_pdb, "A")
    ligand = np.array([r["xyz"] for r in pdb_atom_records(holo_pdb, "B", include_hetatm=True)])
    if not holo_atoms or not apo_atoms or ligand.size == 0:
        return {}

    pocket = {
        r["residue"] for r in holo_atoms
        if np.linalg.norm(ligand - r["xyz"], axis=1).min() <= cutoff
    }
    holo_by_key = {(r["residue"], r["atom"]): r["xyz"] for r in holo_atoms}
    apo_by_key = {(r["residue"], r["atom"]): r["xyz"] for r in apo_atoms}
    ca_keys = sorted(k for k in holo_by_key.keys() & apo_by_key.keys() if k[1] == "CA")
    if len(ca_keys) < 3 or not pocket:
        return {}
    apo_ca = np.array([apo_by_key[k] for k in ca_keys])
    holo_ca = np.array([holo_by_key[k] for k in ca_keys])
    global_rmsd, R, apo_mean, holo_mean = nise_lib._kabsch(apo_ca, holo_ca)

    pocket_ca_keys = [k for k in ca_keys if k[0] in pocket]
    bb_keys = sorted(
        k for k in holo_by_key.keys() & apo_by_key.keys()
        if k[0] in pocket and k[1] in BACKBONE_ATOMS
    )

    def aligned_rmsd(keys):
        if not keys:
            return None
        apo_xyz = np.array([apo_by_key[k] for k in keys])
        holo_xyz = np.array([holo_by_key[k] for k in keys])
        aligned = (R @ (apo_xyz - apo_mean).T).T + holo_mean
        return float(np.sqrt(((aligned - holo_xyz) ** 2).sum(1).mean()))

    return {
        "holo_vs_apo_global_ca_rmsd": global_rmsd,
        "holo_vs_apo_pocket_ca_rmsd": aligned_rmsd(pocket_ca_keys),
        "holo_vs_apo_pocket_backbone_rmsd": aligned_rmsd(bb_keys),
        "holo_pocket_cutoff_a": cutoff,
        "holo_pocket_residue_count": len(pocket_ca_keys),
        "holo_pocket_residues": ";".join(str(k[0][0]) + k[0][1] for k in pocket_ca_keys),
    }


def ligand_heavy_atoms(pdb_path: str, chain: str = "B") -> tuple[list[str], np.ndarray]:
    """Ordered (element, coords) for a chain's heavy atoms, in file order."""
    elements: list[str] = []
    coords: list[list[float]] = []
    for line in Path(pdb_path).read_text().splitlines():
        if not line.startswith(("ATOM", "HETATM")) or line[21] != chain:
            continue
        element = line[76:78].strip() or line[12:16].strip().lstrip("0123456789")[:1]
        if element == "H":
            continue
        elements.append(element)
        coords.append([float(line[30:38]), float(line[38:46]), float(line[46:54])])
    return elements, np.array(coords, dtype=float)


def backbone_ca_rmsd(nise_lib, pdb_a: str, pdb_b: str, chain: str = "A") -> float | None:
    ca_a = nise_lib.ca_coords_chain(pdb_a, chain)
    ca_b = nise_lib.ca_coords_chain(pdb_b, chain)
    if len(ca_a) != len(ca_b) or len(ca_a) < 3:
        return None
    rmsd, _, _, _ = nise_lib._kabsch(ca_a, ca_b)
    return rmsd


def design_vs_holo(nise_lib, holo_pdb: str, design_pdb: str) -> tuple[float | None, float | None]:
    ca_holo = nise_lib.ca_coords_chain(holo_pdb, "A")
    ca_design = nise_lib.ca_coords_chain(design_pdb, "A")
    if len(ca_holo) != len(ca_design) or len(ca_holo) < 3:
        return None, None
    ca_rmsd, R, mean_holo, mean_design = nise_lib._kabsch(ca_holo, ca_design)

    elems_holo, xyz_holo = ligand_heavy_atoms(holo_pdb, "B")
    elems_design, xyz_design = ligand_heavy_atoms(design_pdb, "B")
    if not elems_design or elems_holo != elems_design:
        return ca_rmsd, None
    holo_xyz_aligned = (R @ (xyz_holo - mean_holo).T).T + mean_design
    ligand_rmsd = float(np.sqrt(((holo_xyz_aligned - xyz_design) ** 2).sum(1).mean()))
    return ca_rmsd, ligand_rmsd


def default_root() -> Path:
    """Where venvs/ and src/ live.

    From the environment the app sets, else this checkout's parent -- rfd3 is
    installed inside the pipeline root. Never a hard-coded home directory:
    that is one developer's machine, not the user's.
    """
    env = os.environ.get("NANOHUNTER_ROOT") or os.environ.get("IPROTEIN_ROOT")
    if env:
        return Path(env)
    # Installed layout is <root>/rfd3/scripts/, so the root is two levels up.
    # Verify rather than assume: a standalone checkout has no venvs/ above it,
    # and silently pointing at a home directory would be worse than saying so.
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "venvs").is_dir():
        return candidate
    raise SystemExit(
        "Cannot locate the pipeline root (no venvs/ found). "
        "Set NANOHUNTER_ROOT, or pass --nanohunter-root explicitly.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--nanohunter-root", type=Path)
    args = parser.parse_args()

    pipeline_root = args.nanohunter_root or default_root()
    studio_runtime.configure(pipeline_root)
    nise_lib = studio_runtime

    campaign = args.campaign.resolve()
    holo_rows = {r["name"]: r for r in csv.DictReader((campaign / "predictions" / "holo" / "prediction_metrics.csv").open()) if r.get("ok") == "True"}
    apo_path = campaign / "predictions" / "apo" / "prediction_metrics.csv"
    apo_rows = {}
    if apo_path.exists():
        apo_rows = {r["name"]: r for r in csv.DictReader(apo_path.open()) if r.get("ok") == "True"}

    rows = []
    for name, holo in holo_rows.items():
        design_pdb = holo.get("backbone_pdb")
        if not design_pdb or not Path(design_pdb).exists():
            continue
        ca_rmsd, ligand_rmsd = design_vs_holo(nise_lib, holo["pdb"], design_pdb)
        row = {
            "name": name, "design": holo.get("design"), "seq_index": holo.get("seq_index"),
            "design_vs_holo_ca_rmsd": ca_rmsd, "design_vs_holo_ligand_rmsd": ligand_rmsd,
        }
        apo = apo_rows.get(name)
        if apo:
            row["design_vs_apo_ca_rmsd"] = backbone_ca_rmsd(nise_lib, apo["pdb"], design_pdb)
            row["holo_vs_apo_ca_rmsd"] = backbone_ca_rmsd(nise_lib, apo["pdb"], holo["pdb"])
            row.update(apo_holo_preorganisation(nise_lib, holo["pdb"], apo["pdb"]))
        rows.append(row)

    output = campaign / "analysis"
    output.mkdir(exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with (output / "rmsd_metrics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    scored_path = output / "scored_designs.csv"
    if scored_path.exists():
        scored = {r["name"]: r for r in csv.DictReader(scored_path.open())}
        merged = []
        for row in rows:
            merged.append({**scored.get(row["name"], {}), **row})
        merged_fields = sorted({key for row in merged for key in row})
        with (output / "design_metrics.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=merged_fields)
            writer.writeheader()
            writer.writerows(merged)

    n_ligand = sum(1 for r in rows if r.get("design_vs_holo_ligand_rmsd") is not None)
    n_apo = sum(1 for r in rows if "design_vs_apo_ca_rmsd" in r)
    print(f"computed RMSD for {len(rows)} designs ({n_ligand} with ligand RMSD, {n_apo} with apo comparisons) -> {output / 'rmsd_metrics.csv'}")


if __name__ == "__main__":
    main()
