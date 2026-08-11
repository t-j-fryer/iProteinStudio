#!/usr/bin/env python3
"""Protein-target RFdiffusion3 campaign: backbones and sequences.

The validated production pipeline in the RFD3 repo
(``scripts/run_rfd3_nise_campaign.py``) is small-molecule specific: it uses
LASErMPNN with NISE settings and drives Boltz's affinity head, and both of those
need a ligand SMILES. Protein targets therefore get this shorter path, which
reuses the same ``design_from_yaml.py`` front end -- and so inherits the atom
preflight and, importantly, the binder-length versus Foundry-total-length
accounting -- then inverse-folds with SolubleMPNN.

**Verification is deliberately not attempted here.** Re-folding a protein
complex needs a NanoHunter template and a cached target MSA, which this script
has no way to construct from an RFD3 spec alone. Backbones and sequences are
written where the design tab can pick them up. Pretending to verify would be
worse than stopping.

Progress markers match the campaign runner: RFSTAGE / RFINFO / RFDONE / RFFAIL.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

STAGES = ("fixtures", "backbones", "mpnn")
STAGE_PCT = {"fixtures": 10, "backbones": 30, "mpnn": 80}


def stage(name: str, message: str) -> None:
    print(f"RFSTAGE|{name}|{STAGE_PCT.get(name, 0)}|{message}", flush=True)


def info(message: str) -> None:
    print(f"RFINFO|{message}", flush=True)


def die(message: str) -> None:
    print(f"RFFAIL|{message}", flush=True)
    sys.exit(1)


def run(cmd: list, log_path: Path, cwd: Path, env: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    info("$ " + " ".join(map(str, cmd)))
    started = time.time()
    with log_path.open("w") as handle:
        result = subprocess.run(cmd, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT)
    if result.returncode:
        tail = "\n".join(log_path.read_text(errors="replace").splitlines()[-12:])
        die(f"Stage failed (exit {result.returncode}). Log: {log_path}\n{tail}")
    info(f"ok ({time.time() - started:.0f}s) -> {log_path}")


def design_cmd(cfg: dict, rfd3_root: Path, campaign: Path, stage_name: str) -> list:
    return [sys.executable, str(rfd3_root / "scripts" / "design_from_yaml.py"),
            cfg["design_yaml"],
            "--name", cfg["design_name"],
            "--output", str(campaign),
            "--num-designs", str(cfg["num_backbones"]),
            "--lengths", ",".join(map(str, cfg["lengths"])),
            "--batch-size", str(cfg["rfd3_batch_size"]),
            "--queues-per-bin", str(cfg["rfd3_queues_per_bin"]),
            "--precision", cfg["rfd3_precision"],
            "--timesteps", str(cfg["rfd3_timesteps"]),
            "--n-recycle", str(cfg["rfd3_recycles"]),
            "--seed-base", str(cfg["seed_base"]),
            "--stage", stage_name]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--stage", choices=("all", *STAGES), default="all")
    args = parser.parse_args()

    try:
        cfg = json.loads(args.config.resolve().read_text())
    except (OSError, json.JSONDecodeError) as exc:
        die(f"Could not read {args.config}: {exc}")

    rfd3_root = Path(cfg["rfd3_root"]).resolve() if cfg.get("rfd3_root") else None
    if rfd3_root is None or not (rfd3_root / "scripts" / "design_from_yaml.py").exists():
        die("RFdiffusion3 checkout not found, or it predates design_from_yaml.py.")
    campaign = Path(cfg["campaign_dir"]).resolve()
    logs = campaign / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env.update({"DEBUG": "false", "TOKENIZERS_PARALLELISM": "false"})

    selected = STAGES if args.stage == "all" else (args.stage,)
    started = time.time()
    completed: list[str] = []

    def record(current):
        (campaign / "campaign_progress.json").write_text(json.dumps({
            "completed_stages": completed, "current_stage": current,
            "updated_epoch": time.time(), "wall_sec": time.time() - started,
        }, indent=2) + "\n")

    for name in selected:
        record(name)
        if name == "fixtures":
            stage("fixtures", f"Building {len(cfg['lengths'])} length bins")
            run(design_cmd(cfg, rfd3_root, campaign, "fixtures"), logs / "fixtures.log", rfd3_root, env)
        elif name == "backbones":
            stage("backbones", f"Generating {cfg['num_backbones']} backbones "
                               f"(batch {cfg['rfd3_batch_size']} x {cfg['rfd3_queues_per_bin']} queues)")
            run(design_cmd(cfg, rfd3_root, campaign, "backbones"), logs / "backbones.log", rfd3_root, env)
            # Quota check: an underfilled bin must not be reported as success.
            produced = len(list((campaign / "rfd3" / "backbones").glob("design_*.pdb")))
            if produced != cfg["num_backbones"]:
                die(f"Expected {cfg['num_backbones']} backbones, found {produced}.")
            info(f"{produced} backbones")
        elif name == "mpnn":
            stage("mpnn", "Designing sequences with SolubleMPNN")
            run([sys.executable, str(rfd3_root / "scripts" / "run_mpnn.py"),
                 "--backbones", str(campaign / "rfd3" / "backbones"),
                 "--output", str(campaign / "mpnn"),
                 "--model-type", "soluble_mpnn",
                 "--nanohunter-root", cfg["nanohunter_root"],
                 "--seed", str(cfg["seed_base"] + 31000)],
                logs / "mpnn.log", rfd3_root, env)
            sequences = campaign / "mpnn" / "sequences.csv"
            rows = sum(1 for _ in csv.DictReader(sequences.open())) if sequences.exists() else 0
            if rows < cfg["num_backbones"]:
                die(f"Expected at least {cfg['num_backbones']} sequences, found {rows}.")
            info(f"{rows} sequences -> {sequences}")
        completed.append(name)
        record(None)

    info("Protein-target campaigns stop after sequence design: re-folding a complex "
         "needs a NanoHunter template and a cached target MSA. Take the sequences in "
         f"{campaign / 'mpnn' / 'sequences.csv'} to the design tab to verify them.")
    print(f"RFSTAGE|done|100|Finished in {(time.time() - started) / 60:.1f} min", flush=True)
    print("RFDONE|ok", flush=True)


if __name__ == "__main__":
    main()
