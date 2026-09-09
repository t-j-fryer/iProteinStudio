#!/usr/bin/env python3
"""Plan, queue, gate, and audit the matched aCbx secondary-prior campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CONFIG = json.loads((HERE / "config.json").read_text())
OUTPUT = ROOT / "Validation/output/secondary_structure_priors_v1"
RUNTIME = Path.home() / ".iproteinstudio"
STUDIOCTL = ROOT / "Sources/iProteinStudio/Resources/pipeline/mcp/studioctl.py"
PROJECT = "validation_secondary_structure_priors_v1"
TERMINAL = {"completed", "failed", "cancelled"}


def die(message: str) -> None:
    raise SystemExit(f"secondary_structure_priors_v1: {message}")


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


def git_state() -> dict[str, object]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    diff = subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=ROOT)
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, text=True
    ).splitlines()
    return {
        "commit": commit,
        "tracked_diff_sha256": hashlib.sha256(diff).hexdigest(),
        "untracked_files": {
            item: sha256(ROOT / item) for item in sorted(untracked)
            if (ROOT / item).is_file() and not item.startswith("Validation/output/")
        },
    }


def run_ctl(*arguments: str) -> dict:
    environment = dict(os.environ)
    environment["NANOHUNTER_ROOT"] = str(RUNTIME)
    completed = subprocess.run(
        [sys.executable, str(STUDIOCTL), *arguments], cwd=ROOT, env=environment,
        text=True, capture_output=True,
    )
    if completed.returncode != 0:
        die((completed.stderr or completed.stdout).strip())
    return json.loads(completed.stdout)


def ensure_project_link() -> None:
    destination = OUTPUT / "campaigns"
    destination.mkdir(parents=True, exist_ok=True)
    projects = RUNTIME / "projects"
    projects.mkdir(parents=True, exist_ok=True)
    link = projects / PROJECT
    if link.is_symlink():
        if link.resolve() != destination.resolve():
            die(f"managed project link points elsewhere: {link} -> {link.resolve()}")
    elif link.exists():
        die(f"managed project path exists and is not the validation link: {link}")
    else:
        link.symlink_to(destination, target_is_directory=True)


def validate_inputs() -> tuple[Path, Path]:
    template = RUNTIME / "examples/aCbx_bind.yaml"
    msa = RUNTIME / "msa_cache/example_acbx.a3m"
    runner = RUNTIME / "nanohunter_run.sh"
    helper = RUNTIME / "scripts/secondary_structure_control.py"
    for path in (template, msa, runner, helper):
        if not path.is_file():
            die(f"required managed artifact is missing: {path}")
    if sha256(template) != CONFIG["target"]["managed_template_sha256"]:
        die("managed aCbx template does not match the declared checksum")
    if sha256(msa) != CONFIG["target"]["msa_sha256"]:
        die("managed aCbx MSA does not match the declared checksum")
    if (RUNTIME / "mcp/MCP_VERSION").read_text().strip() != "8":
        die("managed MCP contract is not v8")
    return template, msa


def arguments_for(arm: dict, trajectories: int) -> list[str]:
    c = CONFIG["campaign"]
    controls = CONFIG["controls"]
    values = [
        "--workflow", "protein", "--predictor", "boltz",
        "--sequence-designer", "solublempnn",
        "--num-runs", str(trajectories), "--num-opt-cycles", str(c["design_cycles"]),
        "--iptm-threshold", f"{c['hit_threshold']:.2f}",
        "--post-predictor", "none", "--post-mode", "none",
        "--predictor-seed", str(c["predictor_seed"]),
        "--predictor-samples", str(c["predictor_samples"]),
        "--mpnn-seed", str(c["mpnn_seed"]),
        "--binder-random-seed", str(c["binder_seed"]),
        "--random-binder", "--binder-min-len", str(c["binder_length"]),
        "--binder-max-len", str(c["binder_length"]),
        "--target-msa-mode", "auto", "--target-msa-generator", "auto",
        "--require-target-msa",
    ]
    mode = arm["mode"]
    if mode != "none":
        values += ["--secondary-bias", mode, "--secondary-bias-scope", arm["scope"]]
    if mode == "antihelix":
        values += ["--anti-helix-strength", f"{controls['anti_helix_strength']:.2f}"]
    if mode == "beta":
        values += [
            "--beta-strength", f"{controls['beta_strength']:.2f}",
            "--beta-pattern-strength", f"{controls['beta_pattern_strength']:.2f}",
            "--turn-strength", f"{controls['turn_strength']:.2f}",
        ]
    return values


def prepare(phase: str) -> dict:
    ensure_project_link()
    template, msa = validate_inputs()
    if phase == "full":
        gate = OUTPUT / "smoke_passed.json"
        if not gate.is_file():
            die("full plans require a completed smoke gate")
    trajectories = CONFIG["campaign"][f"{phase}_trajectories"]
    records = {}
    for arm_name, arm in CONFIG["arms"].items():
        request = {
            "project": PROJECT,
            "run_name": f"{phase}__{arm_name}",
            "template_path": str(template),
            "arguments": arguments_for(arm, trajectories),
        }
        request_path = OUTPUT / "requests" / phase / f"{arm_name}.json"
        atomic_json(request_path, request)
        plan = run_ctl("plan-iterative", str(request_path))
        atomic_json(OUTPUT / "plans" / phase / f"{arm_name}.json", plan)
        records[arm_name] = {"id": plan["id"], "sha256": plan["sha256"]}
    manifest = {
        "schema": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "config": CONFIG,
        "git": git_state(),
        "runtime": {
            "root": str(RUNTIME), "runner_sha256": sha256(RUNTIME / "nanohunter_run.sh"),
            "secondary_helper_sha256": sha256(RUNTIME / "scripts/secondary_structure_control.py"),
            "mcp_contract": (RUNTIME / "mcp/MCP_VERSION").read_text().strip(),
            "target_msa": str(msa), "target_msa_sha256": sha256(msa),
            "template_sha256": sha256(template),
        },
        "plans": records,
    }
    atomic_json(OUTPUT / f"manifest_{phase}.json", manifest)
    return manifest


def start(phase: str) -> dict:
    manifest_path = OUTPUT / f"manifest_{phase}.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else prepare(phase)
    jobs = {}
    for arm_name, plan in manifest["plans"].items():
        state = run_ctl("start", plan["id"], plan["sha256"])
        jobs[arm_name] = {"id": state["id"], "status": state["status"]}
    atomic_json(OUTPUT / f"jobs_{phase}.json", jobs)
    return jobs


def status(phase: str) -> dict:
    jobs = json.loads((OUTPUT / f"jobs_{phase}.json").read_text())
    states = {arm: run_ctl("job-status", record["id"]) for arm, record in jobs.items()}
    atomic_json(OUTPUT / f"status_{phase}.json", states)
    return states


def cycle00_sequence(campaign: Path) -> str:
    metrics = campaign / "run_001/metrics_per_cycle.csv"
    if not metrics.is_file():
        die(f"smoke metrics missing: {metrics}")
    import csv
    with metrics.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if int(row["cycle"]) == 0:
                return row["binder_sequence"]
    die(f"cycle 00 row missing: {metrics}")


def gate_smoke() -> dict:
    states = status("smoke")
    incomplete = {arm: state["status"] for arm, state in states.items() if state["status"] != "completed"}
    if incomplete:
        die(f"smoke jobs are not all complete: {incomplete}")
    campaigns = OUTPUT / "campaigns"
    expected_cycles = CONFIG["campaign"]["design_cycles"] + 1
    audit = {}
    for arm_name, arm in CONFIG["arms"].items():
        campaign = campaigns / f"smoke__{arm_name}"
        structures = sorted(campaign.glob("run_001/cycle_*/pred_min/model_0.*"))
        if len(structures) != expected_cycles:
            die(f"{arm_name} has {len(structures)} structures; expected {expected_cycles}")
        plan = json.loads((campaign / "run_001/secondary_structure_plan.json").read_text())
        if plan["mode"] != arm["mode"]:
            die(f"{arm_name} plan mode mismatch")
        if arm["mode"] != "none" and plan["application_scope"] != arm["scope"]:
            die(f"{arm_name} plan scope mismatch")
        audit[arm_name] = {
            "cycle00_sequence": cycle00_sequence(campaign),
            "structures": len(structures), "plan_sha256": sha256(campaign / "run_001/secondary_structure_plan.json"),
        }
    for prefix in ("antihelix", "beta"):
        left = audit[f"{prefix}_seed_only"]["cycle00_sequence"]
        right = audit[f"{prefix}_seed_and_cycles"]["cycle00_sequence"]
        if left != right:
            die(f"matched {prefix} scopes produced different cycle-00 sequences")
    result = {"passed": True, "created_at": datetime.now(timezone.utc).isoformat(), "audit": audit}
    atomic_json(OUTPUT / "smoke_passed.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "start", "status", "gate-smoke"])
    parser.add_argument("--phase", choices=["smoke", "full"], default="smoke")
    args = parser.parse_args()
    if args.action == "prepare":
        value = prepare(args.phase)
    elif args.action == "start":
        value = start(args.phase)
    elif args.action == "status":
        value = status(args.phase)
    else:
        value = gate_smoke()
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
