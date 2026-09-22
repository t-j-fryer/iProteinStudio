from __future__ import annotations

import fcntl
from contextlib import contextmanager
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

from .common import StudioError, agent_root, atomic_json, file_digest, load_json, process_alive, project_uuid, runtime_root, stable_environment, tail_text, utc_now, validate_slug
from .plans import load_plan


TERMINAL = {"completed", "failed", "cancelled"}
_DETACHED: Dict[str, subprocess.Popen] = {}
_CANCEL_REQUESTED = False
_EXECUTION_FD = None
_RUNTIME_BINDINGS = {}
_CODE_SNAPSHOT = None
_PREPARED_RUNTIME_VIEW = None


@contextmanager
def registry_lock():
    # Desktop archive/delete and job registration use this same lock ordering.
    with (agent_root() / "registry.lock").open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def _cancelled(job_id: str) -> bool:
    return (_CANCEL_REQUESTED or (state_path(job_id).parent / "cancel.json").exists()
            or load_json(state_path(job_id)).get("status") in {"stopping", "cancelled"})



def state_path(job_id: str) -> Path:
    validate_slug(job_id, "job ID")
    return agent_root() / "jobs" / job_id / "state.json"


def load_state(job_id: str, refresh: bool = True) -> Dict[str, Any]:
    state = load_json(state_path(job_id))
    if refresh and state.get("status") in {"queued", "running", "stopping"} and state.get("pid") and not process_alive(state.get("pid")):
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
    active = [state for state in states if state.get("status") not in TERMINAL]
    history = [state for state in states if state.get("status") in TERMINAL]
    return active + history[: max(1, min(limit, 500))]


def _existing_for_plan(plan_id: str) -> Optional[Dict[str, Any]]:
    # Idempotence cannot depend on the UI's bounded recent-history window.
    for path in (agent_root() / "jobs").glob("*/state.json"):
        state = load_json(path)
        if state.get("plan_id") == plan_id:
            return load_state(path.parent.name)
    return None


def _spawn(job_id: str) -> Dict[str, Any]:
    directory = state_path(job_id).parent
    log_path = directory / "job.log"
    server_root = directory / "bridge"
    plan = load_json(directory / "plan.json")
    snapshot = plan.get("code_snapshot")
    source_bridge = Path(snapshot["path"]) / "mcp" if snapshot else Path(__file__).resolve().parents[1]
    if not server_root.exists():
        shutil.copytree(source_bridge, server_root,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    support = server_root / "runtime_support"
    if not support.exists():
        support.mkdir()
        source = Path(snapshot["path"]) / "scripts" if snapshot else Path(__file__).resolve().parents[2] / "scripts"
        for name in ("runtime_package.py", "runtime_transaction.py", "runtime_view.py", "engine_registry.py", "engine_registry.json"):
            if (source / name).is_file(): shutil.copy2(source / name, support / name)
    studioctl = server_root / "studioctl.py"
    control = plan.get("runtime_bindings", {}).get("control")
    worker_python = str(Path(control["path"]) / "python/bin/python3") if control else str(Path(sys.executable).resolve())
    with log_path.open("ab", buffering=0) as log:
        process = subprocess.Popen(
            [worker_python, str(studioctl), "_run-job", "--job-id", job_id],
            cwd=str(server_root),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
            env=stable_environment(),
        )
    state = load_json(state_path(job_id))
    state.update({"pid": process.pid, "process_group": process.pid, "worker_contract": 2, "updated_at": utc_now()})
    atomic_json(state_path(job_id), state)
    _DETACHED[job_id] = process
    return load_state(job_id)


def start_job(plan_id: str, plan_sha256: str) -> Dict[str, Any]:
    with registry_lock():
        return _start_job(plan_id, plan_sha256)


def _start_job(plan_id: str, plan_sha256: str) -> Dict[str, Any]:
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
        "display_name": plan.get("normalized_request", {}).get("display_name"),
        "resource_class": plan["resource_class"],
        "status": "queued",
        # Capability belongs to the frozen worker created for this job. Do not
        # upgrade it when resuming jobs that retain an older bridge snapshot.
        "cancellation_contract": 1,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "pid": None,
        "process_group": None,
        "stage": "queued",
        "message": "Waiting for the shared iProteinStudio execution lock.",
        "child_outputs": plan.get("normalized_request", {}).get("child_outputs"),
        "output_root": plan.get("normalized_request", {}).get("output") or plan.get("normalized_request", {}).get("campaign"),
    }
    atomic_json(state_path(job_id), state)
    return _spawn(job_id)


