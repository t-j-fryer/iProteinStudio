"""Recorded recovery of pending controls; rejected geometry remains a failure."""
import argparse
import csv
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import statistics as stats
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "monomer_secondary_structure_v1"))
import campaign as c
import audit as a

RECOVERY = c.OUTPUT / "recovery_v1"
ARM = "beta_sample_then_mask"
JOB = "job-d376ffe43b7b"


def restore():
    receipt = c.read(c.OUTPUT / "stage_receipt.json")
    with (c.RUNTIME / "agent/execution.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        c.require(all(j["status"] in c.TERMINAL for j in c.ctl("jobs")["jobs"]), "Runtime is active")
        for name, record in {**receipt["engine_files"], **receipt["engine_code"]}.items():
            c.require(c.sha(c.RUNTIME / name) == record["sha256"], f"Engine changed: {name}")
        for name, record in receipt["files"].items():
            c.require(c.sha(c.SOURCE / name) == record["after_sha256"], f"Original source changed: {name}")
        out = RECOVERY / "runtime_restore.json"
        c.require(not out.exists(), "Restoration already recorded; verify the existing receipt")
        before = {}
        for name, record in receipt["files"].items():
            path = c.RUNTIME / name
            before[name] = c.sha(path) if path.exists() else None
            if path.exists():
                backup = RECOVERY / "runtime_before" / name
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".monomer-recovery")
            shutil.copy2(c.SOURCE / name, temporary)
            os.replace(temporary, path)
        c.verify_stage(full_hashes=True)
        c.atomic(out, {"time": c.now(), "before_sha256": before,
                       "restored_stage_receipt_sha256": c.sha(c.OUTPUT / "stage_receipt.json"),
                       "reason": "Runtime scripts differed from the frozen campaign; restore exact original identities after verifying engines and idle lock."})
    return {"restored": True}


def verify_audit(value):
    c.require(value["manifest_sha256"] == c.sha(c.OUTPUT / "manifest.json"), "Manifest differs")
    for name, checksum in value["raw_sha256"].items():
        c.require(c.sha(c.OUTPUT / name) == checksum, f"Raw output changed: {name}")
    return value


