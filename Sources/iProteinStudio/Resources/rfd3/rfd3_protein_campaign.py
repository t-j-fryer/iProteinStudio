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


def target_chain_records(cfg: dict) -> list[tuple[str, str]]:
    sequences = [clean_sequence(value) for value in str(cfg.get("target_sequence", "")).split(":")]
    chains = cfg.get("target_chains") or [value.strip() for value in
              str(cfg.get("target_chain", "B")).split(",") if value.strip()]
    if not sequences or any(not sequence for sequence in sequences):
        die("No target sequence was recorded, so target MSAs cannot be generated.")
    if len(sequences) != len(chains) or len(set(chains)) != len(chains):
        die("Target sequence/chain mapping is inconsistent; reopen the RFdiffusion3 target.")
    allowed = set("ACDEFGHIKLMNPQRSTVWYXBZJUO")
    if any(any(residue not in allowed for residue in sequence) for sequence in sequences):
        die("A target chain contains a character that is not a supported amino-acid code.")
    if any(len(chain) != 1 or not chain.isalpha() for chain in chains):
        die("RFdiffusion3 target chain IDs must be single letters.")
    return list(zip(chains, sequences))


def verification_predictors(cfg: dict) -> list[str]:
    """Validate and canonicalize checkers before any resumable stage runs."""
    supported = {"boltz", "intellifold", "protenix-v2", "protenix-mini", "openfold-3-mlx"}
    requested = cfg.get("extra_predictors", [])
    retired = [p for p in requested if p in {"alphafold3", "intellifold-jax"}]
    if retired:
        raise SystemExit("Retired predictors cannot run: " + ", ".join(retired))
    unknown = [p for p in requested if p not in supported]
    if unknown:
        raise SystemExit("Unsupported predictors: " + ", ".join(unknown))
    wanted = list(dict.fromkeys(requested))
    if sum(value.startswith("protenix-") for value in wanted) > 1:
        raise SystemExit("Choose either Protenix v2 or Mini, not both; they are one model family.")
    if not wanted:
        raise SystemExit("Protein campaigns require at least one verification predictor.")
    return wanted


def stage_one_msa(cfg: dict, campaign: Path, rfd3_root: Path, env: dict,
                  chain: str, sequence: str) -> Path:
    """Generate one exact target-chain MSA and cache it for the campaign.

    Uses Protenix's upstream MSA command when a Protenix checker was selected;
    otherwise uses Boltz. Doing this once and passing the exact A3M by path is
    what makes a multi-thousand-fold campaign affordable and reproducible.
    """
    cache = campaign / "assets" / "target_msa" / f"chain_{chain}"
    a3m = cache / "target_full_msa.a3m"

    if a3m.exists() and validate_a3m(a3m, sequence):
        info(f"chain {chain} target MSA cached -> {a3m}")
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
        f"      id: {chain}\n"
        f"      sequence: {sequence}\n"
        "version: 1\n"
    )

    wanted = verification_predictors(cfg)
    protenix = root / "venvs" / "NanoHunter_protenix" / "bin" / "python"
    protenix_adapter = root / "scripts" / "protenix_msa.py"
    if any(value.startswith("protenix-") for value in wanted):
        if not protenix.exists() or not protenix_adapter.exists():
            die("Protenix was selected but its MSA adapter is not installed.")
        work = cache / "protenix_msa"
        run([str(protenix), str(protenix_adapter), "--sequence", sequence,
             "--output", str(a3m), "--nanohunter-root", str(root),
             "--work-dir", str(work)],
            campaign / "logs" / f"msa_{chain}.log", rfd3_root, env)
        if not validate_a3m(a3m, sequence):
            die("Protenix produced no valid target MSA; refusing a single-sequence fallback.")
        info(f"target MSA -> {a3m}")
        return a3m

    boltz = root / "venvs" / "NanoHunter_boltz" / "bin" / "boltz"
    if not boltz.exists():
        die(f"Boltz not found at {boltz}; the target MSA cannot be generated.")
    out_dir = cache / "boltz"
    run([str(boltz), "predict", str(yaml_path), "--out_dir", str(out_dir),
         "--use_msa_server", "--override"],
        campaign / "logs" / f"msa_{chain}.log", rfd3_root, env)

    raw = sorted(out_dir.rglob("msa/*.csv"))
    if not raw:
        die("Boltz produced no MSA. The MSA server may be unreachable — a run "
            "without a real target MSA would silently be much worse, so this stops here.")
    csv_to_a3m(raw[0], a3m, sequence)
    info(f"target MSA -> {a3m}")
    return a3m


