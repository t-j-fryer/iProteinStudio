#!/usr/bin/env python3
"""Protein-target RFdiffusion3 campaign: backbones and sequences.

The validated production pipeline in the RFD3 repo
(``scripts/run_rfd3_nise_campaign.py``) is small-molecule specific: it uses
LASErMPNN with NISE settings and drives Boltz's affinity head, and both of those
need a ligand SMILES. Protein targets therefore get this shorter path, which
reuses the same ``design_from_yaml.py`` front end -- and so inherits the atom
preflight and, importantly, the binder-length versus Foundry-total-length
accounting -- then inverse-folds with SolubleMPNN.

Verification is included. Re-folding a designed complex needs a target MSA, so
the ``msa`` stage generates one **once** through Boltz's MSA server and every
later prediction reuses it by path. That is the same rule NanoHunter follows:
the binder chain is explicitly ``empty`` (a de-novo sequence has no homologues,
and pretending otherwise is worse than useless), the target gets a real MSA, and
a silent fall back to single-sequence mode is treated as an error rather than a
degraded success.

Progress markers match the campaign runner: RFSTAGE / RFINFO / RFDONE / RFFAIL.
"""

from __future__ import annotations

import argparse
import atexit
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

STAGES = ("fixtures", "backbones", "mpnn", "msa", "predict", "score")
STAGE_PCT = {"fixtures": 5, "backbones": 20, "mpnn": 45, "msa": 55, "predict": 60, "score": 95}


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
            "--stage", stage_name] + conformer_args(cfg)


def conformer_args(cfg: dict) -> list:
    """Design across several ligand geometries, splitting the quota by weight."""
    conformers = cfg.get("conformers") or []
    if not conformers:
        return []
    spec = ",".join(f"{c['path']}:{c.get('weight', 1.0)}:{c.get('label', '')}" for c in conformers)
    return ["--conformers", spec]


def clean_sequence(text: str) -> str:
    return "".join(c for c in (text or "").upper() if c.isalpha())


def stage_msa(cfg: dict, campaign: Path, rfd3_root: Path, env: dict) -> Path:
    """Generate the target MSA once, and cache it for the whole campaign.

    Mirrors NanoHunter's own auto-MSA path: predict the bare target through
    Boltz with the MSA server enabled, then keep the A3M it produced. Doing this
    once and passing it by path is what makes a multi-thousand-fold campaign
    affordable.
    """
    cache = campaign / "assets" / "target_msa"
    a3m = cache / "target_full_msa.a3m"
    sequence = clean_sequence(cfg.get("target_sequence", ""))
    if not sequence:
        die("No target sequence was recorded, so the target MSA cannot be generated. "
            "Re-enter the target sequence in the RFdiffusion3 tab.")

    if a3m.exists() and validate_a3m(a3m, sequence):
        info(f"target MSA cached -> {a3m}")
        return a3m
    if a3m.exists():
        die(f"The cached target MSA query does not match the recorded target sequence: {a3m}")

    root = Path(cfg["nanohunter_root"])
    for search_root in (root / "msa_cache", root / "examples_data", root / "projects"):
        if not search_root.exists():
            continue
        for candidate in search_root.rglob("*.a3m"):
            if validate_a3m(candidate, sequence):
                cache.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate, a3m)
                info(f"reused exact target MSA -> {candidate}")
                return a3m

    cache.mkdir(parents=True, exist_ok=True)
    yaml_path = cache / "target.yaml"
    yaml_path.write_text(
        "sequences:\n"
        "  - protein:\n"
        f"      id: {cfg.get('target_chain', 'B')}\n"
        f"      sequence: {sequence}\n"
        "version: 1\n"
    )

    boltz = Path(cfg["nanohunter_root"]) / "venvs" / "NanoHunter_boltz" / "bin" / "boltz"
    if not boltz.exists():
        die(f"Boltz not found at {boltz}; the target MSA cannot be generated.")
    out_dir = cache / "boltz"
    run([str(boltz), "predict", str(yaml_path), "--out_dir", str(out_dir),
         "--use_msa_server", "--override"],
        campaign / "logs" / "msa.log", rfd3_root, env)

    raw = sorted(out_dir.rglob("msa/*.csv"))
    if not raw:
        die("Boltz produced no MSA. The MSA server may be unreachable — a run "
            "without a real target MSA would silently be much worse, so this stops here.")
    csv_to_a3m(raw[0], a3m, sequence)
    info(f"target MSA -> {a3m}")
    return a3m


