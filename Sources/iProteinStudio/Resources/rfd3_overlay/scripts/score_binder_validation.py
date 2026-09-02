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
        for predictor in predictors:
            h = holo.get((design, predictor))
            m = monomer.get((design, predictor))
            if h and backbone:
                complex_rmsds[predictor] = target_aligned_binder_rmsd(h["structure"], backbone)
                binder_backbone_rmsds[predictor] = rmsd(h["structure"], backbone)
            if m:
                binder_plddts[predictor] = number(
                    m, "plddt", "complex_plddt", "protein_plddt", "mean_plddt")
            if h and m:
                binder_rmsds[predictor] = rmsd(m["structure"], h["structure"])

        finite_complex = [v for v in complex_rmsds.values() if v is not None]
        finite_backbone = [v for v in binder_backbone_rmsds.values() if v is not None]
        finite_plddt = [v for v in binder_plddts.values() if v is not None]
        finite_binder = [v for v in binder_rmsds.values() if v is not None]
        aggregate = {
            "maximum_complex_rmsd": max(finite_complex) if finite_complex else None,
            "maximum_binder_backbone_rmsd": max(finite_backbone) if finite_backbone else None,
            "minimum_binder_plddt": min(finite_plddt) if finite_plddt else None,
            "maximum_binder_rmsd": max(finite_binder) if finite_binder else None,
        }
        failed = []
        gates = [
            ("minimum_iptm", number(row, "min_iptm"), lambda x, t: x >= t),
            ("minimum_ipsae_min", number(row, "min_ipsae_min"), lambda x, t: x >= t),
            ("maximum_complex_rmsd", aggregate["maximum_complex_rmsd"], lambda x, t: x <= t),
            ("minimum_binder_plddt", aggregate["minimum_binder_plddt"], lambda x, t: x >= t),
            ("maximum_binder_rmsd", aggregate["maximum_binder_rmsd"], lambda x, t: x <= t),
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
        "rmsd_definition": "complex RMSD is binder pose after fixed-target alignment; binder-backbone RMSD fits the binder itself",
    }
    (output / "hit_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"validated {len(merged)} designs; {summary['hits']} hit(s) -> {output}")


if __name__ == "__main__":
    main()
