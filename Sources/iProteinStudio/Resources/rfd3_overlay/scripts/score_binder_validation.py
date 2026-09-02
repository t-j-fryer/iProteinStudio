#!/usr/bin/env python3
"""Merge complex and binder-alone predictions, then apply saved hit filters.

Every aggregate is conservative across the selected engines: minimum confidence
scores and maximum RMSDs. Per-engine values remain in the table so a hit is
auditable rather than an unexplained boolean.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import numpy as np
from biotite.structure.io.pdb import PDBFile
from biotite.structure.io.pdbx import CIFFile, get_structure as get_cif_structure


def load_array(path: str):
    source = Path(path)
    if source.suffix.lower() in {".cif", ".mmcif", ".bcif"}:
        return get_cif_structure(CIFFile.read(source), model=1)
    return PDBFile.read(source).get_structure(model=1)


def ca_coords(path: str, chain: str = "A") -> np.ndarray:
    array = load_array(path)
    mask = (array.chain_id == chain) & (array.atom_name == "CA")
    return np.asarray(array.coord[mask], dtype=float)


def target_ca_map(path: str) -> dict[tuple[str, int, str], np.ndarray]:
    """Return fixed-target C-alpha coordinates keyed by chain and residue."""
    array = load_array(path)
    mask = (array.chain_id != "A") & (array.atom_name == "CA")
    result = {}
    for atom in array[mask]:
        key = (str(atom.chain_id), int(atom.res_id), str(atom.ins_code or ""))
        result[key] = np.asarray(atom.coord, dtype=float)
    return result


def kabsch_transform(moving: np.ndarray, reference: np.ndarray):
    """Return the rigid transform mapping ``moving`` onto ``reference``."""
    moving_mean, reference_mean = moving.mean(0), reference.mean(0)
    mc, rc = moving - moving_mean, reference - reference_mean
    u, _, vt = np.linalg.svd(mc.T @ rc)
    correction = np.diag([1.0, 1.0, np.sign(np.linalg.det(vt.T @ u.T))])
    rotation = vt.T @ correction @ u.T
    translation = reference_mean - rotation @ moving_mean
    return rotation, translation


def rmsd(path_a: str, path_b: str, chain: str = "A") -> float | None:
    a, b = ca_coords(path_a, chain), ca_coords(path_b, chain)
    if a.shape != b.shape or len(a) < 3:
        return None
    rotation, translation = kabsch_transform(a, b)
    aligned = (rotation @ a.T).T + translation
    return float(np.sqrt(((aligned - b) ** 2).sum(1).mean()))


def target_aligned_binder_rmsd(prediction: str, design: str) -> float | None:
    """Measure interface-pose recovery after aligning the fixed target.

    This is deliberately distinct from fitting chain A onto itself. The latter
    measures binder fold consistency but cannot detect a correct fold placed on
    the wrong target surface.
    """
    predicted_target, design_target = target_ca_map(prediction), target_ca_map(design)
    common = sorted(set(predicted_target) & set(design_target))
    predicted_binder, design_binder = ca_coords(prediction), ca_coords(design)
    if len(common) < 3 or predicted_binder.shape != design_binder.shape or len(design_binder) < 3:
        return None
    moving = np.asarray([predicted_target[key] for key in common])
    reference = np.asarray([design_target[key] for key in common])
    rotation, translation = kabsch_transform(moving, reference)
    aligned_binder = (rotation @ predicted_binder.T).T + translation
    return float(np.sqrt(((aligned_binder - design_binder) ** 2).sum(1).mean()))


def json_dict(value) -> dict:
    """Decode a JSON dictionary carried through the campaign CSV."""
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def residue_selector(value: str) -> tuple[str, int, str] | None:
    # Studio's normalized RFD3 structures deliberately use one-character PDB
    # chain IDs (binder A, targets B onward). Keeping the chain group narrow
    # prevents a selector such as A22 being greedily parsed as chain A2/residue 2.
    match = re.fullmatch(r"([A-Za-z0-9])(-?\d+)([A-Za-z]?)", str(value).strip())
    if not match:
        return None
    return match.group(1), int(match.group(2)), match.group(3)


def selected_atom_map(path: str, residue: str, atom_names: list[str]) -> dict[str, np.ndarray]:
    """Return requested atoms for a chain/residue selector such as ``A19``."""
    selector = residue_selector(residue)
    if selector is None:
        return {}
    chain, res_id, ins_code = selector
    array = load_array(path)
    wanted = {str(name).strip().upper() for name in atom_names if str(name).strip()}
    result = {}
    for atom in array:
        atom_ins = str(atom.ins_code or "")
        if (str(atom.chain_id) == chain and int(atom.res_id) == res_id
                and atom_ins == ins_code and str(atom.atom_name).upper() in wanted):
            result[str(atom.atom_name).upper()] = np.asarray(atom.coord, dtype=float)
    return result


def motif_recovery_rmsd(prediction: str, design: str, row: dict):
    """Fit and score the exact constrained motif atoms in an independent fold.

    ``diffused_index_map`` records where each source motif residue landed in the
    generated chain.  The fit uses only the explicitly constrained atoms, so it
    remains valid when unindexing shifts the motif along the designed sequence.
    Per-residue values use the same global motif fit and are therefore directly
    interpretable rather than independently over-fitted.
    """
    mapping = json_dict(row.get("diffused_index_map"))
    fixed_atoms = json_dict(row.get("motif_fixed_atoms"))
    if not mapping:
        return None, {}

    moving, reference, owners = [], [], []
    for source_residue, generated_residue in sorted(mapping.items()):
        names = fixed_atoms.get(source_residue, [])
        if isinstance(names, str):
            names = [name for name in re.split(r"[\s,]+", names) if name]
        requested = {str(name).strip().upper() for name in names if str(name).strip()}
        if not requested:
            return None, {}
        predicted = selected_atom_map(prediction, str(generated_residue), sorted(requested))
        designed = selected_atom_map(design, str(generated_residue), sorted(requested))
        # A partial intersection would make a damaged motif look artificially
        # good. Every requested atom must exist in both structures or the saved
        # motif-recovery metric is unavailable and its configured gate fails.
        if set(predicted) != requested or set(designed) != requested:
            return None, {}
        for atom_name in sorted(requested):
            moving.append(predicted[atom_name])
            reference.append(designed[atom_name])
            owners.append(str(source_residue))
    if len(moving) < 3:
        return None, {}

    moving_array, reference_array = np.asarray(moving), np.asarray(reference)
    rotation, translation = kabsch_transform(moving_array, reference_array)
    aligned = (rotation @ moving_array.T).T + translation
    squared = ((aligned - reference_array) ** 2).sum(1)
    per_residue = {}
    for owner in sorted(set(owners)):
        values = [value for value, residue in zip(squared, owners) if residue == owner]
        per_residue[owner] = float(np.sqrt(np.mean(values)))
    return float(np.sqrt(np.mean(squared))), per_residue


def number(row: dict, *keys: str) -> float | None:
    for key in keys:
        try:
            raw = row.get(key, "")
            if raw not in ("", None, "None", "nan"):
                value = float(raw)
                if np.isfinite(value):
                    return value / 100.0 if key == "plddt" and value > 1.5 else value
        except (TypeError, ValueError):
            pass
    return None


def read_rows(path: Path) -> list[dict]:
    return list(csv.DictReader(path.open())) if path.exists() else []


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--filters", type=Path, required=True)
    args = parser.parse_args()
    campaign = args.campaign.resolve()
    output = campaign / "analysis"
    # Binder-alone prediction is intentionally limited to the selected top-N.
    # Validate that exact cohort: reading the all-design table here would mark
    # every unselected design as missing a monomer fold and then overwrite the
    # top-N result table with a larger, misleading set.
    selected_path = output / "top100.csv"
    scored = read_rows(selected_path)
    if not scored:
        raise SystemExit(f"No selected protein designs at {selected_path}")
    holo_rows = read_rows(campaign / "predictions" / "holo" / "prediction_metrics.csv")
    monomer_rows = read_rows(campaign / "predictions" / "monomer" / "prediction_metrics.csv")
    filters = json.loads(args.filters.read_text())
    holo = {(r.get("design"), r.get("predictor")): r for r in holo_rows
            if str(r.get("exit_code")) == "0" and r.get("structure")}
    monomer = {(r.get("design"), r.get("predictor")): r for r in monomer_rows
               if str(r.get("exit_code")) == "0" and r.get("structure")}

    merged = []
    for row in scored:
        design = row["design"]
        backbone = row.get("backbone_pdb", "")
        predictors = [p for p in row.get("predictors", "").split(",") if p]
        complex_rmsds, binder_backbone_rmsds, binder_plddts, binder_rmsds = {}, {}, {}, {}
        motif_rmsds, motif_residue_rmsds = {}, {}
        for predictor in predictors:
            h = holo.get((design, predictor))
            m = monomer.get((design, predictor))
            if h and backbone:
                complex_rmsds[predictor] = target_aligned_binder_rmsd(h["structure"], backbone)
                binder_backbone_rmsds[predictor] = rmsd(h["structure"], backbone)
                motif_value, residue_values = motif_recovery_rmsd(h["structure"], backbone, row)
                motif_rmsds[predictor] = motif_value
                motif_residue_rmsds[predictor] = residue_values
            if m:
                binder_plddts[predictor] = number(
                    m, "plddt", "complex_plddt", "protein_plddt", "mean_plddt")
            if h and m:
                binder_rmsds[predictor] = rmsd(m["structure"], h["structure"])

        finite_complex = [v for v in complex_rmsds.values() if v is not None]
        finite_backbone = [v for v in binder_backbone_rmsds.values() if v is not None]
        finite_plddt = [v for v in binder_plddts.values() if v is not None]
        finite_binder = [v for v in binder_rmsds.values() if v is not None]
        finite_motif = [v for v in motif_rmsds.values() if v is not None]
        aggregate = {
            "maximum_complex_rmsd": max(finite_complex) if finite_complex else None,
            "maximum_binder_backbone_rmsd": max(finite_backbone) if finite_backbone else None,
            "minimum_binder_plddt": min(finite_plddt) if finite_plddt else None,
            "maximum_binder_rmsd": max(finite_binder) if finite_binder else None,
            "maximum_motif_rmsd": max(finite_motif) if finite_motif else None,
        }
        failed = []
        gates = [
            ("minimum_iptm", number(row, "min_iptm"), lambda x, t: x >= t),
            ("minimum_ipsae_min", number(row, "min_ipsae_min"), lambda x, t: x >= t),
            ("maximum_complex_rmsd", aggregate["maximum_complex_rmsd"], lambda x, t: x <= t),
            ("minimum_binder_plddt", aggregate["minimum_binder_plddt"], lambda x, t: x >= t),
            ("maximum_binder_rmsd", aggregate["maximum_binder_rmsd"], lambda x, t: x <= t),
            ("maximum_motif_rmsd", aggregate["maximum_motif_rmsd"], lambda x, t: x <= t),
        ]
        for key, value, predicate in gates:
            threshold = filters.get(key)
            if threshold is not None and (value is None or not predicate(value, float(threshold))):
                failed.append(key + ("_unavailable" if value is None else ""))
        merged.append({
            **row, **aggregate,
            "is_hit": not failed,
            "failed_filters": ";".join(failed),
            "complex_rmsd_by_predictor": json.dumps(complex_rmsds, sort_keys=True),
            "binder_backbone_rmsd_by_predictor": json.dumps(binder_backbone_rmsds, sort_keys=True),
            "binder_plddt_by_predictor": json.dumps(binder_plddts, sort_keys=True),
            "binder_rmsd_by_predictor": json.dumps(binder_rmsds, sort_keys=True),
            "motif_rmsd_by_predictor": json.dumps(motif_rmsds, sort_keys=True),
            "motif_rmsd_by_residue": json.dumps(motif_residue_rmsds, sort_keys=True),
            "filter_provenance": str(args.filters.resolve()),
        })

    fields = sorted({key for row in merged for key in row})
    for filename in ("design_metrics.csv", "scored_designs.csv", "top100.csv"):
        with (output / filename).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader(); writer.writerows(merged)
    (output / "top100_manifest.json").write_text(json.dumps(merged, indent=2) + "\n")
    summary = {
        "designs_evaluated": len(merged),
        "hits": sum(str(row["is_hit"]).lower() == "true" for row in merged),
        "filters": filters,
        "aggregation": "minimum confidence and maximum RMSD across selected predictors",
        "rmsd_definition": "complex RMSD is binder pose after fixed-target alignment; binder-backbone RMSD fits the binder itself; motif RMSD aligns and scores the exact constrained motif atoms using the saved unindex map",
    }
    (output / "hit_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"validated {len(merged)} designs; {summary['hits']} hit(s) -> {output}")


if __name__ == "__main__":
    main()
