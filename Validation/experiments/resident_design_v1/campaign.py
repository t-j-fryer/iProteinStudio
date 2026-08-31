#!/usr/bin/env python3
"""Plan, run and audit the SUMO resident-design validation campaign."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CONFIG_PATH = HERE / "config.json"
DEFAULT_OUTPUT = ROOT / "Validation" / "output" / "resident_design_v1"
RUNNER = ROOT / "Sources/iProteinStudio/Resources/pipeline/nanohunter_run.sh"
SETUP = ROOT / "Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh"


def die(message: str) -> None:
    raise SystemExit(f"resident_design_v1: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def query_from_a3m(path: Path) -> str:
    sequence: list[str] = []
    seen_header = False
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            if seen_header and sequence:
                break
            seen_header = True
            continue
        if seen_header:
            sequence.append(line)
    return "".join(sequence).replace("-", "").upper()


def resolve_msa(config: dict, explicit: Path | None) -> Path:
    target = config["target"]
    candidates: list[Path] = []
    if explicit:
        candidates.append(explicit)
    environment = os.environ.get(target["msa_environment"])
    if environment:
        candidates.append(Path(environment))

    # Studio's cache index is the normal user-facing source. The validation
    # fixture is selected by content, never by a machine-specific saved path.
    index = Path.home() / ".iproteinstudio" / "msa_cache" / "index.json"
    if index.is_file():
        try:
            document = json.loads(index.read_text())
        except json.JSONDecodeError:
            document = {}

        def collect(value: object) -> None:
            if isinstance(value, str) and value.endswith((".a3m", ".sto")):
                candidates.append(Path(value))
            elif isinstance(value, dict):
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)
        collect(document)

    expected_hash = target["msa_sha256"]
    expected_query = target["sequence"]
    for candidate in candidates:
        path = candidate.expanduser().resolve()
        if path.is_file() and sha256(path) == expected_hash:
            if query_from_a3m(path) != expected_query:
                die(f"MSA checksum matched but query sequence did not: {path}")
            return path
    die(
        "the exact SUMO A3M was not found. Set "
        f"{target['msa_environment']} or pass --msa; expected SHA-256 {expected_hash}"
    )


def git_state() -> dict:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    diff = subprocess.check_output(
        ["git", "diff", "--binary", "HEAD"], cwd=ROOT
    )
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, text=True
    ).splitlines()
    untracked_hashes = {
        item: sha256(ROOT / item) for item in sorted(untracked)
        if (ROOT / item).is_file() and "Validation/output/" not in item
    }
    return {
        "commit": commit,
        "tracked_diff_sha256": hashlib.sha256(diff).hexdigest(),
        "untracked_files": untracked_hashes,
    }


def template_text(config: dict, msa: Path, constrained: bool) -> str:
    metadata = ""
    if constrained:
        residues = ", ".join(config["target"]["constraint_epitope"])
        metadata = (
            "nanohunter:\n"
            f"  target_epitope_residues: [{residues}]\n"
            "  protenix_pocket_max_distance: 8.0\n"
        )
    target = config["target"]["sequence"]
    binder = "X" * int(config["campaign"]["binder_min_length"])
    return (
        metadata
        + "sequences:\n"
        + "  - protein:\n      id: A\n      sequence: " + binder + "\n      msa: empty\n"
        + "  - protein:\n      id: B\n      sequence: " + target + "\n"
        + f"      msa: {msa}\nversion: 1\n"
    )


def build_command(config: dict, output: Path, engine_name: str, arm_name: str,
                  template: Path) -> list[str]:
    campaign = config["campaign"]
    engine = config["engines"][engine_name]
    arm = config["arms"][arm_name]
    run_name = f"{engine_name}__{arm_name}"
    command = [
        "bash", str(RUNNER),
        "--workflow", "protein",
        "--predictor", engine["predictor"],
        "--sequence-designer", "solublempnn",
        "--template-yaml", str(template),
        "--run-name", run_name,
        "--out-root", str(output / "campaigns"),
        "--num-runs", str(campaign["trajectories"]),
        "--num-opt-cycles", str(campaign["design_cycles"]),
        "--iptm-threshold", f"{campaign['hit_threshold']:.2f}",
        "--post-predictor", "none", "--post-mode", "none",
        "--predictor-seed", str(campaign["predictor_seed"]),
        "--predictor-samples", str(campaign["predictor_samples"]),
        "--mpnn-seed", str(campaign["mpnn_seed"]),
        "--binder-random-seed", str(campaign["binder_seed"]),
        "--random-binder",
        "--binder-min-len", str(campaign["binder_min_length"]),
        "--binder-max-len", str(campaign["binder_max_length"]),
        "--target-msa-mode", "auto", "--target-msa-generator", "auto",
        "--require-target-msa",
        "--max-parallel", "1", "--skip-predictor-calibration",
        "--throughput-profile", "off",
        "--mps-memory-reserve-gb", "8", "--mps-mem-fraction", "0.65",
        "--resume",
    ]
    if "model" in engine:
        command += ["--model", engine["model"]]
    if engine["predictor"] == "boltz":
        command += ["--boltz-no-potentials", "--boltz-contact-mode", "none"]
    if arm["scheduler"] != "run":
        command += ["--design-scheduler", arm["scheduler"], "--wave-batch-size", "all"]
    if engine["predictor"] == "intellifold" and arm.get("intellifold_buckets"):
        command += ["--intellifold-buckets", arm["intellifold_buckets"]]
    if arm["helix_kill"] > 0:
        command += ["--helix-kill", "--negative-helix-constant", str(arm["helix_kill"])]
    return command


def selected(all_values: dict, requested: str | None, enabled_only: bool = False) -> list[str]:
    enabled = {
        key for key, value in all_values.items()
        if not enabled_only or value.get("enabled", True)
    }
    if not requested:
        return [key for key in all_values if key in enabled]
    values = [item.strip() for item in requested.split(",") if item.strip()]
    unknown = sorted(set(values) - set(all_values))
    if unknown:
        die(f"unknown selection(s): {', '.join(unknown)}")
    disabled = sorted(set(values) - enabled)
    if disabled:
        reasons = "; ".join(
            f"{name}: {all_values[name].get('blocked_reason', 'disabled')}"
            for name in disabled
        )
        die(f"disabled selection(s): {reasons}")
    return values


def make_manifest(args: argparse.Namespace) -> tuple[dict, Path]:
    config = json.loads(CONFIG_PATH.read_text())
    output = args.output.expanduser().resolve()
    msa = resolve_msa(config, args.msa)
    runtime_root = (Path.home() / ".iproteinstudio").resolve()
    if not runtime_root.is_dir():
        die(f"installed runtime not found: {runtime_root}")
    runtime_scripts = {}
    for relative in (
        "scripts/intellifold_predict.py",
        "scripts/protenix_predict.py",
        "scripts/resident_predictor.py",
        "scripts/ipsae_score.py",
        "scripts/select_post_tasks.py",
    ):
        bundled = RUNNER.parent / relative
        installed = runtime_root / relative
        if not bundled.is_file() or not installed.is_file():
            die(f"required predictor adapter is missing: {relative}")
        expected = sha256(bundled)
        if sha256(installed) != expected:
            die(f"managed predictor adapter is stale: {relative}; launch the updated app once")
        runtime_scripts[relative] = expected
    templates = output / "inputs"
    templates.mkdir(parents=True, exist_ok=True)
    engines = selected(config["engines"], args.engines)
    arms = selected(config["arms"], args.arms, enabled_only=True)
    jobs = []
    for engine_name in engines:
        engine = config["engines"][engine_name]
        template = templates / f"sumo_{engine_name}.yaml"
        template.write_text(template_text(config, msa, bool(engine.get("constraint"))))
        for arm_name in arms:
            engine_filter = config["arms"][arm_name].get("engine_filter")
            if engine_filter and engine_name not in engine_filter:
                continue
            jobs.append({
                "engine": engine_name,
                "arm": arm_name,
                "run_name": f"{engine_name}__{arm_name}",
                "command": build_command(config, output, engine_name, arm_name, template),
            })
    detect_environment = dict(os.environ)
    detect_environment["NANOHUNTER_ROOT"] = str(runtime_root)
    detect = subprocess.run(
        ["bash", str(SETUP), "--detect"], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True,
        env=detect_environment,
    ).stdout
    detected = {}
    for line in detect.splitlines():
        if line.startswith("NHSTATE|"):
            parts = line.split("|", 3)
            if len(parts) >= 3:
                detected[parts[1]] = parts[2]
    components = {
        "boltz2": "boltz",
        "intellifold_flash": "intellifold",
        "intellifold_v2": "intellifold",
        "protenix_v2": "protenix",
        "protenix_mini": "protenix",
        "protenix_constraint": "protenix_constraint",
    }
    unavailable = [
        name for name in engines
        if detected.get(components[name]) != "ok"
    ]
    if unavailable:
        die("selected engine(s) are not ready: " + ", ".join(unavailable))
    manifest = {
        "schema": 1,
        "created_epoch": time.time(),
        "planner_sha256": sha256(Path(__file__).resolve()),
        "config_sha256": sha256(CONFIG_PATH),
        "runner_sha256": sha256(RUNNER),
        "git": git_state(),
        "msa": {"path": str(msa), "sha256": sha256(msa), "query": query_from_a3m(msa)},
        "engine_detection": detect,
        "runtime_root": str(runtime_root),
        "runtime_script_sha256": runtime_scripts,
        "jobs": jobs,
    }
    return manifest, output


def plan(args: argparse.Namespace) -> None:
    manifest, output = make_manifest(args)
    atomic_json(output / "manifest.json", manifest)
    print(f"Planned {len(manifest['jobs'])} campaign(s): {output / 'manifest.json'}")


def assert_frozen(manifest: dict) -> None:
    if manifest.get("planner_sha256") != sha256(Path(__file__).resolve()):
        die("campaign planner changed after planning; create a new manifest")
    if manifest["config_sha256"] != sha256(CONFIG_PATH):
        die("config changed after planning; create a new manifest")
    if manifest["runner_sha256"] != sha256(RUNNER):
        die("runner changed after planning; create a new manifest")
    msa = Path(manifest["msa"]["path"])
    if not msa.is_file() or sha256(msa) != manifest["msa"]["sha256"]:
        die("planned MSA is missing or changed")
    if manifest.get("git") != git_state():
        die("repository state changed after planning; create a new manifest")
    runtime_root = Path(manifest["runtime_root"])
    for relative, expected in manifest.get("runtime_script_sha256", {}).items():
        installed = runtime_root / relative
        if not installed.is_file() or sha256(installed) != expected:
            die(f"managed predictor adapter changed after planning: {relative}")
    detect_environment = dict(os.environ)
    detect_environment["NANOHUNTER_ROOT"] = manifest["runtime_root"]
    current_detection = subprocess.run(
        ["bash", str(SETUP), "--detect"], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True,
        env=detect_environment,
    ).stdout
    if manifest.get("engine_detection") != current_detection:
        die("installed engine inventory changed after planning; create a new manifest")


def run(args: argparse.Namespace) -> None:
    output = args.output.expanduser().resolve()
    manifest_path = output / "manifest.json"
    if not manifest_path.is_file():
        die("no manifest; run plan first")
    manifest = json.loads(manifest_path.read_text())
    assert_frozen(manifest)
    campaign = json.loads(CONFIG_PATH.read_text())["campaign"]
    expected_designs = campaign["trajectories"] * campaign["design_cycles"]
    environment = dict(os.environ)
    environment["NANOHUNTER_ROOT"] = manifest["runtime_root"]
    for job in manifest["jobs"]:
        receipt = output / "receipts" / f"{job['run_name']}.json"
        if receipt.is_file() and json.loads(receipt.read_text()).get("returncode") == 0:
            designs, errors = audit_campaign(
                output / "campaigns" / job["run_name"],
                campaign["trajectories"], campaign["design_cycles"],
            )
            if not errors and designs == expected_designs:
                print(f"SKIP audited receipt: {job['run_name']}")
                continue
            print(f"REPAIR incomplete receipt: {job['run_name']}", flush=True)
        log = output / "logs" / f"{job['run_name']}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        start = time.time()
        print(f"RUN {job['run_name']}", flush=True)
        with log.open("w") as handle:
            completed = subprocess.run(job["command"], cwd=ROOT, env=environment, text=True,
                                       stdout=handle, stderr=subprocess.STDOUT)
        returncode = completed.returncode
        audit_errors: list[str] = []
        designs = 0
        if returncode == 0:
            designs, audit_errors = audit_campaign(
                output / "campaigns" / job["run_name"],
                campaign["trajectories"], campaign["design_cycles"],
            )
            if audit_errors or designs != expected_designs:
                returncode = 3
        result = {
            "run_name": job["run_name"], "command": job["command"],
            "start_epoch": start, "end_epoch": time.time(),
            "wall_seconds": time.time() - start,
            "returncode": returncode, "log": str(log),
            "designs_excluding_cycle00": designs,
            "audit_errors": audit_errors,
        }
        atomic_json(receipt, result)
        if returncode:
            die(f"{job['run_name']} failed; inspect {log}")


def audit_campaign(path: Path, trajectories: int, design_cycles: int) -> tuple[int, list[str]]:
    errors: list[str] = []
    designs = 0
    for run_index in range(1, trajectories + 1):
        run_dir = path / f"run_{run_index:03d}"
        for cycle in range(0, design_cycles + 1):
            cycle_dir = run_dir / f"cycle_{cycle:02d}" / "pred_min"
            structures = [candidate for candidate in
                          (cycle_dir / "model_0.cif", cycle_dir / "model_0.pdb")
                          if candidate.is_file()]
            if len(structures) != 1:
                errors.append(f"{run_dir.name}/cycle_{cycle:02d}: expected one normalized structure")
            if not (cycle_dir / "confidence.json").is_file():
                errors.append(f"{run_dir.name}/cycle_{cycle:02d}: confidence.json missing")
            if cycle > 0 and structures:
                designs += 1
    return designs, errors


def analyze(args: argparse.Namespace) -> None:
    output = args.output.expanduser().resolve()
    manifest = json.loads((output / "manifest.json").read_text())
    config = json.loads(CONFIG_PATH.read_text())
    campaign = config["campaign"]
    rows = []
    any_errors = False
    for job in manifest["jobs"]:
        run_path = output / "campaigns" / job["run_name"]
        designs, errors = audit_campaign(
            run_path, campaign["trajectories"], campaign["design_cycles"]
        )
        receipt_path = output / "receipts" / f"{job['run_name']}.json"
        receipt = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
        predictor_seconds = 0.0
        inverse_seconds = 0.0
        startup_seconds = 0.0
        model_loads = 0
        if job["arm"] == "current":
            for timing in run_path.glob("run_*/timing_cycles.csv"):
                with timing.open(newline="") as handle:
                    predictor_seconds += sum(float(row["duration_sec"]) for row in csv.DictReader(handle))
            model_loads = campaign["trajectories"] * (campaign["design_cycles"] + 1)
        else:
            wave = run_path / "_cycle_wave"
            predictor_table = wave / "predictor_batches.csv"
            inverse_table = wave / "inverse_folding_batches.csv"
            if predictor_table.is_file():
                with predictor_table.open(newline="") as handle:
                    predictor_rows = list(csv.DictReader(handle))
                predictor_seconds = sum(float(row["duration_sec"]) for row in predictor_rows)
                model_loads = len(predictor_rows)
            if inverse_table.is_file():
                with inverse_table.open(newline="") as handle:
                    inverse_seconds = sum(float(row["duration_sec"]) for row in csv.DictReader(handle))
            if job["arm"] == "resident":
                ready = wave / "resident_ready.json"
                if ready.is_file():
                    startup_seconds = float(json.loads(ready.read_text()).get("startup_seconds", 0.0))
                model_loads = 1
        rows.append({
            "engine": job["engine"], "arm": job["arm"],
            "wall_seconds": receipt.get("wall_seconds", ""),
            "predictor_request_seconds": predictor_seconds,
            "inverse_folding_seconds": inverse_seconds,
            "model_startup_seconds": startup_seconds,
            "model_load_count": model_loads,
            "designs_excluding_cycle00": designs,
            "expected_designs": campaign["trajectories"] * campaign["design_cycles"],
            "audit_errors": len(errors),
        })
        if errors:
            any_errors = True
            (output / "analysis").mkdir(parents=True, exist_ok=True)
            (output / "analysis" / f"{job['run_name']}_errors.txt").write_text("\n".join(errors) + "\n")
    analysis = output / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    with (analysis / "campaign_summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    atomic_json(analysis / "campaign_summary.json", rows)
    print(f"Wrote {analysis / 'campaign_summary.csv'}")
    if any_errors:
        die("one or more campaigns failed the output audit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "run", "analyze"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--msa", type=Path)
    parser.add_argument("--engines", help="comma-separated subset")
    parser.add_argument("--arms", help="comma-separated subset")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    {"plan": plan, "run": run, "analyze": analyze}[args.action](args)


if __name__ == "__main__":
    main()