def cancel_job(job_id: str) -> Dict[str, Any]:
    state = load_state(job_id)
    if state.get("status") in TERMINAL:
        return state
    if state.get("worker_contract") != 2:
        raise StudioError("This job uses an older worker. Stop it through the client that launched it; Studio kept it running.")
    # Keep intent separate from status updates made concurrently by the worker.
    # A queued worker may not yet have installed its signal handlers.
    if state.get("cancellation_contract") == 1:
        atomic_json(state_path(job_id).parent / "cancel.json", {"requested_at": utc_now()})
    _update(job_id, status="stopping", stage="stopping", message="Stopping; waiting for all worker processes to exit.")
    # The worker keeps the execution lease until it has stopped and reaped its
    # child process group. Do not mark cancellation terminal at request time.
    ready_path = state_path(job_id).parent / "worker_ready.json"
    ready = load_json(ready_path).get("pid") if ready_path.exists() else None
    if state.get("pid") and (state.get("cancellation_contract") != 1 or ready == state["pid"]):
        try:
            os.kill(int(state["pid"]), signal.SIGTERM)
        except ProcessLookupError:
            pass
    return load_state(job_id, refresh=False)


def resume_job(job_id: str) -> Dict[str, Any]:
    with registry_lock():
        return _resume_job(job_id)


def _resume_job(job_id: str) -> Dict[str, Any]:
    state = load_state(job_id)
    if state.get("status") not in {"failed", "cancelled"}:
        return state
    if process_alive(state.get("pid")):
        raise StudioError("The previous worker is still alive; wait before resuming.")
    (state_path(job_id).parent / "cancel.json").unlink(missing_ok=True)
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
    root = Path(_CODE_SNAPSHOT["path"]) if _CODE_SNAPSHOT else runtime_root()
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
    from .runtime_bindings import environment
    env = {**env, **environment(_RUNTIME_BINDINGS)}
    # Give subprocesses private temporary storage. Some Apple frameworks use
    # their own system scratch directory independently of TMPDIR.
    scratch = state_path(job_id).parent / "tmp"
    scratch.mkdir(exist_ok=True)
    env["TMPDIR"] = str(scratch) + os.sep
    if _RUNTIME_BINDINGS or _CODE_SNAPSHOT:
        support = Path(__file__).resolve().parents[1] / "runtime_support"
        sys.path.insert(0, str(support))
        try:
            from runtime_view import build, rewrite, bind_configs
            root = runtime_root()
            destination = state_path(job_id).parent / "runtime_view"
            if _PREPARED_RUNTIME_VIEW:
                destination = Path(_PREPARED_RUNTIME_VIEW["path"])
                for name, key in (("assets.json", "assets_sha256"), ("view.json", "view_sha256")):
                    if file_digest(destination / name) != _PREPARED_RUNTIME_VIEW[key]:
                        raise StudioError("Retained job runtime inventory changed: " + name)
            view = build(root, destination, _RUNTIME_BINDINGS, _CODE_SNAPSHOT)
            command = bind_configs(rewrite(command, root, view), root, view, state_path(job_id).parent / "bound_configs")
            env = {key: rewrite([value], root, view)[0] for key, value in env.items()}
            cwd = Path(rewrite([str(cwd)], root, view)[0])
            env["NANOHUNTER_ROOT"] = str(view)
            if "antifold" in _RUNTIME_BINDINGS:
                # Upstream AntiFold locates its checkpoint beside imported
                # source. Import through the view so it uses retained job data.
                env["PYTHONPATH"] = str(view / "src/AntiFold")
        finally: sys.path.remove(str(support))
    log_path = state_path(job_id).parent / "pipeline.log"
    explicit_failure = None
    with log_path.open("a", encoding="utf-8") as log, log_path.open(encoding="utf-8") as reader:
        reader.seek(0, os.SEEK_END)
        process = subprocess.Popen(command, cwd=str(cwd), env=env,
                                   stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True,
                                   pass_fds=(() if _EXECUTION_FD is None else (_EXECUTION_FD,)))
        _update(job_id, child_pid=process.pid, child_process_group=process.pid)
        stopping_at = None
        killed = False
        while True:
            for line in reader.readlines():
                parts = line.rstrip("\n").split("|", 3)
                if len(parts) >= 4 and parts[0] in {"PBSTAGE", "RFSTAGE", "NHSTEP"} and stopping_at is None:
                    _update(job_id, stage=parts[1], message=parts[3])
                elif len(parts) >= 2 and parts[0] in {"PBFAIL", "RFFAIL", "NHFAIL", "PREPFAIL"}:
                    explicit_failure = "|".join(parts[1:])
            if _cancelled(job_id) and stopping_at is None:
                stopping_at = time.monotonic()
                try: os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError: pass
            if stopping_at is not None and not killed and time.monotonic() - stopping_at >= 3:
                # Even if caffeinate exited first, its resistant descendants
                # still belong to the isolated group. Keep the lease until here.
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                killed = True
            code = process.poll()
            if code is not None and (stopping_at is None or killed):
                break
            time.sleep(0.1)
        code = process.wait()
    if stopping_at is not None:
        return 130
    if code != 0:
        diagnostic = tail_text(log_path, 80)
        message = explicit_failure or f"Workflow command exited with status {code}."
        if not explicit_failure and diagnostic:
            message += f" Last output: {diagnostic[-1]}"
        _update(job_id, message=message, error="\n".join(diagnostic) if diagnostic else None)
    return code