def geometry_audit():
    """Port the existing audit checks; classify only the diagnosed rejection."""
    out = RECOVERY / "geometry_failure_audit.json"
    if out.exists():
        return verify_audit(c.read(out))
    root = c.OUTPUT / "campaigns" / f"remaining__{ARM}"
    state = c.ctl("job-status", JOB)
    c.require(state["status"] == "failed", "Diagnosed job is no longer failed")
    c.atomic(RECOVERY / "original_failed_status.json", state)
    pipeline_log = c.RUNTIME / "agent/jobs" / JOB / "pipeline.log"
    shutil.copy2(pipeline_log, RECOVERY / "original_pipeline.log")
    stage = c.read(c.OUTPUT / "stage_receipt.json")
    for name in ("nanohunter_run.sh", "scripts/secondary_structure_control.py", "scripts/initialization_assessment.py", "scripts/initialization_refinement.py"):
        c.require(c.sha(root / ".studio_runtime/pipeline" / name) == stage["files"][name]["after_sha256"], "Snapshot mismatch")
    validator = root / ".studio_runtime/pipeline/scripts/validate_prediction_geometry.py"
    spec = importlib.util.spec_from_file_location("frozen_geometry", validator)
    geometry = importlib.util.module_from_spec(spec); spec.loader.exec_module(geometry)
    plan = c.read(c.OUTPUT / "plans/remaining" / f"{ARM}.json")
    args = plan["normalized_request"]["arguments"]
    for flag, expected in (("--num-runs", "9"), ("--num-opt-cycles", "5"), ("--predictor", "boltz"), ("--design-scheduler", "run")):
        c.require(a.option(args, flag) == expected, f"Plan differs: {flag}")
    arm, config = c.CONFIG["arms"][ARM], c.CONFIG["campaign"]
    runs = sorted(p for p in root.glob("run_*") if p.is_dir())
    c.require([p.name for p in runs] == [f"run_{i:03d}" for i in range(1, 10)], "Trajectory cardinality differs")
    trajectories, structures, rejection = [], [], None
    for local, run in enumerate(runs, 1):
        trajectory = local + 1
        seq, seed_plan = a.generate_sequence(90, 90, arm["mask_percent"], "boltz", config["binder_seed"] + trajectory,
            arm["mode"], arm["anti_helix_strength"], arm["beta_strength"], arm["beta_pattern_strength"], arm["turn_strength"],
            arm["loopkill"], arm["scope"], arm["sampling_order"])
        c.require(seed_plan == c.read(run / "secondary_structure_plan.json"), "Seed plan does not replay")
        c.require(not (run / "initialization_refinement").exists(), "Unexpected refinement")
        rows = list(csv.DictReader((run / "metrics_per_cycle.csv").open()))
        exit_code = int((run / "run_exit_code.txt").read_text())
        summary = {"arm": ARM, "phase": "remaining", "trajectory": trajectory, "attempts": 1}
        if local == 1:
            c.require(exit_code != 0 and not rows, "Diagnosed failed trajectory changed")
            c.require(not (run / "cycle_01").exists(), "Rejected initialization entered optimization")
            raw = list((run / "cycle_00/boltz").glob("boltz_results_*/predictions/*/*_model_0.cif"))
            c.require(len(raw) == 1, "Rejected model cardinality differs")
            issues = geometry.validate(raw[0])
            c.require(len(issues) == 1 and "A:87-88 C-N=2.29 A (>2.2)" in issues[0], f"Unexpected geometry diagnosis: {issues}")
            # Finite coordinates/sequence may be recorded diagnostically, but
            # the invalid model never enters any composition endpoint.
            rejection = {"trajectory": trajectory, "diagnostic": issues,
                         "structure": str(raw[0].relative_to(c.OUTPUT)), "structure_sha256": c.sha(raw[0]),
                         "sequence": seq, "disposition": "retained_geometry_rejection_no_retry_no_replacement"}
            summary.update(outcome="geometry_rejected", completed_cycles=0, selected_attempt=None)
        else:
            c.require(exit_code == 0 and [int(r["cycle"]) for r in rows] == list(range(6)), "Completed trajectory cycles differ")
            measured = []
            for row in rows:
                cycle = int(row["cycle"]); directory = run / f"cycle_{cycle:02d}"
                models = [directory / "pred_min" / n for n in ("model_0.cif", "model_0.pdb") if (directory / "pred_min" / n).exists()]
                raw = [p for p in (directory / "boltz").glob("boltz_results_*/predictions/*/*") if p.suffix in {".cif", ".pdb"}]
                c.require(len(models) == len(raw) == 1 and bool(c.read(directory / "pred_min/confidence.json")), "Prediction cardinality/confidence differs")
                c.require(not geometry.validate(models[0]), "Invalid geometry in a completed cycle")
                sequence = row["binder_sequence"]
                c.require(len(sequence) == 90 and (sequence == seq if cycle == 0 else "X" not in sequence), "Sequence differs")
                result = {"arm": ARM, "phase": "remaining", "trajectory": trajectory, "cycle": cycle,
                          "sequence": sequence, "structure": str(models[0].relative_to(c.OUTPUT)), **a.evaluate(models[0], sequence)}
                structures.append(result); measured.append(result)
                if cycle < 5:
                    mpnn = directory / "ligandmpnn"
                    c.require(int((mpnn / "seed.txt").read_text()) == config["mpnn_seed"] + trajectory * 1000 + cycle, "MPNN seed differs")
                    c.require(not (mpnn / "secondary_structure_bias.json").exists(), "Initialization prior persisted")
            timing = list(csv.DictReader((run / "timing_run.csv").open()))
            c.require(len(timing) == 1 and float(timing[0]["duration_sec"]) > 0, "Missing timing")
            summary.update(outcome="completed", completed_cycles=5, selected_attempt=0,
                           wall_seconds_including_initialization=float(timing[0]["duration_sec"]))
            for metric in a.METRICS:
                summary["mean_" + metric] = stats.mean(r[metric] for r in measured if r["cycle"] > 0)
                summary["final_" + metric] = measured[-1][metric]
        trajectories.append(summary)
    svd = a.check_prediction_logs(root)
    raw_hashes = {str(p.relative_to(c.OUTPUT)): c.sha(p) for p in root.rglob("*") if p.is_file()
                  and ".studio_runtime" not in p.parts and "__pycache__" not in p.parts and "matplotlib" not in p.parts}
    result = {"schema": 1, "arm": ARM, "phase": "remaining", "job": c.compact(state),
              "trajectories": trajectories, "structures": structures, "inspections": [], "raw_sha256": raw_hashes,
              "manifest_sha256": c.sha(c.OUTPUT / "manifest.json"), "scientific_success": False,
              "completed_trajectory_audits": 8, "geometry_rejected": 1, "rejection": rejection,
              "geometry_validator_sha256": c.sha(validator), "audit_code_sha256": c.sha(Path(__file__)),
              "svd_fallback_log_lines": svd, "decision": "Preserve failed arm and continue independent declared conditions"}
    c.atomic(out, result)
    return result


def run():
    c.prepare()
    geometry_audit()
    names = list(c.CONFIG["arms"])
    pending = names[names.index(ARM) + 1:]
    decision = {"time": c.now(), "pending_arms": pending, "failed_job": JOB,
                "failed_trajectory": 2, "retained_failure": "geometry_rejected", "settings_changed": False,
                "source_sha256": c.sha(Path(__file__)), "analysis_sha256": c.sha(HERE / "analyze.py")}
    receipt = RECOVERY / "continuation.json"
    if receipt.exists():
        prior = c.read(receipt)
        c.require(all(prior[k] == decision[k] for k in decision if k != "time"), "Recovery controller changed")
    else:
        c.atomic(receipt, decision)
    for name in pending:
        c.run(only_arm=name)
    c.verify_stage(full_hashes=True)
    subprocess.run([str(c.RUNTIME / "venvs/NanoHunter_protenix/bin/python"), str(HERE / "analyze.py"), "--full"], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["restore", "audit", "run"])
    args = parser.parse_args()
    if args.action == "run":
        run()
    else:
        result = restore() if args.action == "restore" else geometry_audit()
        print(json.dumps({k: result[k] for k in ("restored", "completed_trajectory_audits", "geometry_rejected") if k in result}))