def validate_a3m(path: Path, query: str) -> bool:
    """Require an exact first record and at least one real homologue."""
    try:
        records = []
        current = []
        for line in path.read_text(errors="replace").splitlines():
            if line.startswith(">"):
                if current:
                    records.append("".join(current))
                    current = []
            elif line.strip():
                current.append(line.strip())
        if current:
            records.append("".join(current))
        if len(records) < 2:
            return False
        first = "".join(c for c in records[0] if not c.islower() and c not in "-.").upper()
        return first == query
    except OSError:
        return False


def csv_to_a3m(csv_path: Path, a3m_path: Path, query: str) -> None:
    """Convert Boltz's raw MSA CSV to the A3M the predictors consume.

    The query row is forced to the exact target sequence: every consumer checks
    that the first record matches, and a mismatch there is the classic way a
    reused MSA silently corrupts a campaign.
    """
    rows = list(csv.DictReader(csv_path.open()))
    if not rows:
        die(f"No MSA records in {csv_path}")
    key = "sequence" if "sequence" in rows[0] else list(rows[0])[0]
    lines = [">query", query]
    for i, row in enumerate(rows):
        seq = (row.get(key) or "").strip()
        if not seq:
            continue
        bare = "".join(c for c in seq if not c.islower() and c not in "-.").upper()
        if i == 0 and bare == query:
            continue
        lines += [f">seq{i}", seq]
    if len(lines) < 4:
        die("The target MSA came back with only the query sequence in it.")
    a3m_path.write_text("\n".join(lines) + "\n")


def stage_predict(cfg: dict, campaign: Path, rfd3_root: Path, env: dict, a3m: Path) -> None:
    """Re-fold every designed sequence in complex with the target."""
    sequences = campaign / "mpnn" / "sequences.csv"
    if not sequences.exists():
        die(f"No sequences at {sequences}.")

    # NanoHunter-style template: chain A is the binder (overwritten per design),
    # chain B is the target.
    template = campaign / "config" / "predictor_template.yaml"
    placeholder = "G" * int(cfg.get("max_length", 100))
    template.write_text(
        "sequences:\n"
        "  - protein:\n"
        "      id: A\n"
        f"      sequence: {placeholder}\n"
        "  - protein:\n"
        f"      id: {cfg.get('target_chain', 'B')}\n"
        f"      sequence: {clean_sequence(cfg.get('target_sequence', ''))}\n"
        "version: 1\n"
    )

    yaml_dir = campaign / "predictor_inputs" / "holo"
    run([sys.executable, str(rfd3_root / "scripts" / "prepare_predictor_inputs.py"),
         "--sequences", str(sequences),
         "--template", str(template),
         "--target-msa", str(a3m),
         "--output", str(yaml_dir)],
        campaign / "logs" / "prepare_predictor_inputs.log", rfd3_root, env)

    supported = {"boltz", "intellifold", "intellifold-jax", "alphafold3", "openfold-3-mlx"}
    wanted = [p for p in cfg.get("extra_predictors", []) if p in supported]
    dropped = [p for p in cfg.get("extra_predictors", []) if p not in supported]
    if dropped:
        raise SystemExit(f"Unsupported predictors: {', '.join(dropped)}")
    if not wanted:
        raise SystemExit("Protein campaigns require at least one verification predictor.")
    run([sys.executable, str(rfd3_root / "scripts" / "run_predictors.py"),
         "--inputs", str(yaml_dir),
         "--output", str(campaign / "predictions" / "holo"),
         "--predictors", ",".join(dict.fromkeys(wanted)),
         "--intellifold-model", cfg.get("intellifold_model", "v2-flash"),
         "--max-parallel", str(cfg.get("predict_max_parallel", 4)),
         "--nanohunter-root", cfg["nanohunter_root"],
         "--resume"],
        campaign / "logs" / "predict_holo.log", rfd3_root, env)