def _execute_engine_batch(job_id: str, plan: Dict[str, Any]) -> int:
    """Run saved engine campaigns in order under the existing execution lease."""
    request = plan["normalized_request"]
    output = Path(request["output"])
    receipt = output / "engine_batch_progress.json"
    saved = load_json(receipt) if receipt.exists() else {"plan_sha256": plan["sha256"], "completed": {}}
    if saved.get("plan_sha256") != plan["sha256"] or not isinstance(saved.get("completed"), dict):
        raise StudioError("The engine batch checkpoint does not match its saved plan.")
    for index, child in enumerate(request["engine_campaigns"], 1):
        campaign = Path(child["output"])
        key = str(campaign)
        if key in saved["completed"]:
            files = saved["completed"][key]
            if not files:
                raise StudioError("The completed engine checkpoint has no result artifacts.")
            for name, digest in files.items():
                path = (campaign / name).resolve()
                if campaign.resolve() not in path.parents or not path.is_file() or file_digest(path) != digest:
                    raise StudioError("Completed engine outputs changed; restore the recorded files before resuming.")
            # Repair a quit between the atomic completion receipt and manifest update.
            manifest = dict(child["manifest"])
            manifest.update(state="completed", updatedAt=time.time() - 978_307_200)
            atomic_json(campaign / "studio_run.json", manifest)
            continue
        if _cancelled(job_id):
            return 130
        atomic_json(campaign / "studio_job.json", {"id": job_id, "plan_id": plan["id"], "sha256": plan["sha256"]})
        manifest = dict(child["manifest"])
        manifest.update(state="running", updatedAt=time.time() - 978_307_200)
        atomic_json(campaign / "studio_run.json", manifest)
        _update(job_id, active_output=key, engine_label=child["label"],
                engine_index=index, engine_count=len(request["engine_campaigns"]),
                stage="iterative-design", message=f"Engine {index} of {len(request['engine_campaigns'])}: {child['label']}")
        env = stable_environment(child.get("environment_overrides", {}))
        env["IPROTEINSTUDIO_PIPELINE_SNAPSHOT"] = child["pipeline_snapshot"]
        code = 0
        for step in child["steps"]:
            if _cancelled(job_id):
                code = 130
                break
            _update(job_id, stage=step["stage"], message=f"{child['label']}: {step['stage']}")
            code = _run_logged(job_id, step["command"], Path(step["cwd"]), env)
            if code:
                break
        manifest.update(state="completed" if code == 0 else ("stopped" if code == 130 else "failed"),
                        updatedAt=time.time() - 978_307_200)
        if code == 0:
            # Verify durable scientific artifacts before skipping an engine on resume.
            # Runtime snapshots and mutable broker/log records are excluded.
            artifacts = [p for p in campaign.rglob("*") if p.is_file()
                         and ".studio_runtime" not in p.relative_to(campaign).parts
                         and "inputs" not in p.relative_to(campaign).parts
                         and (p.suffix.lower() in {".csv", ".cif", ".pdb", ".fa", ".fasta"}
                              or p.name == "run_exit_code.txt")]
            nesso_receipt = campaign / "nesso_verification/completed.json"
            if nesso_receipt.is_file():
                nesso_root = nesso_receipt.parent.resolve()
                for relative, expected in load_json(nesso_receipt)["files"].items():
                    path = (nesso_root / relative).resolve()
                    if nesso_root not in path.parents or not path.is_file() or file_digest(path) != expected:
                        raise StudioError("NESSO verification artifact changed before engine completion.")
                    artifacts.append(path)
                artifacts.append(nesso_receipt)
            if not artifacts:
                raise StudioError(f"{child['label']} finished without durable result artifacts.")
            saved["completed"][key] = {str(p.relative_to(campaign)): file_digest(p) for p in artifacts}
            atomic_json(receipt, saved)
        atomic_json(campaign / "studio_run.json", manifest)
        if code:
            return code
    return 0


