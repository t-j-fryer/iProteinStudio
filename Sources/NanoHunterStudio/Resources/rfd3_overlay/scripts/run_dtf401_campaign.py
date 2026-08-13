#!/usr/bin/env python3
"""Orchestrate the dTF401 SMILES -> RFD3 -> LASErMPNN -> Boltz2 pipeline end to end.

Stages: ligand -> fixtures -> backbones -> mpnn -> predict-holo -> score ->
predict-apo -> rmsd. Every stage dispatches to its own script (below) and
each of those scripts is independently resumable (per-batch/per-chunk/
per-backbone checkpointing), so re-running this orchestrator after an
interruption -- or re-running a single --stage -- just picks up where it left
off; there is no separate lock file, matching the rest of the repo's
"check the expected artifact" idiom.

This does NOT self-daemonize. The `backbones`, `mpnn`, and `predict-holo`
stages are genuinely multi-hour on 1000 backbones / 4000 ligand-affinity
Boltz folds -- launch this script itself fully detached (double-fork +
caffeinate, NanoHunter/CLAUDE.md rule 1) rather than as a plain background
command, or it dies with the shell session.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGES = [
    "ligand", "fixtures", "backbones", "mpnn",
    "predict-holo", "score", "predict-apo", "rmsd",
]


def run(cmd: list, log_path: Path) -> None:
    print(f"$ {' '.join(str(c) for c in cmd)}")
    started = time.time()
    with log_path.open("w") as handle:
        result = subprocess.run(cmd, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
    wall = time.time() - started
    if result.returncode:
        raise SystemExit(f"stage failed (exit {result.returncode}, {wall:.1f}s); see {log_path}")
    print(f"  ok ({wall:.1f}s) -> {log_path}")


def stage_ligand(cfg: dict, campaign: Path, logs: Path) -> None:
    ligand_dir = campaign / "assets" / "ligand"
    manifest = ligand_dir / "atom_selections.json"
    if manifest.exists() and not cfg.get("force_ligand"):
        print(f"ligand: cached -> {manifest}")
        return
    run(
        [
            sys.executable, str(ROOT / "scripts" / "prepare_ligand_target.py"),
            "--spec", cfg["ligand_spec"], "--component-id", cfg["component_id"],
            "--output-dir", str(ligand_dir), "--design-name", cfg["design_name"],
            "--base-json", str(ROOT / "oracle" / f"input_{cfg['design_name']}_base.json"),
        ],
        logs / "ligand.log",
    )


def stage_fixtures(cfg: dict, campaign: Path, logs: Path) -> None:
    run(
        [
            sys.executable, str(ROOT / "scripts" / "build_length_bins.py"),
            "--base-json", str(ROOT / "oracle" / f"input_{cfg['design_name']}_base.json"),
            "--design-name", cfg["design_name"],
            "--ligand-manifest", str(campaign / "assets" / "ligand" / "atom_selections.json"),
            "--output", str(campaign),
            "--min-length", str(cfg["min_length"]), "--max-length", str(cfg["max_length"]),
            "--num-bins", str(cfg["num_bins"]), "--num-designs", str(cfg["num_designs"]),
            "--timesteps", str(cfg["timesteps"]), "--n-recycle", str(cfg["n_recycle"]),
        ],
        logs / "fixtures.log",
    )


def stage_backbones(cfg: dict, campaign: Path, logs: Path) -> None:
    run(
        [
            sys.executable, str(ROOT / "scripts" / "run_backbone_bins.py"),
            "--bin-manifest", str(campaign / "rfd3" / "bin_manifest.json"),
            "--output", str(campaign / "rfd3"),
            "--batch-size", str(cfg["batch_size"]), "--queues-per-bin", str(cfg["queues_per_bin"]),
            "--precision", cfg["precision"], "--steps", str(cfg["timesteps"]), "--recycle", str(cfg["n_recycle"]),
        ],
        logs / "backbones.log",
    )


def stage_mpnn(cfg: dict, campaign: Path, logs: Path) -> None:
    ligand_manifest = json.loads((campaign / "assets" / "ligand" / "atom_selections.json").read_text())
    run(
        [
            sys.executable, str(ROOT / "scripts" / "run_lasermpnn.py"),
            "--backbones", str(campaign / "rfd3" / "backbones"),
            "--output", str(campaign / "mpnn"),
            "--smiles", ligand_manifest["smiles"], "--n-seqs", str(cfg["n_seqs"]),
            "--max-parallel", str(cfg["mpnn_max_parallel"]),
        ],
        logs / "mpnn.log",
    )


def stage_predict(cfg: dict, campaign: Path, logs: Path, mode: str) -> None:
    ligand_manifest = json.loads((campaign / "assets" / "ligand" / "atom_selections.json").read_text())
    sequences = campaign / "mpnn" / "sequences.csv" if mode == "holo" else campaign / "analysis" / "top100.csv"
    yaml_dir = campaign / "predictor_inputs" / mode
    prep_cmd = [
        sys.executable, str(ROOT / "scripts" / "prepare_boltz_yaml.py"),
        "--sequences", str(sequences), "--output", str(yaml_dir), "--mode", mode,
    ]
    if mode == "holo":
        prep_cmd += ["--smiles", ligand_manifest["smiles"]]
    run(prep_cmd, logs / f"prepare_yaml_{mode}.log")

    predict_cmd = [
        sys.executable, str(ROOT / "scripts" / "run_boltz_affinity.py"),
        "--inputs", str(yaml_dir), "--output", str(campaign / "predictions" / mode),
        "--chunk-size", str(cfg["boltz_chunk_size"]), "--use-potentials",
    ]
    if mode == "holo":
        predict_cmd += ["--calibrate-n", str(cfg["boltz_calibrate_n"])]
    else:
        holo_manifest_path = campaign / "predictions" / "holo" / "run_manifest.json"
        parallel = json.loads(holo_manifest_path.read_text())["parallel"] if holo_manifest_path.exists() else 1
        predict_cmd += ["--parallel", str(parallel)]
    run(predict_cmd, logs / f"predict_{mode}.log")


def stage_score(cfg: dict, campaign: Path, logs: Path) -> None:
    run(
        [
            sys.executable, str(ROOT / "scripts" / "score_and_select.py"),
            "--predictions", str(campaign / "predictions" / "holo" / "prediction_metrics.csv"),
            "--output", str(campaign / "analysis"), "--top-n", str(cfg["top_n"]),
        ],
        logs / "score.log",
    )


def stage_rmsd(cfg: dict, campaign: Path, logs: Path) -> None:
    run(
        [sys.executable, str(ROOT / "scripts" / "compute_rmsd.py"), "--campaign", str(campaign)],
        logs / "rmsd.log",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--stage", choices=["all", *STAGES], default="all")
    args = parser.parse_args()

    cfg = json.loads(args.config.read_text())
    campaign = Path(cfg["campaign_dir"]).resolve()
    logs = campaign / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    dispatch = {
        "ligand": stage_ligand,
        "fixtures": stage_fixtures,
        "backbones": stage_backbones,
        "mpnn": stage_mpnn,
        "predict-holo": lambda c, camp, l: stage_predict(c, camp, l, "holo"),
        "score": stage_score,
        "predict-apo": lambda c, camp, l: stage_predict(c, camp, l, "apo"),
        "rmsd": stage_rmsd,
    }

    stages = STAGES if args.stage == "all" else [args.stage]
    campaign_start = time.time()
    for name in stages:
        print(f"=== stage: {name} ===")
        dispatch[name](cfg, campaign, logs)

    manifest_path = campaign / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"stages_completed": []}
    manifest["stages_completed"] = sorted(set(manifest["stages_completed"]) | set(stages))
    manifest["last_wall_sec"] = time.time() - campaign_start
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"done: {stages} in {manifest['last_wall_sec']:.1f}s")


if __name__ == "__main__":
    main()
