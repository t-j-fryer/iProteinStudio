#!/usr/bin/env python3
"""Score one independent complex refold and its optional binder-alone refold.

The output is a single RFC-4180 CSV row consumed directly by the iterative
campaign aggregator. Complex RMSD is chain-A pose recovery after fitting the
fixed target; binder-backbone and binder-alone RMSDs fit chain A directly.
Missing requested evidence fails its gate rather than being silently ignored.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_prediction_geometry import read_residues  # noqa: E402


def ca(path: Path, chain: str = "A") -> np.ndarray:
    residues = read_residues(path)
    coordinates = [atoms["CA"] for (model, chain_id, _), atoms in residues.items()
                   if model == "1" and chain_id == chain and "CA" in atoms]
    return np.asarray(coordinates, dtype=float)


def target_ca_map(path: Path) -> dict[tuple[str, str], np.ndarray]:
    residues = read_residues(path)
    return {
        (chain_id, residue_id): np.asarray(atoms["CA"], dtype=float)
        for (model, chain_id, residue_id), atoms in residues.items()
        if model == "1" and chain_id != "A" and "CA" in atoms
    }


def kabsch_transform(moving: np.ndarray, reference: np.ndarray):
    moving_mean, reference_mean = moving.mean(axis=0), reference.mean(axis=0)
    mc, rc = moving - moving_mean, reference - reference_mean
    u, _, vt = np.linalg.svd(mc.T @ rc)
    correction = np.diag([1.0, 1.0, np.sign(np.linalg.det(vt.T @ u.T))])
    rotation = vt.T @ correction @ u.T
    translation = reference_mean - rotation @ moving_mean
    return rotation, translation


def kabsch_rmsd(first: Path | None, second: Path | None) -> float | None:
    if first is None or second is None or not first.is_file() or not second.is_file():
        return None
    a, b = ca(first), ca(second)
    if a.shape != b.shape or len(a) < 3:
        return None
    rotation, translation = kabsch_transform(a, b)
    aligned = (rotation @ a.T).T + translation
    return float(np.sqrt(np.square(aligned - b).sum(axis=1).mean()))


def target_aligned_binder_rmsd(prediction: Path, design: Path) -> float | None:
    predicted_target, design_target = target_ca_map(prediction), target_ca_map(design)
    common = sorted(set(predicted_target) & set(design_target))
    predicted_binder, design_binder = ca(prediction), ca(design)
    if len(common) < 3 or predicted_binder.shape != design_binder.shape or len(design_binder) < 3:
        return None
    moving = np.asarray([predicted_target[key] for key in common])
    reference = np.asarray([design_target[key] for key in common])
    rotation, translation = kabsch_transform(moving, reference)
    aligned_binder = (rotation @ predicted_binder.T).T + translation
    return float(np.sqrt(np.square(aligned_binder - design_binder).sum(axis=1).mean()))


def confidence_number(path: Path | None, keys: tuple[str, ...]) -> float | None:
    if path is None or not path.is_file():
        return None
    try:
        root = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    def walk(value):
        if isinstance(value, dict):
            for key in keys:
                candidate = value.get(key)
                if isinstance(candidate, (int, float)) and math.isfinite(candidate):
                    return float(candidate)
            for child in value.values():
                found = walk(child)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = walk(child)
                if found is not None:
                    return found
        return None

    return walk(root)


def optional_path(raw: str) -> Path | None:
    return Path(raw).resolve() if raw else None


def finite(raw: str) -> float | None:
    try:
        value = float(raw)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--cycle", type=int, required=True)
    parser.add_argument("--predictor", required=True)
    parser.add_argument("--sequence", required=True)
    parser.add_argument("--design-structure", required=True)
    parser.add_argument("--complex-structure", required=True)
    parser.add_argument("--complex-confidence", default="")
    parser.add_argument("--complex-iptm", default="nan")
    parser.add_argument("--complex-plddt", default="nan")
    parser.add_argument("--binder-structure", default="")
    parser.add_argument("--binder-confidence", default="")
    parser.add_argument("--binder-plddt", default="nan")
    parser.add_argument("--min-iptm", type=float)
    parser.add_argument("--min-ipsae", type=float)
    parser.add_argument("--max-complex-rmsd", type=float)
    parser.add_argument("--min-binder-plddt", type=float)
    parser.add_argument("--max-binder-rmsd", type=float)
    args = parser.parse_args()

    design = Path(args.design_structure).resolve()
    complex_structure = Path(args.complex_structure).resolve()
    complex_confidence = optional_path(args.complex_confidence)
    binder_structure = optional_path(args.binder_structure)
    binder_confidence = optional_path(args.binder_confidence)
    iptm = finite(args.complex_iptm)
    complex_plddt = finite(args.complex_plddt)
    ipsae = confidence_number(complex_confidence, ("ipsae_min", "ipSAE_min", "ipsae(min)"))
    binder_plddt = finite(args.binder_plddt)
    if binder_plddt is None:
        binder_plddt = confidence_number(
            binder_confidence, ("complex_plddt", "protein_plddt", "mean_plddt", "plddt")
        )
    if binder_plddt is not None and binder_plddt > 1.5:
        binder_plddt /= 100.0
    complex_rmsd = target_aligned_binder_rmsd(complex_structure, design)
    binder_backbone_rmsd = kabsch_rmsd(complex_structure, design)
    binder_rmsd = kabsch_rmsd(binder_structure, complex_structure)

    gates = (
        ("minimum_iptm", iptm, args.min_iptm, lambda value, threshold: value >= threshold),
        ("minimum_ipsae_min", ipsae, args.min_ipsae, lambda value, threshold: value >= threshold),
        ("maximum_complex_rmsd", complex_rmsd, args.max_complex_rmsd, lambda value, threshold: value <= threshold),
        ("minimum_binder_plddt", binder_plddt, args.min_binder_plddt, lambda value, threshold: value >= threshold),
        ("maximum_binder_rmsd", binder_rmsd, args.max_binder_rmsd, lambda value, threshold: value <= threshold),
    )
    failed = []
    for name, value, threshold, predicate in gates:
        if threshold is not None and (value is None or not predicate(value, threshold)):
            failed.append(name + ("_unavailable" if value is None else ""))

    row = {
        "run": args.run,
        "cycle": args.cycle,
        "predictor": args.predictor,
        "iptm": iptm,
        "ipsae_min": ipsae,
        "complex_plddt": complex_plddt,
        "binder_plddt": binder_plddt,
        "complex_rmsd": complex_rmsd,
        "binder_backbone_rmsd": binder_backbone_rmsd,
        "binder_rmsd": binder_rmsd,
        "binder_sequence": args.sequence,
        "structure_path": str(complex_structure),
        "confidence_json": str(complex_confidence or ""),
        "binder_structure_path": str(binder_structure or ""),
        "binder_confidence_json": str(binder_confidence or ""),
        "is_hit": not failed,
        "failed_filters": ";".join(failed),
        "filter_provenance": ";".join((
            f"minimum_iptm={args.min_iptm}",
            f"minimum_ipsae_min={args.min_ipsae}",
            f"maximum_complex_rmsd={args.max_complex_rmsd}",
            f"minimum_binder_plddt={args.min_binder_plddt}",
            f"maximum_binder_rmsd={args.max_binder_rmsd}",
        )),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


if __name__ == "__main__":
    main()