def stage_msas(cfg: dict, campaign: Path, rfd3_root: Path, env: dict) -> dict[str, Path]:
    """Resolve a distinct verified alignment for every fixed target chain."""
    result = {
        chain: stage_one_msa(cfg, campaign, rfd3_root, env, chain, sequence)
        for chain, sequence in target_chain_records(cfg)
    }
    manifest = campaign / "assets" / "target_msa" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({chain: str(path) for chain, path in result.items()}, indent=2) + "\n")
    return result


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


def stage_predict(cfg: dict, campaign: Path, rfd3_root: Path, env: dict,
                  msas: dict[str, Path]) -> None:
    """Re-fold every designed sequence in complex with the target."""
    sequences = campaign / "mpnn" / "sequences.csv"
    if not sequences.exists():
        die(f"No sequences at {sequences}.")

    # NanoHunter-style template: chain A is the binder (overwritten per design),
    # followed by every fixed target subunit in its explicit structure order.
    template = campaign / "config" / "predictor_template.yaml"
    placeholder = "G" * int(cfg.get("max_length", 100))
    lines = ["sequences:", "  - protein:", "      id: A",
             f"      sequence: {placeholder}"]
    for chain, sequence in target_chain_records(cfg):
        lines += ["  - protein:", f"      id: {chain}",
                  f"      sequence: {sequence}"]
    lines.append("version: 1")
    template.write_text("\n".join(lines) + "\n")

    msa_manifest = campaign / "assets" / "target_msa" / "manifest.json"
    msa_manifest.write_text(json.dumps({chain: str(path) for chain, path in msas.items()}, indent=2) + "\n")

    yaml_dir = campaign / "predictor_inputs" / "holo"
    run([sys.executable, str(rfd3_root / "scripts" / "prepare_predictor_inputs.py"),
         "--sequences", str(sequences),
         "--template", str(template),
         "--target-msa-map", str(msa_manifest),
         "--output", str(yaml_dir)],
        campaign / "logs" / "prepare_predictor_inputs.log", rfd3_root, env)

    wanted = verification_predictors(cfg)
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
         "--predictors", ",".join(verification_predictors(cfg)),
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

    # Validate launch identities even when Resume starts after prediction. A
    # stale retired checker must never survive merely because its fold stage was
    # marked complete in an older campaign.
    verification_predictors(cfg)

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
            stage("msa", "Resolving each target chain's MSA (once, then reused)")
            stage_msas(cfg, campaign, rfd3_root, env)
        elif name == "predict":
            stage("predict", "Re-folding designs with the target")
            manifest = campaign / "assets" / "target_msa" / "manifest.json"
            try:
                saved = json.loads(manifest.read_text())
                msas = {chain: Path(path) for chain, path in saved.items()}
            except (OSError, json.JSONDecodeError):
                msas = stage_msas(cfg, campaign, rfd3_root, env)
            expected = {chain for chain, _ in target_chain_records(cfg)}
            if set(msas) != expected or any(not path.exists() for path in msas.values()):
                msas = stage_msas(cfg, campaign, rfd3_root, env)
            stage_predict(cfg, campaign, rfd3_root, env, msas)
        elif name == "score":
            stage("score", "Ranking designs")
            stage_score(cfg, campaign, rfd3_root, env)
        completed.append(name)
        record(None)

    print(f"RFSTAGE|done|100|Finished in {(time.time() - started) / 60:.1f} min", flush=True)
    print("RFDONE|ok", flush=True)


if __name__ == "__main__":
    main()
