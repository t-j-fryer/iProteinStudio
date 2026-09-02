#!/usr/bin/env python3
"""Functional contract for unindexed motif correspondence and atom scoring."""

from __future__ import annotations

import importlib.util
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCORER = ROOT / "Sources/iProteinStudio/Resources/rfd3_overlay/scripts/score_binder_validation.py"


def load_scorer():
    spec = importlib.util.spec_from_file_location("rfd3_motif_scorer", SCORER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def atom(serial: int, name: str, residue: int, xyz: np.ndarray) -> str:
    element = name.strip()[0]
    return (f"ATOM  {serial:5d} {name:>4s} PHE A{residue:4d}    "
            f"{xyz[0]:8.3f}{xyz[1]:8.3f}{xyz[2]:8.3f}  1.00 20.00          {element:>2s}")


def write_motif(path: Path, coordinates: dict[tuple[int, str], np.ndarray]) -> None:
    path.write_text("\n".join(
        atom(index, name, residue, xyz)
        for index, ((residue, name), xyz) in enumerate(coordinates.items(), 1)
    ) + "\nEND\n")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run_filter_gate(campaign: Path, design: Path, prediction: Path, row: dict) -> dict:
    scored = {
        "design": "candidate_1", "predictors": "boltz", "backbone_pdb": str(design),
        "min_iptm": "0.8", "min_ipsae_min": "0.7", **row,
    }
    write_csv(campaign / "analysis/top100.csv", [scored])
    write_csv(campaign / "predictions/holo/prediction_metrics.csv", [{
        "design": "candidate_1", "predictor": "boltz", "exit_code": "0",
        "structure": str(prediction),
    }])
    write_csv(campaign / "predictions/monomer/prediction_metrics.csv", [])
    filters = campaign / "filters.json"
    filters.write_text(json.dumps({"maximum_motif_rmsd": 0.1}) + "\n")
    subprocess.run(
        [sys.executable, str(SCORER), "--campaign", str(campaign), "--filters", str(filters)],
        check=True, capture_output=True, text=True,
    )
    return next(csv.DictReader((campaign / "analysis/top100.csv").open()))


def main() -> None:
    scorer = load_scorer()
    names = ["CG", "CE1", "CZ"]
    base = {
        (residue, name): np.asarray([residue * 1.7, offset * 1.2, (residue + offset) % 3], dtype=float)
        for residue, source in zip((8, 22, 51), (19, 23, 26))
        for offset, name in enumerate(names)
    }
    rotation = np.asarray([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    translation = np.asarray([12.0, -7.0, 3.0])
    rigid = {key: (rotation @ value) + translation for key, value in base.items()}
    distorted = dict(rigid)
    distorted[(22, "CZ")] = distorted[(22, "CZ")] + np.asarray([4.0, 0.0, 0.0])
    row = {
        "diffused_index_map": json.dumps({"A19": "A8", "A23": "A22", "A26": "A51"}),
        "motif_fixed_atoms": json.dumps({key: names for key in ("A19", "A23", "A26")}),
    }

    with tempfile.TemporaryDirectory(prefix="iproteinstudio-motif-score-") as raw:
        root = Path(raw)
        design, prediction, bad = root / "design.pdb", root / "prediction.pdb", root / "bad.pdb"
        write_motif(design, base)
        write_motif(prediction, rigid)
        write_motif(bad, distorted)

        value, per_residue = scorer.motif_recovery_rmsd(str(prediction), str(design), row)
        assert value is not None and value < 1e-3, value
        assert set(per_residue) == {"A19", "A23", "A26"}
        bad_value, bad_residues = scorer.motif_recovery_rmsd(str(bad), str(design), row)
        assert bad_value is not None and bad_value > 0.5, bad_value
        assert bad_residues["A23"] > per_residue["A23"]

        missing, details = scorer.motif_recovery_rmsd(
            str(prediction), str(design), {"diffused_index_map": row["diffused_index_map"]})
        assert missing is None and details == {}, "missing atom provenance must fail closed"

        partial_coordinates = dict(rigid)
        del partial_coordinates[(22, "CZ")]
        partial = root / "partial.pdb"
        write_motif(partial, partial_coordinates)
        missing, details = scorer.motif_recovery_rmsd(str(partial), str(design), row)
        assert missing is None and details == {}, "a missing requested atom must fail closed"

        valid_gate = run_filter_gate(root / "valid-gate", design, prediction, row)
        assert valid_gate["is_hit"].lower() == "true", valid_gate
        missing_gate = run_filter_gate(root / "missing-gate", design, partial, row)
        assert missing_gate["is_hit"].lower() == "false", missing_gate
        assert "maximum_motif_rmsd_unavailable" in missing_gate["failed_filters"], missing_gate

    print("RFdiffusion3 motif correspondence and recovery scoring: PASS")


if __name__ == "__main__":
    main()
