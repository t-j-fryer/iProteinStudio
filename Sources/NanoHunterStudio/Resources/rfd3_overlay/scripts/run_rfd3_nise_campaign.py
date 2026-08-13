#!/usr/bin/env python3
"""Resumable RFD3 → LASErMPNN → Boltz-2 affinity/apo campaign.

This is the production orchestrator for fixed, prevalidated ligand design
YAMLs.  It generates length-binned RFD3 backbones, four NISE-configured
LASErMPNN sequences per backbone, holo Boltz-2 predictions with steering
potentials and the affinity head, ranks by ligand-pLDDT/100 + P(bind), then
folds the top designs apo and measures pocket preorganisation.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("validate", "fixtures", "backbones", "mpnn", "predict-holo", "score", "predict-apo", "rmsd")


def run(cmd: list[str], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print("$ " + " ".join(map(str, cmd)), flush=True)
    started = time.time()
    with log_path.open("w") as handle:
        result = subprocess.run(cmd, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
    if result.returncode:
        raise SystemExit(f"stage command failed (exit {result.returncode}); see {log_path}")
    print(f"  ok ({time.time() - started:.1f}s) -> {log_path}", flush=True)


def read_smiles(path: Path) -> str:
    text = path.read_text().strip().splitlines()[0].strip()
    smiles = text.split()[0] if text else ""
    if not smiles:
        raise SystemExit(f"No SMILES in {path}")
    return smiles


def count_csv(path: Path) -> int:
    return sum(1 for _ in csv.DictReader(path.open())) if path.exists() else 0


def design_cmd(cfg: dict, stage: str, campaign: Path) -> list[str]:
    cmd = [
        sys.executable, str(ROOT / "scripts" / "design_from_yaml.py"), cfg["design_yaml"],
        "--name", cfg["design_name"], "--output", str(campaign),
        "--num-designs", str(cfg["num_backbones"]),
        "--lengths", ",".join(map(str, cfg["lengths"])),
        "--batch-size", str(cfg["rfd3_batch_size"]),
        "--queues-per-bin", str(cfg["rfd3_queues_per_bin"]),
        "--precision", cfg["rfd3_precision"],
        "--timesteps", str(cfg["rfd3_timesteps"]),
        "--n-recycle", str(cfg["rfd3_recycles"]),
        "--seed-base", str(cfg["seed_base"]), "--stage", stage,
    ]
    if cfg.get("ccd_mirror"):
        cmd += ["--ccd-mirror", cfg["ccd_mirror"]]
    # Optional: design across several ligand geometries rather than one, with the
    # quota split by weight. Absent, behaviour is exactly as before.
    conformers = cfg.get("conformers") or []
    if conformers:
        cmd += ["--conformers", ",".join(
            f"{c['path']}:{c.get('weight', 1.0)}:{c.get('label', '')}" for c in conformers)]
    return cmd


def stage_validate(cfg: dict, campaign: Path, logs: Path) -> None:
    validator = Path(cfg["bundle_validator"]) if cfg.get("bundle_validator") else Path(cfg["design_yaml"]).resolve().parent / "validate_bundle.py"
    if validator.exists():
        run([sys.executable, str(validator)], logs / "validate_bundle.log")
    if cfg.get("ligand_sdf") and cfg.get("atom_map") and cfg.get("ccd_mirror"):
        run([
            sys.executable, str(ROOT / "scripts" / "prepare_ccd_from_sdf.py"),
            "--sdf", cfg["ligand_sdf"], "--atom-map", cfg["atom_map"],
            "--component-id", cfg["component_id"], "--output", cfg["ccd_mirror"],
        ], logs / "prepare_ccd.log")
    run(design_cmd(cfg, "check", campaign), logs / "validate_design.log")


def stage_fixtures(cfg: dict, campaign: Path, logs: Path) -> None:
    run(design_cmd(cfg, "fixtures", campaign), logs / "fixtures.log")


def stage_backbones(cfg: dict, campaign: Path, logs: Path) -> None:
    run(design_cmd(cfg, "backbones", campaign), logs / "backbones.log")
    n = len(list((campaign / "rfd3" / "backbones").glob("design_*.pdb")))
    if n != cfg["num_backbones"]:
        raise SystemExit(f"Expected {cfg['num_backbones']} flattened backbones, found {n}")


def stage_mpnn(cfg: dict, campaign: Path, logs: Path) -> None:
    # ``sequence_model`` is optional and defaults to lasermpnn, so a config
    # written before this option existed behaves exactly as it did before.
    model = cfg.get("sequence_model", "lasermpnn")
    if model == "lasermpnn":
        cmd = [
            sys.executable, str(ROOT / "scripts" / "run_lasermpnn.py"),
            "--backbones", str(campaign / "rfd3" / "backbones"),
            "--output", str(campaign / "mpnn"), "--smiles", read_smiles(Path(cfg["smiles_file"])),
            "--n-seqs", str(cfg["sequences_per_backbone"]),
            "--max-parallel", str(cfg["mpnn_max_parallel"]),
        ]
        if "sequence_temperature" in cfg:
            cmd += ["--seq-temp", str(cfg["sequence_temperature"])]
        if "first_shell_temperature" in cfg:
            cmd += ["--fs-temp", str(cfg["first_shell_temperature"])]
    else:
        # LigandMPNN / SolubleMPNN / ProteinMPNN all go through run_mpnn.py,
        # which loads the model once for the whole backbone set.
        cmd = [
            sys.executable, str(ROOT / "scripts" / "run_mpnn.py"),
            "--backbones", str(campaign / "rfd3" / "backbones"),
            "--output", str(campaign / "mpnn"),
            "--model-type", "ligand_mpnn" if model == "ligandmpnn" else "soluble_mpnn",
            "--temperature", str(cfg.get("sequence_temperature", 0.1)),
        ]
        if cfg.get("nanohunter_root"):
            cmd += ["--nanohunter-root", cfg["nanohunter_root"]]
    run(cmd, logs / "mpnn.log")
    # run_mpnn.py emits one sequence per backbone; run_lasermpnn.py emits N.
    per_backbone = cfg["sequences_per_backbone"] if model == "lasermpnn" else 1
    expected = cfg["num_backbones"] * per_backbone
    observed = count_csv(campaign / "mpnn" / "sequences.csv")
    if observed != expected:
        raise SystemExit(f"Expected {expected} sequence rows, found {observed}")


def prepare_and_predict(cfg: dict, campaign: Path, logs: Path, mode: str) -> None:
    sequences = campaign / "mpnn" / "sequences.csv" if mode == "holo" else campaign / "analysis" / "top100.csv"
    yaml_dir = campaign / "predictor_inputs" / mode
    prep = [
        sys.executable, str(ROOT / "scripts" / "prepare_boltz_yaml.py"),
        "--sequences", str(sequences), "--output", str(yaml_dir), "--mode", mode,
    ]
    if mode == "holo":
        prep += ["--smiles", read_smiles(Path(cfg["smiles_file"]))]
    run(prep, logs / f"prepare_{mode}_yaml.log")

    predict = [
        sys.executable, str(ROOT / "scripts" / "run_boltz_affinity.py"),
        "--inputs", str(yaml_dir), "--output", str(campaign / "predictions" / mode),
        "--chunk-size", str(cfg["boltz_chunk_size"]),
    ]
    # Steering potentials roughly double Boltz's time; both directions are passed
    # explicitly so the recorded command says which was used.
    predict += ["--use-potentials"] if cfg.get("use_potentials", True) else ["--no-use-potentials"]
    if mode == "holo":
        predict += ["--calibrate-n", str(cfg["boltz_calibrate_n"])]
    else:
        holo = json.loads((campaign / "predictions" / "holo" / "run_manifest.json").read_text())
        predict += ["--parallel", str(holo["parallel"])]
    run(predict, logs / f"predict_{mode}.log")

    per_backbone = cfg["sequences_per_backbone"] if cfg.get("sequence_model", "lasermpnn") == "lasermpnn" else 1
    expected = cfg["num_backbones"] * per_backbone if mode == "holo" else cfg["top_n"]
    observed = count_csv(campaign / "predictions" / mode / "prediction_metrics.csv")
    if observed != expected:
        raise SystemExit(f"Expected {expected} {mode} predictions, found {observed}")

    # Optional independent second opinions, run over the same inputs. Agreement
    # between unrelated models is far stronger evidence than one high score.
    extra = [p for p in cfg.get("extra_predictors", []) if p in {"intellifold"}]
    if extra and mode == "holo":
        run([
            sys.executable, str(ROOT / "scripts" / "run_predictors.py"),
            "--inputs", str(yaml_dir),
            "--output", str(campaign / "predictions" / f"{mode}_second_opinion"),
            "--predictors", ",".join(extra),
            "--max-parallel", str(cfg.get("predict_max_parallel", 4)),
            "--nanohunter-root", cfg.get("nanohunter_root", "/Users/thomasfryer/NanoHunter"),
            "--resume",
        ], logs / f"predict_{mode}_second_opinion.log")


def stage_score(cfg: dict, campaign: Path, logs: Path) -> None:
    run([
        sys.executable, str(ROOT / "scripts" / "score_and_select.py"),
        "--predictions", str(campaign / "predictions" / "holo" / "prediction_metrics.csv"),
        "--output", str(campaign / "analysis"), "--top-n", str(cfg["top_n"]),
    ] + (["--require-pbind"] if cfg.get("run_affinity", True) else []) + [
        "--require-top-n",
    ], logs / "score.log")


def stage_rmsd(cfg: dict, campaign: Path, logs: Path) -> None:
    run([sys.executable, str(ROOT / "scripts" / "compute_rmsd.py"), "--campaign", str(campaign)], logs / "rmsd.log")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--stage", choices=("all", *STAGES), default="all")
    args = parser.parse_args()
    cfg = json.loads(args.config.resolve().read_text())
    for key in ("design_yaml", "smiles_file", "campaign_dir", "ligand_sdf", "atom_map", "ccd_mirror", "bundle_validator"):
        if key not in cfg:
            continue
        p = Path(cfg[key]).expanduser()
        if not p.is_absolute():
            p = ROOT / p
        cfg[key] = str(p.resolve())
    campaign = Path(cfg["campaign_dir"])
    if not campaign.is_absolute():
        campaign = (ROOT / campaign).resolve()
    campaign.mkdir(parents=True, exist_ok=True)
    logs = campaign / "logs"
    logs.mkdir(exist_ok=True)
    (campaign / "config").mkdir(exist_ok=True)
    (campaign / "config" / "resolved_campaign.json").write_text(json.dumps(cfg, indent=2) + "\n")
    shutil.copy2(cfg["design_yaml"], campaign / "config" / "design.yaml")
    shutil.copy2(cfg["smiles_file"], campaign / "config" / "ligand.smi")

    dispatch = {
        "validate": stage_validate, "fixtures": stage_fixtures, "backbones": stage_backbones,
        "mpnn": stage_mpnn,
        "predict-holo": lambda c, p, l: prepare_and_predict(c, p, l, "holo"),
        "score": stage_score,
        "predict-apo": lambda c, p, l: prepare_and_predict(c, p, l, "apo"),
        "rmsd": stage_rmsd,
    }
    stages = list(STAGES) if args.stage == "all" else [args.stage]
    if not cfg.get("run_apo", True):
        stages = [s for s in stages if s not in ("predict-apo", "rmsd")]
    start = time.time()
    completed = []
    for stage in stages:
        print(f"=== stage: {stage} ===", flush=True)
        (campaign / "campaign_progress.json").write_text(json.dumps({
            "completed_stages": completed, "current_stage": stage,
            "updated_epoch": time.time(), "wall_sec": time.time() - start,
        }, indent=2) + "\n")
        dispatch[stage](cfg, campaign, logs)
        completed.append(stage)
        (campaign / "campaign_progress.json").write_text(json.dumps({
            "completed_stages": completed, "current_stage": None,
            "updated_epoch": time.time(), "wall_sec": time.time() - start,
        }, indent=2) + "\n")
    print(f"complete: {', '.join(completed)} in {time.time() - start:.1f}s", flush=True)


if __name__ == "__main__":
    main()