def stage_score(cfg: dict, campaign: Path, rfd3_root: Path, env: dict) -> None:
    metrics = campaign / "predictions" / "holo" / "prediction_metrics.csv"
    if not metrics.exists():
        die(f"No prediction metrics at {metrics}.")
    # No --require-pbind: the affinity head is small-molecule only, so a protein
    # campaign ranks on confidence alone.
    run([sys.executable, str(rfd3_root / "scripts" / "score_and_select.py"),
         "--predictions", str(metrics),
         "--output", str(campaign / "analysis"),
         "--top-n", str(cfg.get("top_n", 100)),
         "--protein",
         "--predictors", ",".join(dict.fromkeys(cfg.get("extra_predictors", []))),
         "--sequences", str(campaign / "mpnn" / "sequences.csv"),
         "--require-top-n",
         "--nanohunter-root", cfg["nanohunter_root"]],
        campaign / "logs" / "score.log", rfd3_root, env)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--stage", choices=("all", *STAGES), default="all")
    parser.add_argument("--resume", action="store_true",
                        help="skip stages already recorded complete on disk")
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
    pid_file = campaign / "campaign.pid"
    pid_file.write_text(str(os.getpid()) + "\n")
    atexit.register(lambda: pid_file.unlink(missing_ok=True))

    env = dict(os.environ)
    env.update({"DEBUG": "false", "TOKENIZERS_PARALLELISM": "false"})

    selected = STAGES if args.stage == "all" else (args.stage,)
    started = time.time()
    completed: list[str] = []
    progress_file = campaign / "campaign_progress.json"
    if args.resume and progress_file.exists():
        try:
            completed = [name for name in json.loads(progress_file.read_text()).get("completed_stages", [])
                         if name in STAGES]
        except (OSError, json.JSONDecodeError):
            completed = []
        selected = tuple(name for name in selected if name not in completed)
        if completed:
            info("resuming after completed stages: " + ", ".join(completed))

    def record(current):
        progress_file.write_text(json.dumps({
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
            model = cfg.get("sequence_model", "solublempnn")
            if model not in {"solublempnn", "proteinmpnn"}:
                die(f"Unsupported protein sequence model: {model}")
            model_type = "protein_mpnn" if model == "proteinmpnn" else "soluble_mpnn"
            stage("mpnn", f"Designing sequences with {model_type}")
            run([sys.executable, str(rfd3_root / "scripts" / "run_mpnn.py"),
                 "--backbones", str(campaign / "rfd3" / "backbones"),
                 "--output", str(campaign / "mpnn"),
                 "--model-type", model_type,
                 "--nanohunter-root", cfg["nanohunter_root"],
                 "--temperature", str(cfg.get("sequence_temperature", 0.1)),
                 "--n-seqs", str(cfg.get("sequences_per_backbone", 1)),
                 "--seed", str(cfg["seed_base"] + 31000)],
                logs / "mpnn.log", rfd3_root, env)
            sequences = campaign / "mpnn" / "sequences.csv"
            rows = sum(1 for _ in csv.DictReader(sequences.open())) if sequences.exists() else 0
            expected = cfg["num_backbones"] * cfg.get("sequences_per_backbone", 1)
            if rows != expected:
                die(f"Expected {expected} sequences, found {rows}.")
            info(f"{rows} sequences -> {sequences}")
        elif name == "msa":
            stage("msa", "Generating the target's MSA (once, then reused)")
            msa_path = stage_msa(cfg, campaign, rfd3_root, env)
        elif name == "predict":
            stage("predict", "Re-folding designs with the target")
            msa_path = campaign / "assets" / "target_msa" / "target_full_msa.a3m"
            if not msa_path.exists():
                msa_path = stage_msa(cfg, campaign, rfd3_root, env)
            stage_predict(cfg, campaign, rfd3_root, env, msa_path)
        elif name == "score":
            stage("score", "Ranking designs")
            stage_score(cfg, campaign, rfd3_root, env)
        completed.append(name)
        record(None)

    print(f"RFSTAGE|done|100|Finished in {(time.time() - started) / 60:.1f} min", flush=True)
    print("RFDONE|ok", flush=True)


if __name__ == "__main__":
    main()
