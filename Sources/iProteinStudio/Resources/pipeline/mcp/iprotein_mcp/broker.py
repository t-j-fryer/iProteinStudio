from __future__ import annotations

import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from .common import StudioError, agent_root, atomic_json, load_json, process_alive, project_uuid, runtime_root, stable_environment, tail_text, utc_now, validate_slug
from .plans import load_plan


TERMINAL = {"completed", "failed", "cancelled"}
_DETACHED: Dict[str, subprocess.Popen] = {}


def state_path(job_id: str) -> Path:
    validate_slug(job_id, "job ID")
    return agent_root() / "jobs" / job_id / "state.json"


def load_state(job_id: str, refresh: bool = True) -> Dict[str, Any]:
    state = load_json(state_path(job_id))
    if refresh and state.get("status") in {"queued", "running"} and not process_alive(state.get("pid")):
        state.update({"status": "failed", "finished_at": utc_now(), "error": "The durable worker stopped without recording completion."})
        atomic_json(state_path(job_id), state)
    directory = agent_root() / "jobs" / job_id
    worker_tail = tail_text(directory / "job.log", 80)
    pipeline_tail = tail_text(directory / "pipeline.log", 80)
    # The durable worker captures child output in pipeline.log. Returning only
    # job.log made real RFD3 failures look blank to MCP clients and encouraged
    # them to guess about stale directories, potentials, and unrelated fields.
    state["log_tail"] = pipeline_tail or worker_tail
    state["pipeline_log_tail"] = pipeline_tail
    state["worker_log_tail"] = worker_tail
    # Older bridge versions persisted only a generic exit message. Preserve the
    # record on disk, but make even those historical failures actionable when
    # viewed through the repaired server.
    if (state.get("status") == "failed" and pipeline_tail
            and str(state.get("message", "")).startswith("Workflow exited with status")):
        state["message"] = f"{state['message']} Last output: {pipeline_tail[-1]}"
    process = _DETACHED.get(job_id)
    if process is not None and process.poll() is not None:
        process.wait()
        _DETACHED.pop(job_id, None)
    return state


def list_jobs(limit: int = 100) -> List[Dict[str, Any]]:
    states = []
    for path in (agent_root() / "jobs").glob("*/state.json"):
        try:
            states.append(load_state(path.parent.name))
        except StudioError:
            continue
    states.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return states[: max(1, min(limit, 500))]


def _existing_for_plan(plan_id: str) -> Optional[Dict[str, Any]]:
    for state in list_jobs(500):
        if state.get("plan_id") == plan_id:
            return state
    return None


def _spawn(job_id: str) -> Dict[str, Any]:
    directory = state_path(job_id).parent
    log_path = directory / "job.log"
    server_root = Path(__file__).resolve().parents[1]
    studioctl = server_root / "studioctl.py"
    with log_path.open("ab", buffering=0) as log:
        process = subprocess.Popen(
            [sys.executable, str(studioctl), "_run-job", "--job-id", job_id],
            cwd=str(server_root),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
            env=stable_environment(),
        )
    state = load_json(state_path(job_id))
    state.update({"pid": process.pid, "process_group": process.pid, "updated_at": utc_now()})
    atomic_json(state_path(job_id), state)
    _DETACHED[job_id] = process
    return load_state(job_id)


def start_job(plan_id: str, plan_sha256: str) -> Dict[str, Any]:
    plan = load_plan(plan_id, plan_sha256)
    existing = _existing_for_plan(plan_id)
    if existing:
        return existing
    job_id = f"job-{plan['sha256'][:12]}"
    directory = agent_root() / "jobs" / job_id
    suffix = 1
    while directory.exists():
        suffix += 1
        job_id = f"job-{plan['sha256'][:12]}-{suffix}"
        directory = agent_root() / "jobs" / job_id
    directory.mkdir(parents=True)
    (directory / "plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    state = {
        "schema_version": 1,
        "id": job_id,
        "plan_id": plan_id,
        "plan_sha256": plan_sha256,
        "kind": plan["kind"],
        "project": plan["project"],
        "resource_class": plan["resource_class"],
        "status": "queued",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "pid": None,
        "process_group": None,
        "stage": "queued",
        "message": "Waiting for the shared iProteinStudio execution lock.",
        "output_root": plan.get("normalized_request", {}).get("output") or plan.get("normalized_request", {}).get("campaign"),
    }
    atomic_json(state_path(job_id), state)
    return _spawn(job_id)


