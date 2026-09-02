from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict

from .common import StudioError, import_artifact, runtime_root, stable_environment


def inspect_target(arguments: Dict[str, Any]) -> Dict[str, Any]:
    kind = arguments.get("kind")
    if kind not in {"protein", "ligand"}:
        raise StudioError("kind must be protein or ligand.")
    root = runtime_root()
    python = root / "rfd3" / ".venv" / "bin" / "python"
    script = root / "rfd3_scripts" / "inspect_target.py"
    if not python.is_file() or not script.is_file():
        raise StudioError("RFdiffusion3 support is not installed or its target inspector is missing.")
    command = [str(python), str(script), "--kind", kind]
    artifact = None
    if arguments.get("structure"):
        artifact = import_artifact(arguments["structure"])
        command += ["--structure", artifact["path"]]
    if arguments.get("smiles"):
        command += ["--smiles", str(arguments["smiles"])]
    if arguments.get("resname"):
        command += ["--resname", str(arguments["resname"])]
    if arguments.get("chain"):
        command += ["--chain", str(arguments["chain"])]
    if arguments.get("chains"):
        command += ["--chains", ",".join(str(value) for value in arguments["chains"])]
    completed = subprocess.run(command, cwd=str(root / "rfd3"), env=stable_environment(), capture_output=True, text=True, timeout=120)
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise StudioError(f"Target inspection returned invalid output: {(completed.stderr or completed.stdout)[-1000:]}") from exc
    if completed.returncode != 0 or result.get("error"):
        raise StudioError(result.get("error") or "Target inspection failed.")
    if artifact:
        result["input_artifact"] = artifact
    return result
