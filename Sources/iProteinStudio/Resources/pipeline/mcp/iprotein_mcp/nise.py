"""Typed ligand NISE planning; execution uses the shared desktop/broker adapter."""
import importlib.util
import secrets
import shutil
from pathlib import Path

from .common import StudioError, atomic_json, project_root, runtime_root, validate_slug


def contract():
    path = Path(__file__).resolve().parents[2] / "scripts/nise/contract.py"
    spec = importlib.util.spec_from_file_location("studio_nise_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def nise_plan(arguments):
    from .desktop import desktop_plan
    if set(arguments) - {"project", "request", "restart_from", "name"}:
        raise StudioError("NISE plans accept project, request and optional name/restart_from.")
    project = validate_slug(arguments.get("project", ""))
    try:
        settings = contract().preflight(runtime_root(), arguments.get("request"))
    except ValueError as exc:
        raise StudioError(str(exc)) from exc
    name = arguments.get("name")
    if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 120):
        raise StudioError("Run name must contain 1–120 characters.")
    output = project_root(project) / "nise_runs" / ("nise-" + secrets.token_hex(8))
    output.mkdir(parents=True)
    if name is not None:
        atomic_json(output / "studio_run_label.json", {"name": name.strip()})
    pipeline = Path(__file__).resolve().parents[2]
    snapshot = output / ".studio_runtime/pipeline"
    # This ships code only. Model files are resolved and fingerprinted in the
    # managed runtime. A job keeps this code across app/bridge updates.
    shutil.copytree(pipeline / "scripts", snapshot / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    atomic_json(output / "nise_config.json", {"output": str(output), "request": settings})
    if arguments.get("restart_from"):
        import subprocess, os
        source_name = validate_slug(arguments["restart_from"])
        source = project_root(project) / "nise_runs" / source_name
        if not source.is_dir() or source.resolve().parent != (project_root(project) / "nise_runs").resolve():
            raise StudioError("The initial-restart source must be a NISE campaign in this workspace.")
        result = subprocess.run([str(runtime_root() / "venvs/NanoHunter_boltz/bin/python"),
                                 str(snapshot / "scripts/nise/restart_initial.py"), str(source), str(output)],
                                capture_output=True, text=True,
                                env={**os.environ, "NANOHUNTER_ROOT": str(runtime_root())})
        if result.returncode:
            raise StudioError("Initial checkpoint import failed; preserved for diagnosis: " + result.stderr[-3000:])
    return desktop_plan({"project": project, "workflow": "nise", "output": str(output)})