def _execute_desktop(job_id: str, plan: Dict[str, Any]) -> int:
    request = plan["normalized_request"]
    output = Path(request["output"])
    output.mkdir(parents=True, exist_ok=True)
    atomic_json(output / "studio_job.json", {"id": job_id, "plan_id": plan["id"], "sha256": plan["sha256"]})
    if request["workflow"] == "iterative_batch":
        return _execute_engine_batch(job_id, plan)
    env = stable_environment(request.get("environment_overrides", {}))
    if request.get("pipeline_snapshot"):
        env["IPROTEINSTUDIO_PIPELINE_SNAPSHOT"] = request["pipeline_snapshot"]
    code = 0
    preparation = output / "desktop_preparation.json"
    for step in request["steps"]:
        if step["stage"] == "prepare" and preparation.exists():
            saved = load_json(preparation)
            if saved.get("plan_sha256") != plan["sha256"] or not saved.get("files"):
                raise StudioError("The saved preparation checkpoint does not match this plan.")
            for name, digest in saved["files"].items():
                path = (output / name).resolve()
                if output.resolve() not in path.parents or not path.is_file() or file_digest(path) != digest:
                    raise StudioError("Prepared campaign inputs changed; restore the recorded files before resuming.")
            continue
        if _cancelled(job_id):
            return 130
        _update(job_id, stage=step["stage"], message="Running the saved " + request["workflow"] + " settings.")
        code = _run_logged(job_id, step["command"], Path(step["cwd"]), env)
        if code != 0:
            break
        if step["stage"] == "prepare":
            config = output / "config/campaign.json"
            if not config.is_file():
                raise StudioError("Preparation finished without saving its campaign settings.")
            files = [path for folder in ("config", "assets") for path in (output / folder).rglob("*") if path.is_file()]
            atomic_json(preparation, {"plan_sha256": plan["sha256"],
                                      "files": {str(path.relative_to(output)): file_digest(path) for path in files}})
    if code == 0 and request["workflow"] == "target_prepare":
        if not any(output.rglob("*.cif")):
            raise StudioError("Target prediction completed without a structure; the previous cache was kept.")
        atomic_json(output.parent / "current-result.json", {"directory": output.name})
    return code


def _finish_manifest(plan: Dict[str, Any], state: str) -> None:
    normalized = plan["normalized_request"]
    output = normalized.get("output") or normalized.get("campaign")
    if output:
        path = Path(output) / "studio_run.json"
        if path.is_file():
            manifest = load_json(path)
            manifest.update(state=state, updatedAt=time.time() - 978_307_200)
            atomic_json(path, manifest)


def _execute_prediction(job_id: str, plan: Dict[str, Any]) -> int:
    normalized = plan["normalized_request"]
    output = Path(normalized["output"])
    output.mkdir(parents=True, exist_ok=True)
    config_path = output / "prediction_config.json"
    atomic_json(config_path, normalized["config"])
    manifest = {"schema_version": 1, "workflow": "prediction", "plan_id": plan["id"], "plan_sha256": plan["sha256"], "created_at": utc_now(), "config": str(config_path), "provenance": plan["provenance"]}
    atomic_json(output / "studio_agent_run.json", manifest)
    command = ["/usr/bin/caffeinate", "-dimsu", sys.executable, str(runtime_root() / "rfd3_scripts" / "predict_batch.py"), "--config", str(config_path)]
    _update(job_id, output_root=str(output), stage="prediction", message="Running the durable prediction batch.")
    return _run_logged(job_id, command, runtime_root(), stable_environment())


