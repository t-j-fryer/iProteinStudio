#!/usr/bin/env python3
"""Run a paired 0-vs-1 helix-kill benchmark against an explicit protein target."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
WORKING_SOURCE = ROOT / "Sources/iProteinStudio/Resources/pipeline"
SOURCE = ROOT / "Validation/output/binder_helix_strength_all_engines_v6/source"
RUNTIME = Path(os.environ.get("NANOHUNTER_ROOT", str(Path.home() / ".iproteinstudio"))).resolve()
OUTPUT = ROOT / "Validation/output/binder_helix_strength_all_engines_v6"
PROJECT = "validation_binder_helix_strength_all_engines_v6"
CONFIG = json.loads((HERE / "config.json").read_text())
MANAGED_INPUTS = RUNTIME / "validation_inputs" / CONFIG["name"]
STAGED = (
    "nanohunter_run.sh",
    "scripts/secondary_structure_control.py",
    "scripts/initialization_assessment.py",
    "scripts/validate_prediction_geometry.py",
    "scripts/boltz_mps.py",
    "scripts/intellifold_predict.py",
    "scripts/resident_predictor.py",
    "mcp/iprotein_mcp/plans.py",
    "mcp/schemas/iterative-design-v1.json",
    "mcp/iprotein_mcp/catalog.py",
    "mcp/iprotein_mcp/broker.py",
    "mcp/MCP_VERSION",
    "mcp/iprotein_mcp/__init__.py",
    "mcp/README.md",
)
TERMINAL = {"completed", "failed", "cancelled"}
AMINO_ACIDS = set("ACDEFGHIKLMNPQRSTVWY")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".writing-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_text(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".writing-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def now():
    return datetime.now(timezone.utc).isoformat()


def ctl(*args):
    result = subprocess.run(
        [sys.executable, str(RUNTIME / "mcp/studioctl.py"), *map(str, args)],
        env={**os.environ, "NANOHUNTER_ROOT": str(RUNTIME)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    require(result.returncode == 0, result.stderr or result.stdout)
    return json.loads(result.stdout)


def emit(value):
    print(json.dumps(value, sort_keys=True, allow_nan=False), flush=True)


def _ungap_alignment_sequence(text):
    return "".join(character for character in text if character not in ".-" and not character.islower()).upper()


def read_target_sequence(path):
    path = Path(path).expanduser().resolve()
    require(path.is_file(), f"Target sequence file does not exist: {path}")
    lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    require(lines, f"Target sequence file is empty: {path}")
    if any(line.startswith(">") for line in lines):
        headers = [index for index, line in enumerate(lines) if line.startswith(">")]
        require(headers == [0], "Target FASTA must contain exactly one record")
        lines = lines[1:]
    sequence = re.sub(r"\s+", "", "".join(lines)).upper()
    require(sequence, "Target sequence is empty")
    invalid = sorted(set(sequence) - AMINO_ACIDS)
    require(not invalid, f"Target sequence must use the 20 canonical amino acids; found: {''.join(invalid)}")
    require(len(sequence) >= 5, "Target sequence must contain at least five residues")
    return sequence


def alignment_query(path):
    path = Path(path).expanduser().resolve()
    require(path.is_file(), f"Target MSA does not exist: {path}")
    lines = path.read_text().splitlines()
    stockholm = next((line.strip() for line in lines if line.strip()), "").startswith("# STOCKHOLM")
    if stockholm:
        records, order = {}, []
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or line == "//":
                continue
            fields = line.split()
            require(len(fields) >= 2, f"Malformed Stockholm sequence row: {raw}")
            name, segment = fields[0], fields[1]
            if name not in records:
                records[name] = []
                order.append(name)
            records[name].append(segment)
        require(order, "Stockholm alignment contains no sequence records")
        query = _ungap_alignment_sequence("".join(records[order[0]]))
        count = len(order)
        kind = "stockholm"
        suffix = ".sto"
    else:
        records, current = [], None
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                current = []
                records.append(current)
            else:
                require(current is not None, "A3M sequence data appears before the first FASTA header")
                current.append(line)
        require(records and all(records), "A3M alignment contains an empty or missing sequence record")
        query = _ungap_alignment_sequence("".join(records[0]))
        count = len(records)
        kind = "a3m"
        suffix = ".a3m"
    require(query, "Target MSA query is empty after removing gaps/insertions")
    return {"query": query, "records": count, "format": kind, "suffix": suffix, "path": path}


def validate_target(target_name, sequence_path, msa_path):
    name = str(target_name or "").strip()
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", name) is not None,
            "Target name must be a 1-80 character filesystem-safe slug")
    sequence_file = Path(sequence_path).expanduser().resolve()
    msa_file = Path(msa_path).expanduser().resolve()
    sequence = read_target_sequence(sequence_file)
    alignment = alignment_query(msa_file)
    require(alignment["query"] == sequence,
            f"Target MSA query does not exactly match the supplied sequence ({len(alignment['query'])} vs {len(sequence)} residues)")
    require(alignment["records"] >= 2, "Target MSA must contain at least two sequence records")
    return {
        "name": name,
        "sequence": sequence,
        "length": len(sequence),
        "sequence_source": str(sequence_file),
        "sequence_source_sha256": sha(sequence_file),
        "msa_source": str(msa_file),
        "msa_sha256": sha(msa_file),
        "msa_format": alignment["format"],
        "msa_records": alignment["records"],
        "msa_suffix": alignment["suffix"],
        "chain": "B",
    }


def fingerprint(path):
    stat = path.stat()
    return {"sha256": sha(path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def stage_preview():
    return {
        "files": {
            name: {
                "before_sha256": sha(RUNTIME / name) if (RUNTIME / name).is_file() else None,
                "after_sha256": sha(WORKING_SOURCE / name),
            }
            for name in STAGED
        },
        "runtime": str(RUNTIME),
        "project": PROJECT,
        "output": str(OUTPUT),
    }


def stage():
    for name in STAGED:
        require((WORKING_SOURCE / name).is_file(), f"Required pipeline source is missing: {name}")
        destination = SOURCE / name
        if destination.exists():
            require(sha(destination) == sha(WORKING_SOURCE / name),
                    f"A partial stage contains different source bytes: {name}")
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(WORKING_SOURCE / name, destination)
    receipt_path = OUTPUT / "stage_receipt.json"
    if receipt_path.exists():
        return verify_stage(full_hashes=True)
    (RUNTIME / "agent").mkdir(parents=True, exist_ok=True)
    with (RUNTIME / "agent/execution.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(all(job["status"] in TERMINAL for job in ctl("jobs")["jobs"]),
                "An active/queued job exists; staging requires an idle runtime")
        receipt = stage_preview()
        receipt["created_at"] = now()
        receipt["hardware"] = {
            key: subprocess.check_output(command, text=True).strip()
            for key, command in {
                "cpu": ["sysctl", "-n", "machdep.cpu.brand_string"],
                "memory_bytes": ["sysctl", "-n", "hw.memsize"],
                "macos": ["sw_vers", "-productVersion"],
            }.items()
        }
        engine_paths = [
            path
            for folder in ("models", "receipts", "locks")
            for path in (RUNTIME / folder).rglob("*")
            if path.is_file()
        ]
        engine_paths.append(RUNTIME / "src/LigandMPNN/model_params/solublempnn_v_48_020.pt")
        require(all(path.is_file() for path in engine_paths), "Required engine inventory is incomplete")
        receipt["engine_files"] = {str(path.relative_to(RUNTIME)): fingerprint(path) for path in engine_paths}
        code_paths = sorted((RUNTIME / "src").rglob("*.py"))
        code_paths += sorted((RUNTIME / "scripts").rglob("*.py"))
        code_paths += sorted((RUNTIME / "venvs").glob("*/lib/python*/site-packages/boltz/**/*.py"))
        receipt["engine_code"] = {
            str(path.relative_to(RUNTIME)): fingerprint(path)
            for path in code_paths if str(path.relative_to(RUNTIME)) not in STAGED
        }
        receipt["detect"] = ctl("detect")
        required_engines = {
            "boltz", "mpnn", "intellifold", "intellifold_full", "protenix",
            "protenix_v2", "protenix_mini", "protenix_constraint", "openfold3",
        }
        unavailable = {
            name: receipt["detect"]["engines"].get(name)
            for name in required_engines
            if receipt["detect"]["engines"].get(name, {}).get("state") != "ok"
        }
        require(not unavailable, f"Required benchmark engines are unavailable: {unavailable}")
        probe = subprocess.run(
            [str(RUNTIME / "venvs/NanoHunter_boltz/bin/python"), "-c",
             "import json,torch; print(json.dumps({'torch':torch.__version__,'mps':torch.backends.mps.is_available()})); assert torch.backends.mps.is_available()"],
            capture_output=True, text=True, check=True,
        )
        receipt["mps_probe"] = json.loads(probe.stdout)
        for name in STAGED:
            destination = RUNTIME / name
            if destination.exists():
                backup = OUTPUT / "runtime_before" / name
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, backup)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".binder-helix-stage")
            shutil.copy2(SOURCE / name, temporary)
            os.replace(temporary, destination)
        campaigns = OUTPUT / "campaigns"
        campaigns.mkdir(parents=True, exist_ok=True)
        project = RUNTIME / "projects" / PROJECT
        if project.exists() or project.is_symlink():
            require(project.is_symlink() and project.resolve() == campaigns.resolve(),
                    "Project path already belongs to another workspace")
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


def _freeze_file(source, destination):
    if destination.exists():
        require(sha(source) == sha(destination), f"Frozen input differs: {destination}")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def prepare(target_name=None, sequence_path=None, msa_path=None):
    verify_stage()
    manifest_path = OUTPUT / "manifest.json"
    if manifest_path.exists():
        manifest = read(manifest_path)
        require(manifest["config"] == CONFIG, "The declared study configuration changed")
        require(manifest["stage_receipt_sha256"] == sha(OUTPUT / "stage_receipt.json"), "Stage receipt identity changed")
        for name, checksum in manifest["experiment_code"].items():
            require(sha(HERE / name) == checksum, f"Experiment code changed: {name}")
        target = manifest["target"]
        require(sha(OUTPUT / target["sequence_file"]) == target["sequence_sha256"], "Frozen target sequence changed")
        require(sha(OUTPUT / target["msa_file"]) == target["msa_sha256"], "Frozen target MSA changed")
        require(sha(RUNTIME / target["managed_msa_file"]) == target["msa_sha256"], "Managed target MSA changed")
        require(sha(Path(manifest["template"]["path"])) == manifest["template"]["sha256"], "Managed input template changed")
        if target_name or sequence_path or msa_path:
            require(target_name and sequence_path and msa_path, "Provide all three target arguments or none")
            supplied = validate_target(target_name, sequence_path, msa_path)
            require(supplied["name"] == target["name"] and supplied["sequence"] == target["sequence"]
                    and supplied["msa_sha256"] == target["msa_sha256"],
                    "Supplied target differs from the immutable prepared target")
        return manifest
    require(target_name and sequence_path and msa_path,
            "First prepare requires --target-name, --target-sequence-file, and --target-msa")
    target = validate_target(target_name, sequence_path, msa_path)
    frozen_sequence = OUTPUT / "inputs/target.fasta"
    frozen_msa = OUTPUT / f"inputs/target{target['msa_suffix']}"
    managed_msa = MANAGED_INPUTS / f"target{target['msa_suffix']}"
    sequence_text = f">{target['name']}\n{target['sequence']}\n"
    if frozen_sequence.exists():
        require(frozen_sequence.read_text() == sequence_text, "A partial prepare contains a different target sequence")
    else:
        atomic_text(frozen_sequence, sequence_text)
    _freeze_file(Path(target["msa_source"]), frozen_msa)
    _freeze_file(Path(target["msa_source"]), managed_msa)
    target_record = {
        key: target[key]
        for key in ("name", "sequence", "length", "chain", "msa_format", "msa_records", "sequence_source_sha256")
    }
    target_record.update({
        "sequence_file": str(frozen_sequence.relative_to(OUTPUT)),
        "sequence_sha256": sha(frozen_sequence),
        "msa_file": str(frozen_msa.relative_to(OUTPUT)),
        "msa_sha256": sha(frozen_msa),
        "managed_msa_file": str(managed_msa.relative_to(RUNTIME)),
    })
    template = MANAGED_INPUTS / "input_template.yaml"
    template_copy = OUTPUT / "inputs/input_template.yaml"
    msa_yaml = json.dumps(str(managed_msa))
    template_text = ("sequences:\n"
                     f"  - protein:\n      id: A\n      sequence: {'X' * CONFIG['campaign']['length']}\n      msa: empty\n"
                     f"  - protein:\n      id: B\n      sequence: {target['sequence']}\n      msa: {msa_yaml}\n"
                     "version: 1\n")
    if template.exists():
        require(template.read_text() == template_text, "A partial prepare contains a different managed template")
    else:
        atomic_text(template, template_text)
    if template_copy.exists():
        require(template_copy.read_text() == template_text, "A partial prepare contains a different portable template copy")
    else:
        atomic_text(template_copy, template_text)
    manifest = {
        "schema": 1,
        "created_at": now(),
        "config": CONFIG,
        "target": target_record,
        "template": {"path": str(template), "portable_copy": str(template_copy.relative_to(OUTPUT)),
                     "sha256": sha(template)},
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "git_diff_sha256": hashlib.sha256(subprocess.check_output(["git", "diff", "HEAD", "--binary"], cwd=ROOT)).hexdigest(),
        "stage_receipt_sha256": sha(OUTPUT / "stage_receipt.json"),
        "experiment_code": {path.name: sha(path) for path in HERE.glob("*.py")},
        "msa": {"policy": "required-exact-supplied", "checksum": sha(frozen_msa), "records": target["msa_records"]},
    }
    atomic(manifest_path, manifest)
    return manifest


def arguments_for(arm, phase):
    campaign = CONFIG["campaign"]
    offset = 0 if phase == "pilot" else campaign["pilot_trajectories"]
    count = campaign["pilot_trajectories"] if phase == "pilot" else campaign["trajectories"] - offset
    args = [
        "--workflow", "protein", "--predictor", arm["predictor"],
        "--sequence-designer", campaign["sequence_designer"],
        "--num-runs", str(count), "--num-opt-cycles", str(campaign["optimization_cycles"]),
        "--iptm-threshold", str(campaign["hit_threshold"]),
        "--post-predictor", "none", "--post-mode", "none",
        "--target-msa-mode", "auto", "--require-target-msa",
        "--predictor-seed", str(campaign["predictor_seed"]),
        "--predictor-samples", str(campaign["predictor_samples"]),
        "--mpnn-seed", str(campaign["mpnn_seed"] + 1000 * offset),
        "--binder-random-seed", str(campaign["binder_seed"] + offset),
        "--random-binder", "--binder-min-len", str(campaign["length"]),
        "--binder-max-len", str(campaign["length"]), "--binder-percent-x", "50",
        "--negative-helix-constant", str(arm["strength"]),
        "--ligand-temp-cycle1", "0.3", "--ligand-temp-other", "0.1",
    ]
    if arm["model"]:
        args += ["--model", arm["model"]]
    return args


def ensure_plan(phase, arm_name):
    manifest = prepare()
    plan_path = OUTPUT / "plans" / phase / f"{arm_name}.json"
    if plan_path.exists():
        plan = read(plan_path)
        for record in plan["provenance"]:
            require(sha(record["path"]) == record["sha256"], "Plan code identity changed")
        return plan
    if phase == "remaining":
        gate = read(OUTPUT / "audits/pilot" / f"{arm_name}.json")
        require(gate["operational_passed"], f"Pilot integrity gate failed for {arm_name}")
    template = Path(manifest["template"]["path"])
    require(sha(template) == manifest["template"]["sha256"], "Frozen input template changed")
    request = {
        "project": PROJECT,
        "run_name": f"{phase}__{arm_name}",
        "template_path": str(template),
        "arguments": arguments_for(CONFIG["arms"][arm_name], phase),
    }
    request_path = OUTPUT / "requests" / phase / f"{arm_name}.json"
    atomic(request_path, request)
    plan = ctl("plan-iterative", request_path)
    actual = plan["normalized_request"]["arguments"]
    require(actual[actual.index("--predictor") + 1] == CONFIG["arms"][arm_name]["predictor"], "Predictor changed")
    require("--require-target-msa" in actual, "Required target-MSA policy was lost")
    atomic(plan_path, plan)
    return plan


def plan(only_arm=None, pilot_only=False):
    prepare()
    arm_names = [only_arm] if only_arm else list(CONFIG["arms"])
    work = [("pilot", arm_name) for arm_name in arm_names]
    if not pilot_only:
        work += [("remaining", arm_name) for arm_name in arm_names]
    results = []
    for phase, arm_name in work:
        value = ensure_plan(phase, arm_name)
        arguments = value["normalized_request"]["arguments"]
        results.append({
            "phase": phase,
            "arm": arm_name,
            "plan_id": value["id"],
            "plan_sha256": value["sha256"],
            "predictor": arguments[arguments.index("--predictor") + 1],
            "scheduler": arguments[arguments.index("--design-scheduler") + 1],
            "command_preview": value["command_preview"],
        })
    return {"plans": results, "count": len(results)}


def compact(state):
    return {key: state.get(key) for key in ("id", "status", "stage", "message", "error", "pipeline_log_tail", "output_root", "started_at", "finished_at")}


def _audit(phase, arm_name):
    result = subprocess.run(
        [str(RUNTIME / "venvs/NanoHunter_protenix/bin/python"), str(HERE / "audit.py"), "--phase", phase, "--arm", arm_name],
        env={**os.environ, "NANOHUNTER_ROOT": str(RUNTIME), "MPLCONFIGDIR": str(OUTPUT / "matplotlib")},
        capture_output=True,
        text=True,
    )
    require(result.returncode == 0, result.stderr or result.stdout)
    return json.loads(result.stdout)


def run(only_arm=None, pilot_only=False):
    prepare()
    (OUTPUT / "controller.lock").touch(exist_ok=True)
    with (OUTPUT / "controller.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        arm_names = [only_arm] if only_arm else list(CONFIG["arms"])
        work = [("pilot", arm_name) for arm_name in arm_names]
        if not pilot_only:
            work += [("remaining", arm_name) for arm_name in arm_names]
        for phase, arm_name in work:
            audit_path = OUTPUT / "audits" / phase / f"{arm_name}.json"
            if audit_path.exists():
                outcome = _audit(phase, arm_name)
                emit(outcome)
                continue
            plan = ensure_plan(phase, arm_name)
            state = ctl("start", plan["id"], plan["sha256"])
            atomic(OUTPUT / "jobs" / phase / f"{arm_name}.json", {"id": state["id"], "plan_id": plan["id"]})
            emit({"phase": phase, "arm": arm_name, **compact(state)})
            while state["status"] not in TERMINAL:
                time.sleep(15)
                state = ctl("job-status", state["id"])
                atomic(OUTPUT / "status" / phase / f"{arm_name}.json", state)
            atomic(OUTPUT / "status" / phase / f"{arm_name}.json", state)
            emit({"phase": phase, "arm": arm_name, **compact(state)})
            outcome = _audit(phase, arm_name)
            emit(outcome)
            atomic(OUTPUT / "analysis_status.json", {
                "complete": False, "status": "running", "last_audited": outcome,
                "time": now(), "geometry_policy": "record_only",
            })
        if not pilot_only and not only_arm:
            verify_stage(full_hashes=True)
            result = subprocess.run(
                [str(RUNTIME / "venvs/NanoHunter_protenix/bin/python"), str(HERE / "audit.py"), "--report"],
                env={**os.environ, "MPLCONFIGDIR": str(OUTPUT / "matplotlib")},
                check=True,
                capture_output=True,
                text=True,
            )
            atomic(OUTPUT / "analysis_status.json", {"complete": True, "status": "complete", "time": now(), "report": json.loads(result.stdout)})


def status():
    result = []
    for path in sorted((OUTPUT / "jobs").glob("*/*.json")):
        state = ctl("job-status", read(path)["id"])
        result.append({"phase": path.parent.name, "arm": path.stem, **compact(state)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["validate-target", "stage-preview", "stage", "prepare", "plan", "run", "status"])
    parser.add_argument("--target-name")
    parser.add_argument("--target-sequence-file", type=Path)
    parser.add_argument("--target-msa", type=Path)
    parser.add_argument("--arm", choices=list(CONFIG["arms"]))
    parser.add_argument("--pilot-only", action="store_true")
    args = parser.parse_args()
    if args.action == "validate-target":
        require(args.target_name and args.target_sequence_file and args.target_msa,
                "validate-target requires all three target arguments")
        emit(validate_target(args.target_name, args.target_sequence_file, args.target_msa))
    elif args.action == "prepare":
        emit(prepare(args.target_name, args.target_sequence_file, args.target_msa))
    elif args.action == "plan":
        emit(plan(args.arm, args.pilot_only))
    elif args.action == "run":
        run(args.arm, args.pilot_only)
    elif args.action == "stage":
        receipt = stage()
        emit({"created_at": receipt["created_at"], "runtime": receipt["runtime"],
              "project": receipt["project"], "mps_probe": receipt["mps_probe"],
              "stage_receipt_sha256": sha(OUTPUT / "stage_receipt.json")})
    else:
        emit({"stage-preview": stage_preview, "status": status}[args.action]())


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        result = {"complete": False, "status": "blocked", "error": str(error), "time": now()}
        if OUTPUT.exists():
            atomic(OUTPUT / "analysis_status.json", result)
        emit(result)
        raise SystemExit(1)


