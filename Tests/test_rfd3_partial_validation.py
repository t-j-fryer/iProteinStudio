#!/usr/bin/env python3
"""Regression contracts for RFD3 modes and dual structural validation."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def atom(serial: int, chain: str, residue: int, xyz: tuple[float, float, float]) -> str:
    x, y, z = xyz
    return (f"ATOM  {serial:5d}  CA  ALA {chain}{residue:4d}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00           C")


def write_complex(path: Path, binder: np.ndarray, target: np.ndarray) -> None:
    lines = []
    serial = 1
    for chain, coordinates in (("A", binder), ("B", target)):
        for residue, xyz in enumerate(coordinates, 1):
            lines.append(atom(serial, chain, residue, tuple(xyz)))
            serial += 1
    path.write_text("\n".join(lines) + "\nEND\n")


def main() -> None:
    prepare = load(
        "rfd3_prepare_contract",
        ROOT / "Sources/iProteinStudio/Resources/rfd3/prepare_campaign.py",
    )
    score = load(
        "post_pair_contract",
        ROOT / "Sources/iProteinStudio/Resources/pipeline/scripts/score_post_prediction_pair.py",
    )

    with tempfile.TemporaryDirectory(prefix="iproteinstudio-rfd3-modes-") as raw:
        work = Path(raw)
        common = {
            "target_kind": "protein",
            "design_name": "contract",
            "target_structure": str(work / "complex.pdb"),
            "target_chains": ["B"],
            "normalized_chain_ranges": {"B": "B1-3"},
            "redesign_motif_sidechains": False,
            "is_non_loopy": True,
            "infer_ori_strategy": "hotspots",
            "ori_token": [100.0, 100.0, 100.0],
            "conditions": {},
        }
        partial = {
            **common,
            "design_mode": "partialDiffusion",
            "partial_t": 0.5,
        }
        partial_yaml = prepare.write_design_yaml(partial, work / "partial", None, None).read_text()
        assert "partial_t: 0.5" in partial_yaml
        assert '\"B1-3\": \"ALL\"' in partial_yaml
        assert "infer_ori_strategy" not in partial_yaml and "ori_token" not in partial_yaml, (
            "partial diffusion inherited a de-novo origin override"
        )

        motif = {
            **common,
            "design_mode": "motifScaffolding",
            "lengths": [70, 80],
            "motif_sites": {"A2": "CB,CA"},
        }
        motif_yaml = prepare.write_design_yaml(motif, work / "motif", None, None).read_text()
        assert '\"unindex\": \"A2\"' not in motif_yaml  # keys, unlike values, are not quoted
        assert 'unindex: \"A2\"' in motif_yaml and '\"A2\": \"CB,CA\"' in motif_yaml
        assert '\"70-80,/0,B1-3\"' in motif_yaml

        target = np.asarray([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [0.0, 3.0, 0.0]])
        binder = np.asarray([[5.0, 0.0, 0.0], [5.0, 2.0, 0.0], [6.0, 1.0, 1.0]])
        design = work / "design.pdb"
        rigid = work / "rigid.pdb"
        wrong_pose = work / "wrong_pose.pdb"
        write_complex(design, binder, target)

        rotation = np.asarray([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        translation = np.asarray([11.0, -4.0, 2.0])
        write_complex(rigid, (rotation @ binder.T).T + translation,
                      (rotation @ target.T).T + translation)
        write_complex(wrong_pose, binder + np.asarray([12.0, 0.0, 0.0]), target)

        assert score.target_aligned_binder_rmsd(rigid, design) < 1e-6
        assert score.kabsch_rmsd(wrong_pose, design) < 1e-6, (
            "binder-fit fold RMSD should ignore rigid interface displacement"
        )
        assert score.target_aligned_binder_rmsd(wrong_pose, design) > 10.0, (
            "target-aligned pose RMSD failed to detect the wrong interface placement"
        )

    print("RFdiffusion3 mode and dual-RMSD contracts: PASS")


if __name__ == "__main__":
    main()
