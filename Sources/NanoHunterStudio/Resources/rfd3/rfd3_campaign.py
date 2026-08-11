#!/usr/bin/env python3
"""Run an RFdiffusion3 design campaign from a Studio campaign JSON.

This generalises ``RFD3/scripts/run_dtf401_campaign.py`` — which is small-molecule
only — to cover protein targets as well, and adds machine-parseable progress so
the app can show a live dashboard. **It does not reimplement any science.** Every
stage shells out to the same validated script the RFD3 repo already uses; the
only new code here is the protein-target branch, the spec assembly, and the
progress markers.

Stages, each independently resumable by checking for its expected artefact:

    target      SMILES/structure -> CCD component + PDB + conditioning spec
    fixtures    one Foundry fixture per binder-length bin
    backbones   MLX sampling, natively batched by shape
    mpnn        inverse folding (SolubleMPNN for protein, LigandMPNN for ligand)
    predict     independent re-fold with the chosen predictors
    score       rank and select
    apo         re-fold the top designs without the target
    rmsd        self-consistency between designed and re-folded backbones

Why length bins exist: an RFD3 fixture is frozen at a single binder length, and
"different lengths cannot share a native tensor batch". Covering a length range
therefore means several fixtures, each internally batched by shape — which is
exactly the "same length within a batch, different lengths between batches"
behaviour we want, and it is why the batch-8 optimum is preserved.

Progress markers on stdout:
    RFSTAGE|<name>|<0-100>|<message>
    RFINFO|<message>
    RFDONE|ok
    RFFAIL|<message>
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

STAGES = ["target", "fixtures", "backbones", "mpnn", "predict", "score", "apo", "rmsd"]
STAGE_PCT = {"target": 2, "fixtures": 10, "backbones": 25, "mpnn": 65,
             "predict": 75, "score": 90, "apo": 93, "rmsd": 98}


def stage(name: str, message: str) -> None:
    print(f"RFSTAGE|{name}|{STAGE_PCT.get(name, 0)}|{message}", flush=True)


def info(message: str) -> None:
    print(f"RFINFO|{message}", flush=True)


def die(message: str) -> None:
    print(f"RFFAIL|{message}", flush=True)
    sys.exit(1)


def run(cmd: list, log_path: Path, rfd3_root: Path, env: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    info(f"$ {' '.join(str(c) for c in cmd)}")
    started = time.time()
    with log_path.open("w") as handle:
        result = subprocess.run(cmd, cwd=rfd3_root, env=env, stdout=handle, stderr=subprocess.STDOUT)
    wall = time.time() - started
    if result.returncode:
        tail = ""
        try:
            tail = "\n".join(log_path.read_text().splitlines()[-12:])
        except OSError:
            pass
        die(f"Stage failed after {wall:.0f}s (exit {result.returncode}). Log: {log_path}\n{tail}")
    info(f"ok ({wall:.0f}s) -> {log_path}")


# ------------------------------------------------------------------ target --

def stage_target(cfg: dict, campaign: Path, rfd3_root: Path, env: dict, python: str) -> None:
    """Turn the user's target into something RFD3 can be given.

    Small molecule: RFD3 has no SMILES field, so the molecule becomes an
    explicit CCD component plus a chain-L PDB. Chain L specifically -- Foundry
    reserves chain A for the diffused binder and errors if the ligand shares it.

    Protein: the structure is used directly; only the conditioning spec is built.
    """
    stage("target", "Preparing your target")
    assets = campaign / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    base_json = campaign / "config" / "base_input.json"
    base_json.parent.mkdir(parents=True, exist_ok=True)
    design_name = cfg["design_name"]

    if cfg["target_kind"] == "small_molecule":
        manifest = assets / "ligand" / "atom_selections.json"
        if manifest.exists() and not cfg.get("force_target"):
            info(f"target: cached -> {manifest}")
            return
        spec_path = campaign / "config" / "ligand_spec.json"
        spec_path.write_text(json.dumps(cfg["ligand_spec"], indent=2) + "\n")
        run([python, str(rfd3_root / "scripts" / "prepare_ligand_target.py"),
             "--spec", str(spec_path),
             "--component-id", cfg["component_id"],
             "--output-dir", str(assets / "ligand"),
             "--design-name", design_name,
             "--base-json", str(base_json)],
            campaign / "logs" / "target.log", rfd3_root, env)
    else:
        # Protein target: assemble the DesignInputSpecification directly. There
        # is no ligand component to build, so there is nothing to shell out to.
        spec = {
            "input": cfg["target_structure"],
            "contig": cfg["contig"],
            "length": "PLACEHOLDER",   # build_length_bins.py overwrites per bin
        }
        if cfg.get("hotspots"):
            spec["select_hotspots"] = ",".join(cfg["hotspots"])
        if cfg.get("infer_ori_strategy"):
            spec["infer_ori_strategy"] = cfg["infer_ori_strategy"]
        if cfg.get("ori_token"):
            spec["ori_token"] = cfg["ori_token"]
        if cfg.get("is_non_loopy") is not None:
            spec["is_non_loopy"] = bool(cfg["is_non_loopy"])
        spec["redesign_motif_sidechains"] = False
        base_json.write_text(json.dumps({design_name: spec}, indent=2) + "\n")
        info(f"target: protein spec written -> {base_json}")


def apply_global_conditioning(cfg: dict, campaign: Path) -> None:
    """Add the global conditioning fields to whatever the target stage wrote.

    ``prepare_ligand_target.py`` owns the per-atom selections, but not the
    global flags, so they are merged in here rather than by patching that script.
    """
    base_json = campaign / "config" / "base_input.json"
    if not base_json.exists():
        die(f"Expected {base_json} to exist after the target stage.")
    data = json.loads(base_json.read_text())
    name = cfg["design_name"]
    if name not in data:
        die(f"{name!r} not found in {base_json} (keys: {list(data)})")
    spec = data[name]

    # Spelled is_non_loopy, not is_not_loopy. The pinned rfd3 build sets
    # extra="forbid" so a misspelling raises -- but rfd3na sets extra="allow"
    # and would silently swallow it, so this is worth being exact about.
    if cfg.get("is_non_loopy") is not None:
        spec["is_non_loopy"] = bool(cfg["is_non_loopy"])
    if cfg.get("infer_ori_strategy"):
        spec["infer_ori_strategy"] = cfg["infer_ori_strategy"]
    if cfg.get("ori_token"):
        spec["ori_token"] = cfg["ori_token"]
        spec.pop("infer_ori_strategy", None)

    data[name] = spec
    base_json.write_text(json.dumps(data, indent=2) + "\n")
    info(f"conditioning: is_non_loopy={spec.get('is_non_loopy')} "
         f"origin={spec.get('ori_token') or spec.get('infer_ori_strategy')}")


# ---------------------------------------------------------------- fixtures --

def stage_fixtures(cfg: dict, campaign: Path, rfd3_root: Path, env: dict, python: str) -> None:
    stage("fixtures", f"Building {cfg['num_bins']} length bins "
                      f"({cfg['min_length']}-{cfg['max_length']} residues)")
    if cfg["target_kind"] == "small_molecule":
        run([python, str(rfd3_root / "scripts" / "build_length_bins.py"),
             "--base-json", str(campaign / "config" / "base_input.json"),
             "--design-name", cfg["design_name"],
             "--ligand-manifest", str(campaign / "assets" / "ligand" / "atom_selections.json"),
             "--output", str(campaign),
             "--min-length", str(cfg["min_length"]),
             "--max-length", str(cfg["max_length"]),
             "--num-bins", str(cfg["num_bins"]),
             "--num-designs", str(cfg["num_designs"]),
             "--timesteps", str(cfg["timesteps"]),
             "--n-recycle", str(cfg["recycles"]),
             "--seed-base", str(cfg["seed_base"])],
            campaign / "logs" / "fixtures.log", rfd3_root, env)
    else:
        _build_bins_protein(cfg, campaign, rfd3_root, env, python)


def _bin_lengths(min_length: int, max_length: int, num_bins: int) -> list[int]:
    """Identical to build_length_bins.bin_lengths -- kept in step deliberately."""
    if num_bins < 1:
        die("Number of length bins must be at least 1.")
    if num_bins == 1:
        return [min_length]
    step = (max_length - min_length) / (num_bins - 1)
    return sorted({round(min_length + step * i) for i in range(num_bins)})


def _build_bins_protein(cfg: dict, campaign: Path, rfd3_root: Path, env: dict, python: str) -> None:
    """Length-bin a protein target.

    ``RFD3/scripts/build_length_bins.py`` requires a ligand manifest, so it
    cannot be used for a protein target as it stands. This mirrors its logic and
    writes a byte-compatible ``bin_manifest.json`` so ``run_backbone_bins.py``
    consumes it unchanged. If that upstream script gains an optional ligand
    manifest, delete this and call it instead.
    """
    base = json.loads((campaign / "config" / "base_input.json").read_text())
    design_name = cfg["design_name"]
    design_input = base[design_name]

    lengths = _bin_lengths(cfg["min_length"], cfg["max_length"], cfg["num_bins"])
    total = cfg["num_designs"]
    base_quota, remainder = divmod(total, len(lengths))
    quotas = [base_quota + (1 if i < remainder else 0) for i in range(len(lengths))]

    oracle_dir = rfd3_root / "oracle"
    oracle_dir.mkdir(exist_ok=True)
    rfd3_dir = campaign / "rfd3"
    rfd3_dir.mkdir(parents=True, exist_ok=True)

    bins = []
    for i, (length, quota) in enumerate(zip(lengths, quotas)):
        name = f"{design_name}_L{length}"
        input_json = oracle_dir / f"input_{name}.json"
        fixture = oracle_dir / f"oracle_{name}.npz"
        spec = dict(design_input)
        spec["length"] = f"{length}-{length}"
        input_json.write_text(json.dumps({name: spec}, indent=2) + "\n")

        if fixture.exists():
            info(f"bin {i} (L={length}): fixture cached")
        else:
            # This is also the fail-fast validation point for the conditioning
            # spec: a bad chain/residue key raises here, before any GPU time.
            run([python, str(rfd3_root / "milestone0_oracle.py"),
                 "--name", name, "--input_json", str(input_json),
                 "--timesteps", str(cfg["timesteps"]),
                 "--n_recycle", str(cfg["recycles"]),
                 "--seed", str(cfg["seed_base"] + i)],
                rfd3_dir / f"fixture_{name}.log", rfd3_root, env)

        bins.append({"bin_index": i, "length": length, "quota": quota, "name": name,
                     "input_json": str(input_json), "fixture": str(fixture),
                     "seed": cfg["seed_base"] + i})

    manifest = {
        "design_name": design_name,
        "component_id": None,
        "ccd_mirror": None,
        "num_designs": total,
        "min_length": cfg["min_length"],
        "max_length": cfg["max_length"],
        "timesteps": cfg["timesteps"],
        "n_recycle": cfg["recycles"],
        "bins": bins,
    }
    (rfd3_dir / "bin_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    info(f"wrote {len(bins)} bins ({sum(quotas)} designs) -> {rfd3_dir / 'bin_manifest.json'}")


# --------------------------------------------------------------- backbones --

def stage_backbones(cfg: dict, campaign: Path, rfd3_root: Path, env: dict, python: str) -> None:
    # Batch 8 with two shape queues is the measured optimum on an M4 Max, and it
    # is deliberately NOT derived from free memory: peak footprint barely moved
    # between batch 1 and 32 while throughput fell off a cliff above 8, so the
    # limit is Metal kernel behaviour, not capacity.
    stage("backbones", f"Generating {cfg['num_designs']} backbones "
                       f"(batch {cfg['batch_size']} x {cfg['queues_per_bin']} queues)")
    cmd = [python, str(rfd3_root / "scripts" / "run_backbone_bins.py"),
           "--bin-manifest", str(campaign / "rfd3" / "bin_manifest.json"),
           "--output", str(campaign / "rfd3"),
           "--batch-size", str(cfg["batch_size"]),
           "--queues-per-bin", str(cfg["queues_per_bin"]),
           "--precision", cfg["precision"],
           "--steps", str(cfg["timesteps"]),
           "--recycle", str(cfg["recycles"])]
    if cfg["target_kind"] == "small_molecule":
        cmd += ["--ligand-code", cfg["component_id"]]
    run(cmd, campaign / "logs" / "backbones.log", rfd3_root, env)


# -------------------------------------------------------------------- mpnn --

def stage_mpnn(cfg: dict, campaign: Path, rfd3_root: Path, env: dict, python: str) -> None:
    # Routing is deliberately restricted: protein target -> SolubleMPNN,
    # small molecule -> LigandMPNN. AbMPNN and AntiFold stay nanobody-only.
    model = "ligand_mpnn" if cfg["target_kind"] == "small_molecule" else "soluble_mpnn"
    stage("mpnn", f"Designing sequences with {'LigandMPNN' if model == 'ligand_mpnn' else 'SolubleMPNN'}")
    run([python, str(rfd3_root / "scripts" / "run_mpnn.py"),
         "--backbones", str(campaign / "rfd3" / "backbones"),
         "--output", str(campaign / "mpnn"),
         "--model-type", model,
         "--nanohunter-root", cfg["nanohunter_root"],
         "--seed", str(cfg["seed_base"] + 31000)],
        campaign / "logs" / "mpnn.log", rfd3_root, env)


# ----------------------------------------------------------------- predict --

def stage_predict(cfg: dict, campaign: Path, rfd3_root: Path, env: dict, python: str,
                  mode: str = "holo") -> None:
    label = "Re-folding designs" if mode == "holo" else "Re-folding the best designs without the target"
    stage("predict" if mode == "holo" else "apo", label)
    sequences = (campaign / "mpnn" / "sequences.csv") if mode == "holo" \
        else (campaign / "analysis" / f"top{cfg['top_n']}.csv")
    if not sequences.exists():
        die(f"Expected sequences at {sequences}.")

    yaml_dir = campaign / "predictor_inputs" / mode
    prep = [python, str(rfd3_root / "scripts" / "prepare_boltz_yaml.py"),
            "--sequences", str(sequences), "--output", str(yaml_dir), "--mode", mode]
    if mode == "holo" and cfg["target_kind"] == "small_molecule":
        prep += ["--smiles", cfg["ligand_spec"]["smiles"]]
    run(prep, campaign / "logs" / f"prepare_yaml_{mode}.log", rfd3_root, env)

    predictors = cfg["predictors"]
    # Boltz is the only backend with an affinity head, and run_boltz_affinity.py
    # is the script that drives it, so it gets its own path. Everything else goes
    # through the generic multi-predictor runner.
    if predictors == ["boltz"] and cfg.get("run_affinity", True):
        cmd = [python, str(rfd3_root / "scripts" / "run_boltz_affinity.py"),
               "--inputs", str(yaml_dir),
               "--output", str(campaign / "predictions" / mode),
               "--chunk-size", str(cfg["boltz_chunk_size"]),
               "--nanohunter-root", cfg["nanohunter_root"]]
        cmd += ["--use-potentials"] if cfg.get("use_potentials", True) else ["--no-use-potentials"]
        if mode == "holo":
            cmd += ["--calibrate-n", str(cfg["boltz_calibrate_n"])]
        else:
            # Reuse the concurrency the holo run calibrated rather than paying
            # for a second calibration on a smaller job.
            holo_manifest = campaign / "predictions" / "holo" / "run_manifest.json"
            parallel = 1
            if holo_manifest.exists():
                parallel = json.loads(holo_manifest.read_text()).get("parallel", 1)
            cmd += ["--parallel", str(parallel)]
    else:
        cmd = [python, str(rfd3_root / "scripts" / "run_predictors.py"),
               "--inputs", str(yaml_dir),
               "--output", str(campaign / "predictions" / mode),
               "--predictors", ",".join(predictors),
               "--max-parallel", str(cfg["predict_max_parallel"]),
               "--nanohunter-root", cfg["nanohunter_root"],
               "--resume"]
    run(cmd, campaign / "logs" / f"predict_{mode}.log", rfd3_root, env)


# ------------------------------------------------------------- score / rmsd --

def stage_score(cfg: dict, campaign: Path, rfd3_root: Path, env: dict, python: str) -> None:
    stage("score", "Ranking designs")
    run([python, str(rfd3_root / "scripts" / "score_and_select.py"),
         "--predictions", str(campaign / "predictions" / "holo" / "prediction_metrics.csv"),
         "--output", str(campaign / "analysis"),
         "--top-n", str(cfg["top_n"]),
         "--nanohunter-root", cfg["nanohunter_root"]],
        campaign / "logs" / "score.log", rfd3_root, env)


def stage_rmsd(cfg: dict, campaign: Path, rfd3_root: Path, env: dict, python: str) -> None:
    stage("rmsd", "Checking self-consistency")
    run([python, str(rfd3_root / "scripts" / "compute_rmsd.py"), "--campaign", str(campaign)],
        campaign / "logs" / "rmsd.log", rfd3_root, env)


# -------------------------------------------------------------------- main --

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--stage", choices=["all", *STAGES], default="all")
    args = parser.parse_args()

    try:
        cfg = json.loads(args.config.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        die(f"Could not read campaign config {args.config}: {exc}")

    rfd3_root = Path(cfg["rfd3_root"]).resolve()
    if not (rfd3_root / "scripts" / "generate_backbones.py").exists():
        die(f"{rfd3_root} does not look like an RFdiffusion3 checkout.")
    python = cfg.get("python") or str(rfd3_root / ".venv" / "bin" / "python")
    if not Path(python).exists():
        die(f"RFdiffusion3 Python environment not found at {python}. Install RFdiffusion3 support first.")

    campaign = Path(cfg["campaign_dir"]).resolve()
    campaign.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    # The dev machine's global shell sets DEBUG=release, which Foundry cannot
    # parse as a boolean. Every Foundry call therefore needs DEBUG=false.
    env["DEBUG"] = "false"
    env["TOKENIZERS_PARALLELISM"] = "false"
    if cfg["target_kind"] == "small_molecule":
        env["CCD_MIRROR_PATH"] = str(campaign / "assets" / "ligand" / "ccd")

    selected = STAGES if args.stage == "all" else [args.stage]
    started = time.time()

    for name in selected:
        if name == "apo" and not cfg.get("run_apo", True):
            info("apo: skipped (not requested)")
            continue
        if name == "rmsd" and not cfg.get("run_apo", True):
            info("rmsd: skipped (needs the apo stage)")
            continue
        if name == "target":
            stage_target(cfg, campaign, rfd3_root, env, python)
            apply_global_conditioning(cfg, campaign)
        elif name == "fixtures":
            stage_fixtures(cfg, campaign, rfd3_root, env, python)
        elif name == "backbones":
            stage_backbones(cfg, campaign, rfd3_root, env, python)
        elif name == "mpnn":
            stage_mpnn(cfg, campaign, rfd3_root, env, python)
        elif name == "predict":
            stage_predict(cfg, campaign, rfd3_root, env, python, "holo")
        elif name == "score":
            stage_score(cfg, campaign, rfd3_root, env, python)
        elif name == "apo":
            stage_predict(cfg, campaign, rfd3_root, env, python, "apo")
        elif name == "rmsd":
            stage_rmsd(cfg, campaign, rfd3_root, env, python)

    manifest_path = campaign / "run_manifest.json"
    manifest = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError:
            manifest = {}
    manifest["stages_completed"] = sorted(set(manifest.get("stages_completed", [])) | set(selected))
    manifest["last_wall_sec"] = time.time() - started
    manifest["config"] = str(args.config)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"RFSTAGE|done|100|Campaign finished in {(time.time() - started) / 60:.1f} min", flush=True)
    print("RFDONE|ok", flush=True)


if __name__ == "__main__":
    main()