def cancel_job(job_id: str) -> Dict[str, Any]:
    state = load_state(job_id)
    if state.get("status") in TERMINAL:
        return state
    state.update({"status": "cancelled", "stage": "cancelled", "message": "Cancellation requested.", "finished_at": utc_now(), "updated_at": utc_now()})
    atomic_json(state_path(job_id), state)
    process_group = state.get("process_group")
    if process_group:
        try:
            os.killpg(int(process_group), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, ValueError):
            pass
    return load_state(job_id, refresh=False)


def resume_job(job_id: str) -> Dict[str, Any]:
    state = load_state(job_id)
    if state.get("status") not in {"failed", "cancelled"}:
        return state
    state.update({"status": "queued", "stage": "queued", "message": "Waiting to resume from durable outputs.", "finished_at": None, "error": None, "updated_at": utc_now(), "pid": None, "process_group": None})
    atomic_json(state_path(job_id), state)
    return _spawn(job_id)


def wait_job(job_id: str, timeout_seconds: int = 30) -> Dict[str, Any]:
    deadline = time.monotonic() + max(0, min(timeout_seconds, 55))
    previous = None
    while True:
        state = load_state(job_id)
        signature = (state.get("status"), state.get("stage"), state.get("updated_at"))
        if state.get("status") in TERMINAL or (previous is not None and signature != previous) or time.monotonic() >= deadline:
            return state
        previous = signature
        time.sleep(0.5)


def _update(job_id: str, **changes: Any) -> Dict[str, Any]:
    state = load_json(state_path(job_id))
    state.update(changes)
    state["updated_at"] = utc_now()
    atomic_json(state_path(job_id), state)
    return state


def _snapshot_pipeline(campaign: Path) -> Path:
    root = runtime_root()
    destination = campaign / ".studio_runtime" / "pipeline"
    if destination.is_dir() and (destination / "nanohunter_run.sh").is_file():
        return destination
    temporary = destination.with_name(f".pipeline-{os.getpid()}.stage")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.mkdir()
    for name in ("nanohunter_run.sh", "scripts", "examples", "locks", "PIPELINE_VERSION", "THIRD_PARTY_NOTICES.md"):
        source = root / name
        if not source.exists():
            continue
        target = temporary / name
        if source.is_dir():
            shutil.copytree(source, target, symlinks=True)
        else:
            shutil.copy2(source, target)
    if not (temporary / "nanohunter_run.sh").is_file():
        shutil.rmtree(temporary, ignore_errors=True)
        raise StudioError("The staged iterative-design runner is missing.")
    os.replace(temporary, destination)
    return destination


def _run_logged(job_id: str, command: List[str], cwd: Path, env: Dict[str, str]) -> int:
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    _update(job_id, child_pid=process.pid)
    log_path = state_path(job_id).parent / "pipeline.log"
    explicit_failure = None
    with log_path.open("a", encoding="utf-8") as log:
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
            log.flush()
            stripped = line.rstrip("\n")
            parts = stripped.split("|", 3)
            if len(parts) >= 4 and parts[0] in {"PBSTAGE", "RFSTAGE", "NHSTEP"}:
                _update(job_id, stage=parts[1], message=parts[3])
            elif len(parts) >= 2 and parts[0] in {"PBFAIL", "RFFAIL", "NHFAIL"}:
                explicit_failure = "|".join(parts[1:])
                _update(job_id, message=explicit_failure)
    code = process.wait()
    if code != 0:
        diagnostic = tail_text(log_path, 80)
        last_line = diagnostic[-1] if diagnostic else ""
        message = explicit_failure or f"Workflow command exited with status {code}."
        if not explicit_failure and last_line:
            message += f" Last output: {last_line}"
        _update(job_id, message=message, error="\n".join(diagnostic) if diagnostic else None)
    return code