def _execute_iterative(job_id: str, plan: Dict[str, Any]) -> int:
    normalized = plan["normalized_request"]
    campaign = Path(normalized["campaign"])
    campaign.mkdir(parents=True, exist_ok=True)
    snapshot = _snapshot_pipeline(campaign)
    template = Path(normalized["template_artifact"]["path"])
    shutil.copy2(template, campaign / "input_template.yaml")
    target_template = normalized.get("target_template_artifact")
    if target_template:
        source = Path(target_template["path"])
        destination = campaign / "inputs" / f"target_template{source.suffix.lower()}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
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
    preparation_code = _run_logged(job_id, [str(python), str(prepare), str(request_path)], root / "rfd3", stable_environment())
    if preparation_code != 0:
        return preparation_code
    config = None
    for line in tail_text(state_path(job_id).parent / "pipeline.log", 80):
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


def _gpu_storage_preflight(job_id: str) -> None:
    from .gpu_storage import check, failure_message
    result = check()
    atomic_json(state_path(job_id).parent / "gpu_storage.json", result)
    message = failure_message(result)
    if message:
        raise StudioError(message)


def run_worker(job_id: str) -> int:
    global _CANCEL_REQUESTED, _EXECUTION_FD, _RUNTIME_BINDINGS, _CODE_SNAPSHOT, _PREPARED_RUNTIME_VIEW
    _CANCEL_REQUESTED = False
    def request_stop(signum, frame):
        global _CANCEL_REQUESTED
        _CANCEL_REQUESTED = True
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    # Wait for the launching client to publish the worker identity.
    for _ in range(200):
        if int(load_json(state_path(job_id)).get("pid") or 0) == os.getpid():
            break
        time.sleep(0.01)
    atomic_json(state_path(job_id).parent / "worker_ready.json", {"pid": os.getpid()})
    plan = None
    try:
        recorded = load_json(state_path(job_id).parent / "plan.json")
        with (agent_root() / "execution.lock").open("a+") as lock:
            while True:
                if _cancelled(job_id):
                    _update(job_id, status="cancelled", stage="cancelled", message="Stopped before starting.", finished_at=utc_now())
                    return 130
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    time.sleep(0.2)
            _EXECUTION_FD = lock.fileno()
            # Recheck after waiting: scripts or inputs may have changed in queue.
            plan = load_plan(recorded["id"], recorded["sha256"])
            if plan != recorded:
                raise StudioError("The job's plan copy does not match the immutable plan registry.")
            from .runtime_bindings import verify as verify_runtime_bindings
            _RUNTIME_BINDINGS = plan.get("runtime_bindings", {})
            _CODE_SNAPSHOT = plan.get("code_snapshot")
            _PREPARED_RUNTIME_VIEW = plan.get("prepared_runtime_view")
            verify_runtime_bindings(_RUNTIME_BINDINGS)
            _update(job_id, status="running", started_at=utc_now(), stage="starting", message="Acquired the shared iProteinStudio execution lock.")
            kind = plan["kind"]
            if plan.get("resource_class") == "apple_gpu_exclusive":
                _update(job_id, stage="gpu-storage-check", message="Checking macOS GPU temporary storage.")
                _gpu_storage_preflight(job_id)
            if kind.startswith("desktop_"):
                code = _execute_desktop(job_id, plan)
            elif kind in {"prediction", "target_prepare"}:
                code = _execute_prediction(job_id, plan)
            elif kind == "iterative_design":
                code = _execute_iterative(job_id, plan)
            elif kind.startswith("rfd3_"):
                code = _execute_rfd3(job_id, plan)
            elif kind in {"engine_install", "engine_repair", "storage_minimise"}:
                code = _execute_admin(job_id, plan)
            else:
                raise StudioError(f"Unsupported plan kind: {kind}")
            if _cancelled(job_id):
                _finish_manifest(plan, "stopped")
                _update(job_id, status="cancelled", stage="cancelled", message="Stopped. Completed checkpoints were kept.", exit_code=130, finished_at=utc_now())
                return 130
            _finish_manifest(plan, "completed" if code == 0 else "failed")
            current = load_json(state_path(job_id))
            _update(job_id, status="completed" if code == 0 else "failed",
                    stage="done" if code == 0 else "failed",
                    message="Completed." if code == 0 else current.get("message", "The workflow failed."),
                    error=None if code == 0 else current.get("error"),
                    exit_code=code, finished_at=utc_now())
            return code
    except BaseException as exc:
        if plan:
            try: _finish_manifest(plan, "failed")
            except OSError: pass
        _update(job_id, status="failed", stage="failed", message=str(exc), error=traceback.format_exc(), finished_at=utc_now())
        return 1
