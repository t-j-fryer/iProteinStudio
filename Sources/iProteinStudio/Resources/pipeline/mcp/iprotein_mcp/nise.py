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
    if set(arguments) - {"project", "request"}:
        raise StudioError("NISE plans accept only project and request.")
    project = validate_slug(arguments.get("project", ""))
    try:
        settings = contract().preflight(runtime_root(), arguments.get("request"))
    except ValueError as exc:
        raise StudioError(str(exc)) from exc
    output = project_root(project) / "nise_runs" / ("nise-" + secrets.token_hex(8))
    output.mkdir(parents=True)
    pipeline = Path(__file__).resolve().parents[2]
    snapshot = output / ".studio_runtime/pipeline"
    # This ships code only. Model files are resolved and fingerprinted in the
    # managed runtime. A job keeps this code across app/bridge updates.
    shutil.copytree(pipeline / "scripts", snapshot / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    atomic_json(output / "nise_config.json", {"output": str(output), "request": settings})
    return desktop_plan({"project": project, "workflow": "nise", "output": str(output)})