def _execute_prediction(job_id: str, plan: Dict[str, Any]) -> int:
    normalized = plan["normalized_request"]
    output = Path(normalized["output"])
    output.mkdir(parents=True, exist_ok=True)
    config_path = output / "prediction_config.json"
    atomic_json(config_path, normalized["config"])
    manifest = {"schema_version": 1, "workflow": "prediction", "plan_id": plan["id"], "plan_sha256": plan["sha256"], "created_at": utc_now(), "config": str(config_path), "provenance": plan["provenance"]}
    atomic_json(output / "studio_agent_run.json", manifest)
    command = ["/usr/bin/caffeinate", "-dimsu", "/usr/bin/python3", str(runtime_root() / "rfd3_scripts" / "predict_batch.py"), "--config", str(config_path)]
    _update(job_id, output_root=str(output), stage="prediction", message="Running the durable prediction batch.")
    return _run_logged(job_id, command, runtime_root(), stable_environment())


def _execute_iterative(job_id: str, plan: Dict[str, Any]) -> int:
    normalized = plan["normalized_request"]
    campaign = Path(normalized["campaign"])
    campaign.mkdir(parents=True, exist_ok=True)
    snapshot = _snapshot_pipeline(campaign)
    template = Path(normalized["template_artifact"]["path"])
    shutil.copy2(template, campaign / "input_template.yaml")
    arguments = list(normalized["arguments"])
    # Foundation's default Date Codable representation is seconds since
    # 2001-01-01, not ISO-8601. Match it so Activity can decode this exact file.
    foundation_now = time.time() - 978_307_200
    manifest = {
        "version": 1,
        "projectID": project_uuid(plan["project"]),
        "projectName": plan["project"],
        "workflow": "iterative",
        "runName": normalized["run_name"],
        "arguments": arguments,
        "environmentOverrides": normalized.get("environment_overrides", {}),
        "pipelineSnapshot": str(snapshot),
        "state": "running",
        "createdAt": foundation_now,
        "updatedAt": foundation_now,
    }
    atomic_json(campaign / "studio_run.json", manifest)
    env = stable_environment(normalized.get("environment_overrides", {}))
    env["IPROTEINSTUDIO_PIPELINE_SNAPSHOT"] = str(snapshot)
    command = ["/usr/bin/caffeinate", "-dimsu", str(snapshot / "nanohunter_run.sh")] + arguments
    _update(job_id, output_root=str(campaign), stage="iterative-design", message="Running with the recorded resident/cycle-wave scheduling policy.")
    code = _run_logged(job_id, command, snapshot, env)
    manifest["state"] = "completed" if code == 0 else "failed"
    manifest["updatedAt"] = time.time() - 978_307_200
    atomic_json(campaign / "studio_run.json", manifest)
    return code


def _execute_rfd3(job_id: str, plan: Dict[str, Any]) -> int:
    normalized = plan["normalized_request"]
    request = normalized["request"]
    campaign = Path(normalized["campaign"])
    (campaign / "config").mkdir(parents=True, exist_ok=True)
    request_path = campaign / "config" / "studio_request.json"
    atomic_json(request_path, request)
    root = runtime_root()
    python = root / "rfd3" / ".venv" / "bin" / "python"
    prepare = root / "rfd3_scripts" / "prepare_campaign.py"
    _update(job_id, output_root=str(campaign), stage="prepare", message="Validating and preparing the RFD3 campaign.")
    preparation = subprocess.run([str(python), str(prepare), str(request_path)], cwd=str(root / "rfd3"), env=stable_environment(), capture_output=True, text=True)
    with (state_path(job_id).parent / "pipeline.log").open("a", encoding="utf-8") as log:
        log.write(preparation.stdout)
        log.write(preparation.stderr)
    if preparation.returncode != 0:
        diagnostic = (preparation.stderr or preparation.stdout or "").strip()
        lines = diagnostic.splitlines()
        message = lines[-1] if lines else f"RFD3 preparation exited with status {preparation.returncode}."
        if message.startswith("PREPFAIL|"):
            message = message.split("|", 1)[1]
        _update(job_id, message=message, error=diagnostic[-16_000:])
        return preparation.returncode
    config = None
    for line in preparation.stdout.splitlines():
        if line.startswith("PREPOK|"):
            config = Path(line.split("|", 1)[1])
    if config is None or not config.is_file():
        raise StudioError("RFD3 preparation returned no durable campaign configuration.")
    if normalized["target_kind"] == "small_molecule":
        runner = root / "rfd3" / "scripts" / "run_rfd3_nise_campaign.py"
    else:
        runner = root / "rfd3_scripts" / "rfd3_protein_campaign.py"
    command = ["/usr/bin/caffeinate", "-dimsu", str(python), str(runner), "--config", str(config), "--resume"]
    _update(job_id, stage="rfd3", message="Running the resumable RFD3 campaign.")
    return _run_logged(job_id, command, root / "rfd3", stable_environment())


