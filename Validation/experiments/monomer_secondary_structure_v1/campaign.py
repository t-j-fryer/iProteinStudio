#!/usr/bin/env python3
"""Declared target-free control screen, executed only through Studio plans/jobs."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / "Sources/iProteinStudio/Resources/pipeline"
RUNTIME = Path(os.environ.get("NANOHUNTER_ROOT", str(Path.home() / ".iproteinstudio"))).resolve()
OUTPUT = ROOT / "Validation/output/monomer_secondary_structure_v1"
PROJECT = "validation_monomer_secondary_structure_v1"
CONFIG = json.loads((HERE / "config.json").read_text())
STAGED = ("nanohunter_run.sh", "scripts/secondary_structure_control.py",
          "scripts/initialization_refinement.py", "scripts/initialization_assessment.py",
          "examples/monomer_initialization.yaml", "mcp/iprotein_mcp/plans.py",
          "mcp/schemas/iterative-design-v1.json")
TERMINAL = {"completed", "failed", "cancelled"}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".writing-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def now():
    return datetime.now(timezone.utc).isoformat()


def ctl(*args):
    result = subprocess.run([sys.executable, str(RUNTIME / "mcp/studioctl.py"), *map(str, args)],
                            env={**os.environ, "NANOHUNTER_ROOT": str(RUNTIME)},
                            capture_output=True, text=True, timeout=120)
    require(result.returncode == 0, result.stderr or result.stdout)
    return json.loads(result.stdout)


def emit(value):
    print(json.dumps(value, sort_keys=True, allow_nan=False), flush=True)


def stage_preview():
    return {"files": {name: {"before_sha256": sha(RUNTIME / name) if (RUNTIME / name).is_file() else None,
                             "after_sha256": sha(SOURCE / name)} for name in STAGED},
            "runtime": str(RUNTIME), "project": PROJECT, "output": str(OUTPUT)}


def fingerprint(path):
    stat = path.stat()
    return {"sha256": sha(path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def stage():
    receipt_path = OUTPUT / "stage_receipt.json"
    if receipt_path.exists():
        verify_stage()
        return read(receipt_path)
    (RUNTIME / "agent").mkdir(parents=True, exist_ok=True)
    with (RUNTIME / "agent/execution.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(all(job["status"] in TERMINAL for job in ctl("jobs")["jobs"]),
                "An active/queued job exists; staging requires an idle runtime")
        receipt = stage_preview()
        receipt["created_at"] = now()
        receipt["hardware"] = {key: subprocess.check_output(command, text=True).strip()
                               for key, command in {
                                   "cpu": ["sysctl", "-n", "machdep.cpu.brand_string"],
                                   "memory_bytes": ["sysctl", "-n", "hw.memsize"],
                                   "macos": ["sw_vers", "-productVersion"]}.items()}
        engine_paths = ["receipts/boltz.json", "models/boltz2/boltz2_conf.ckpt",
                        "src/LigandMPNN/model_params/solublempnn_v_48_020.pt",
                        "scripts/boltz_mps.py", "locks/boltz.txt", "locks/protenix.txt"]
        receipt["engine_files"] = {name: fingerprint(RUNTIME / name) for name in engine_paths}
        code_paths = sorted((RUNTIME / "src/LigandMPNN").glob("*.py"))
        code_paths += sorted((RUNTIME / "venvs/NanoHunter_boltz/lib").glob("python*/site-packages/boltz/**/*.py"))
        receipt["engine_code"] = {str(path.relative_to(RUNTIME)): fingerprint(path) for path in code_paths}
        probe = subprocess.run([str(RUNTIME / "venvs/NanoHunter_boltz/bin/python"), "-c",
                                "import json,torch; print(json.dumps({'torch':torch.__version__,'mps':torch.backends.mps.is_available()})); assert torch.backends.mps.is_available()"],
                               capture_output=True, text=True, check=True)
        receipt["mps_probe"] = json.loads(probe.stdout)
        for name in STAGED:
            destination = RUNTIME / name
            if destination.exists():
                backup = OUTPUT / "runtime_before" / name
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, backup)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".monomer-stage")
            shutil.copy2(SOURCE / name, temporary)
            os.replace(temporary, destination)
        project = RUNTIME / "projects" / PROJECT
        campaigns = OUTPUT / "campaigns"
        campaigns.mkdir(parents=True, exist_ok=True)
        if project.exists() or project.is_symlink():
            require(project.is_symlink() and project.resolve() == campaigns.resolve(), "Project path already belongs to another workspace")
        else:
            project.symlink_to(campaigns, target_is_directory=True)
        atomic(receipt_path, receipt)
        return receipt


def verify_stage(full_hashes=False):
    receipt = read(OUTPUT / "stage_receipt.json")
    for name, record in receipt["files"].items():
        require(sha(SOURCE / name) == sha(RUNTIME / name) == record["after_sha256"], f"Staged code changed: {name}")
    for name, record in {**receipt["engine_files"], **receipt["engine_code"]}.items():
        path = RUNTIME / name
        stat = path.stat()
        require(stat.st_size == record["bytes"] and stat.st_mtime_ns == record["mtime_ns"], f"Engine file changed: {name}")
        if full_hashes:
            require(sha(path) == record["sha256"], f"Engine checksum changed: {name}")
    return receipt


def arguments_for(arm, phase):
    c = CONFIG["campaign"]
    offset = 0 if phase == "pilot" else c["pilot_trajectories"]
    count = c["pilot_trajectories"] if phase == "pilot" else c["trajectories"] - offset
    args = ["--workflow", "protein", "--predictor", c["predictor"], "--sequence-designer", c["sequence_designer"],
            "--num-runs", str(count), "--num-opt-cycles", str(c["optimization_cycles"]), "--iptm-threshold", "0.7",
            "--post-predictor", "none", "--post-mode", "none", "--target-msa-mode", "off",
            "--predictor-seed", str(c["predictor_seed"]), "--predictor-samples", str(c["predictor_samples"]),
            "--mpnn-seed", str(c["mpnn_seed"] + 1000 * offset), "--binder-random-seed", str(c["binder_seed"] + offset),
            "--random-binder", "--binder-min-len", str(c["length"]), "--binder-max-len", str(c["length"]),
            "--binder-percent-x", str(arm["mask_percent"]), "--loopkill", str(arm["loopkill"]),
            "--ligand-temp-cycle1", str(arm["first_temperature"]), "--ligand-temp-other", str(arm["later_temperature"])]
    if arm["mode"] != "none":
        args += ["--secondary-bias", arm["mode"], "--secondary-bias-scope", arm["scope"]]
        if arm["mode"] in {"antihelix", "mixed"}:
            args += ["--anti-helix-strength", str(arm["anti_helix_strength"])]
        if arm["mode"] in {"beta", "mixed"}:
            for key, flag in (("beta_strength", "--beta-strength"), ("beta_pattern_strength", "--beta-pattern-strength"),
                              ("turn_strength", "--turn-strength")):
                args += [flag, str(arm[key])]
    args += ["--seed-sampling-order", arm["sampling_order"]]
    for key, flag in (("global_bias_first", "--mpnn-bias-aa-cycle1"), ("global_bias_later", "--mpnn-bias-aa-other")):
        if key in arm:
            args += [flag, arm[key]]
    if "inspection" in arm:
        for key, flag in (("max_attempts", "--initialization-max-attempts"),
                          ("min_uncertain_coil_length", "--initialization-min-coil-length"),
                          ("confidence_threshold", "--initialization-confidence-threshold")):
            args += [flag, str(arm["inspection"][key])]
    return args


def prepare():
    verify_stage()
    path = OUTPUT / "manifest.json"
    if path.exists():
        manifest = read(path)
        require(manifest["config"] == CONFIG and manifest["stage_receipt_sha256"] == sha(OUTPUT / "stage_receipt.json"),
                "The declared study changed; create a new campaign")
        for name, checksum in manifest["experiment_code"].items():
            require(sha(HERE / name) == checksum, f"Experiment code changed: {name}")
        return manifest
    require(CONFIG["campaign"]["length"] == 90 and CONFIG["campaign"]["trajectories"] == 10
            and CONFIG["campaign"]["optimization_cycles"] == 5, "Study cardinality differs from the user's request")
    manifest = {"schema": 1, "created_at": now(), "config": CONFIG,
                "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "git_diff_sha256": hashlib.sha256(subprocess.check_output(["git", "diff", "HEAD", "--binary"], cwd=ROOT)).hexdigest(),
                "stage_receipt_sha256": sha(OUTPUT / "stage_receipt.json"),
                "experiment_code": {p.name: sha(p) for p in HERE.glob("*.py")},
                "msa": {"policy": "empty", "target": None, "checksum": None},
                "template_sha256": sha(RUNTIME / "examples/monomer_initialization.yaml")}
    atomic(path, manifest)
    return manifest


def ensure_plan(phase, arm_name):
    prepare()
    plan_path = OUTPUT / "plans" / phase / f"{arm_name}.json"
    if plan_path.exists():
        plan = read(plan_path)
        for record in plan["provenance"]:
            require(sha(record["path"]) == record["sha256"], "Plan code identity changed")
        return plan
    if phase == "remaining":
        gate = read(OUTPUT / "audits/pilot" / f"{arm_name}.json")
        require(gate["operational_passed"], f"Pilot integrity gate failed for {arm_name}")
    request = {"project": PROJECT, "run_name": f"{phase}__{arm_name}", "monomer_control_benchmark": True,
               "template_path": str(RUNTIME / "examples/monomer_initialization.yaml"),
               "arguments": arguments_for(CONFIG["arms"][arm_name], phase)}
    request_path = OUTPUT / "requests" / phase / f"{arm_name}.json"
    atomic(request_path, request)
    plan = ctl("plan-iterative", request_path)
    actual = plan["normalized_request"]["arguments"]
    require(actual[actual.index("--design-scheduler") + 1] == "run", "Control arms must use the recorded run scheduler")
    require(actual[actual.index("--predictor") + 1] == "boltz", "Predictor changed")
    atomic(plan_path, plan)
    return plan


def compact(state):
    return {key: state.get(key) for key in ("id", "status", "stage", "message", "error", "output_root", "started_at", "finished_at")}


def run(only_arm=None, pilot_only=False):
    prepare()
    (OUTPUT / "controller.lock").touch(exist_ok=True)
    with (OUTPUT / "controller.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        arm_names = [only_arm] if only_arm else list(CONFIG["arms"])
        for phase in (["pilot"] if pilot_only else ["pilot", "remaining"]):
            for arm_name in arm_names:
                plan = ensure_plan(phase, arm_name)
                # start_job is idempotent for an immutable plan. Reconstructing
                # the controller never starts a second copy of the same job.
                state = ctl("start", plan["id"], plan["sha256"])
                atomic(OUTPUT / "jobs" / phase / f"{arm_name}.json", {"id": state["id"], "plan_id": plan["id"]})
                emit({"phase": phase, "arm": arm_name, **compact(state)})
                while state["status"] not in TERMINAL:
                    time.sleep(15)
                    state = ctl("job-status", state["id"])
                    atomic(OUTPUT / "status" / phase / f"{arm_name}.json", state)
                # Record actionable bridge diagnostics before classifying any
                # failure. Never tune settings in response to a failed fold.
                atomic(OUTPUT / "status" / phase / f"{arm_name}.json", state)
                emit({"phase": phase, "arm": arm_name, **compact(state)})
                result = subprocess.run([str(RUNTIME / "venvs/NanoHunter_protenix/bin/python"),
                                         str(HERE / "audit.py"), "--phase", phase, "--arm", arm_name],
                                        env={**os.environ, "NANOHUNTER_ROOT": str(RUNTIME),
                                             "MPLCONFIGDIR": str(OUTPUT / "matplotlib")}, capture_output=True, text=True)
                require(result.returncode == 0, result.stderr or result.stdout)
                emit(json.loads(result.stdout))
        if not pilot_only and not only_arm:
            verify_stage(full_hashes=True)
            subprocess.run([str(RUNTIME / "venvs/NanoHunter_protenix/bin/python"), str(HERE / "audit.py"), "--report"],
                           env={**os.environ, "MPLCONFIGDIR": str(OUTPUT / "matplotlib")}, check=True)


def status():
    result = []
    for path in sorted((OUTPUT / "jobs").glob("*/*.json")):
        state = ctl("job-status", read(path)["id"])
        result.append({"phase": path.parent.name, "arm": path.stem, **compact(state)})
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["stage-preview", "stage", "prepare", "run", "status"])
    p.add_argument("--arm", choices=list(CONFIG["arms"]))
    p.add_argument("--pilot-only", action="store_true")
    args = p.parse_args()
    if args.action == "run":
        run(args.arm, args.pilot_only)
    else:
        emit({"stage-preview": stage_preview, "stage": stage, "prepare": prepare, "status": status}[args.action]())


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        emit({"status": "blocked", "error": str(error), "time": now()})
        raise SystemExit(1)
