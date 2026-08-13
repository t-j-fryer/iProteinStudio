#!/usr/bin/env python3
"""Join RFD3, MPNN, predictor, self-consistency, and ligand-exposure metrics."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import biotite.structure as struc
import biotite.structure.io.pdbx as pdbx
import numpy as np


def read_csv(path: Path) -> list[dict]:
    return list(csv.DictReader(path.open()))


def pdb_atoms(path: Path, chain: str, atom_name: str | None = None):
    rows = []
    for line in path.read_text().splitlines():
        if not (line.startswith("ATOM") or line.startswith("HETATM")) or line[21:22] != chain:
            continue
        name = line[12:16].strip()
        if atom_name is not None and name != atom_name:
            continue
        rows.append((name, np.array([float(line[30:38]), float(line[38:46]), float(line[46:54])])))
    return rows


def read_cif(path: Path):
    return pdbx.get_structure(pdbx.CIFFile.read(path), model=1, extra_fields=["b_factor"])


def kabsch(source: np.ndarray, reference: np.ndarray):
    source_center = source.mean(0)
    reference_center = reference.mean(0)
    left, _, right = np.linalg.svd((source - source_center).T @ (reference - reference_center))
    rotation = left @ right
    if np.linalg.det(rotation) < 0:
        left[:, -1] *= -1
        rotation = left @ right
    return rotation, source_center, reference_center


def transform(x: np.ndarray, fit) -> np.ndarray:
    rotation, source_center, reference_center = fit
    return (x - source_center) @ rotation + reference_center


def rmsd(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(np.square(a - b).sum() / len(a)))


def aligned_rmsd(mobile: np.ndarray, reference: np.ndarray) -> float:
    return rmsd(transform(mobile, kabsch(mobile, reference)), reference)


def ligand_rasa(array, exposed: set[str], buried: set[str]) -> dict[str, float]:
    ligand_mask = array.hetero & np.isin(array.atom_name, sorted(exposed | buried))
    ligand = array[ligand_mask]
    if len(ligand) != len(exposed | buried):
        return {}
    complex_sasa = struc.sasa(array, vdw_radii="Single", point_number=400)
    ligand_sasa = struc.sasa(ligand, vdw_radii="Single", point_number=400)
    rel = complex_sasa[ligand_mask] / np.maximum(ligand_sasa, 1e-6)
    names = ligand.atom_name.tolist()
    exposed_values = np.array([rel[i] for i, name in enumerate(names) if name in exposed])
    buried_values = np.array([rel[i] for i, name in enumerate(names) if name in buried])
    return {
        "linker_rasa_mean": float(np.nanmean(exposed_values)),
        "core_rasa_mean": float(np.nanmean(buried_values)),
        "linker_minus_core_rasa": float(np.nanmean(exposed_values) - np.nanmean(buried_values)),
        "linker_atoms_rasa_ge_0p5": int(np.sum(exposed_values >= 0.5)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--ligand-manifest", type=Path)
    args = parser.parse_args()
    campaign = args.campaign.resolve()
    backbone_rows = {row["design"]: row for row in read_csv(campaign / "rfd3" / "backbone_metrics.csv")}
    sequence_rows = {row["design"]: row for row in read_csv(campaign / "mpnn" / "sequences.csv")}
    prediction_rows = read_csv(campaign / "predictions" / "prediction_metrics.csv")
    exposed: set[str] = set()
    buried: set[str] = set()
    if args.ligand_manifest:
        manifest = json.loads(args.ligand_manifest.read_text())
        exposed = set(manifest["exposed_atoms"])
        buried = set(manifest["buried_atoms"])

    rows: list[dict] = []
    for prediction in prediction_rows:
        design = prediction["design"]
        backbone = backbone_rows[design]
        sequence = sequence_rows[design]
        backbone_path = Path(backbone["backbone_pdb"])
        predicted_path = Path(prediction["structure"])
        array = read_cif(predicted_path)
        pred_binder = array[(array.chain_id == "A") & (array.atom_name == "CA")].coord
        ref_binder = np.array([xyz for _, xyz in pdb_atoms(backbone_path, "A", "CA")])
        if len(pred_binder) != len(ref_binder):
            raise SystemExit(f"Binder CA mismatch for {design}: {len(pred_binder)} != {len(ref_binder)}")
        self_rmsd = aligned_rmsd(pred_binder, ref_binder)

        target_aligned = float("nan")
        if exposed:
            ref_ligand = {name: xyz for name, xyz in pdb_atoms(backbone_path, "B") if name in exposed | buried}
            pred_ligand = {
                str(array.atom_name[i]): array.coord[i]
                for i in np.where(array.hetero & np.isin(array.atom_name, sorted(exposed | buried)))[0]
            }
            names = sorted(ref_ligand.keys() & pred_ligand.keys())
            if len(names) == len(exposed | buried):
                fit = kabsch(np.array([pred_ligand[n] for n in names]), np.array([ref_ligand[n] for n in names]))
                target_aligned = rmsd(transform(pred_binder, fit), ref_binder)
        else:
            ref_target = np.array([xyz for _, xyz in pdb_atoms(backbone_path, "B", "CA")])
            pred_target = array[(array.chain_id == "B") & (array.atom_name == "CA")].coord
            if len(ref_target) == len(pred_target):
                fit = kabsch(pred_target, ref_target)
                target_aligned = rmsd(transform(pred_binder, fit), ref_binder)

        row = {
            **backbone,
            **{f"mpnn_{key}": value for key, value in sequence.items() if key not in {"design", "backbone_pdb"}},
            **{f"predictor_{key}": value for key, value in prediction.items() if key != "design"},
            "design": design,
            "binder_ca_self_rmsd": self_rmsd,
            "target_aligned_binder_ca_rmsd": target_aligned,
        }
        if exposed:
            row.update(ligand_rasa(array, exposed, buried))
        rows.append(row)

    output = campaign / "analysis"
    output.mkdir(exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with (output / "design_metrics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    aggregate = {"num_rows": len(rows), "predictors": {}}
    for predictor in sorted({row["predictor_predictor"] for row in rows}):
        subset = [row for row in rows if row["predictor_predictor"] == predictor]
        keys = ["predictor_iptm", "binder_ca_self_rmsd", "target_aligned_binder_ca_rmsd"]
        if exposed:
            keys += ["linker_rasa_mean", "core_rasa_mean", "linker_minus_core_rasa"]
        aggregate["predictors"][predictor] = {
            key: float(np.nanmean([float(row[key]) for row in subset if row.get(key, "") != ""]))
            for key in keys
        }
    (output / "aggregate.json").write_text(json.dumps(aggregate, indent=2) + "\n")

    # Conservative cross-predictor ranking: prioritize the weaker iPTM, then
    # the mean iPTM. All component metrics remain visible in the CSV.
    by_design: dict[str, list[dict]] = {}
    for row in rows:
        by_design.setdefault(row["design"], []).append(row)
    rankings: list[dict] = []
    for design, design_rows in by_design.items():
        predictor_rows = {row["predictor_predictor"]: row for row in design_rows}
        iptms = [float(row["predictor_iptm"]) for row in design_rows]
        plddts = [
            float(row["predictor_plddt"] or row["predictor_complex_plddt"])
            for row in design_rows
        ]
        rank_row = {
            "design": design,
            "sequence": design_rows[0]["mpnn_sequence"],
            "consensus_min_iptm": min(iptms),
            "consensus_mean_iptm": float(np.mean(iptms)),
            "consensus_mean_plddt": float(np.mean(plddts)),
            "max_binder_ca_self_rmsd": max(
                float(row["binder_ca_self_rmsd"]) for row in design_rows
            ),
            "max_target_aligned_binder_ca_rmsd": max(
                float(row["target_aligned_binder_ca_rmsd"]) for row in design_rows
            ),
        }
        for predictor in sorted(predictor_rows):
            row = predictor_rows[predictor]
            rank_row[f"{predictor}_iptm"] = float(row["predictor_iptm"])
            rank_row[f"{predictor}_plddt"] = float(
                row["predictor_plddt"] or row["predictor_complex_plddt"]
            )
        if exposed:
            rank_row["mean_linker_minus_core_rasa"] = float(
                np.mean([float(row["linker_minus_core_rasa"]) for row in design_rows])
            )
        rankings.append(rank_row)
    rankings.sort(
        key=lambda row: (row["consensus_min_iptm"], row["consensus_mean_iptm"]),
        reverse=True,
    )
    for rank, row in enumerate(rankings, 1):
        row["consensus_rank"] = rank
    rank_fields = ["consensus_rank"] + sorted(
        {key for row in rankings for key in row if key != "consensus_rank"}
    )
    with (output / "consensus_ranking.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rank_fields)
        writer.writeheader()
        writer.writerows(rankings)
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