def _execute_admin(job_id: str, plan: Dict[str, Any]) -> int:
    root = runtime_root()
    command = ["/usr/bin/caffeinate", "-dimsu", "/bin/bash", str(root / "setup_pipeline.sh")] + plan["normalized_request"]["arguments"]
    _update(job_id, output_root=str(root), stage="admin", message="Running the explicitly approved managed-runtime operation.")
    return _run_logged(job_id, command, root, stable_environment())


def run_worker(job_id: str) -> int:
    # The parent learns our PID only after Popen returns. Do not race its first
    # state update and accidentally replace a running state with queued.
    for _ in range(200):
        try:
            if int(load_json(state_path(job_id)).get("pid") or 0) == os.getpid():
                break
        except (StudioError, ValueError):
            pass
        time.sleep(0.01)
    try:
        recorded_plan = load_json(state_path(job_id).parent / "plan.json")
        plan = load_plan(recorded_plan["id"], recorded_plan["sha256"])
        if plan != recorded_plan:
            raise StudioError("The job's plan copy does not match the immutable plan registry.")
        lock_path = agent_root() / "execution.lock"
        with lock_path.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            current = load_json(state_path(job_id))
            if current.get("status") == "cancelled":
                return 130
            _update(job_id, status="running", started_at=utc_now(), stage="starting", message="Acquired the shared iProteinStudio execution lock.")
            kind = plan["kind"]
            if kind in {"prediction", "target_prepare"}:
                code = _execute_prediction(job_id, plan)
            elif kind == "iterative_design":
                code = _execute_iterative(job_id, plan)
            elif kind.startswith("rfd3_"):
                code = _execute_rfd3(job_id, plan)
            elif kind in {"engine_install", "engine_repair", "storage_minimise"}:
                code = _execute_admin(job_id, plan)
            else:
                raise StudioError(f"Unsupported plan kind: {kind}")
            if load_json(state_path(job_id)).get("status") != "cancelled":
                current = load_json(state_path(job_id))
                if code == 0:
                    message = "Completed."
                    error = None
                else:
                    previous = str(current.get("message") or "")
                    generic = {
                        "", "Acquired the shared iProteinStudio execution lock.",
                        "Validating and preparing the RFD3 campaign.",
                        "Running the resumable RFD3 campaign.",
                    }
                    message = previous if previous not in generic else f"Workflow exited with status {code}."
                    diagnostic = tail_text(state_path(job_id).parent / "pipeline.log", 80)
                    error = "\n".join(diagnostic) if diagnostic else current.get("error")
                _update(job_id, status="completed" if code == 0 else "failed",
                        stage="done" if code == 0 else "failed", message=message,
                        error=error, exit_code=code, finished_at=utc_now())
            return code
    except BaseException as exc:
        current = load_json(state_path(job_id))
        if current.get("status") != "cancelled":
            _update(job_id, status="failed", stage="failed", message=str(exc), error=traceback.format_exc(), finished_at=utc_now())
        return 1
