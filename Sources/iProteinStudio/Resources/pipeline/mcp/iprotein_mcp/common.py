from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SAFE_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class StudioError(RuntimeError):
    """A user-actionable, fail-closed bridge error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def runtime_root() -> Path:
    configured = os.environ.get("NANOHUNTER_ROOT") or os.environ.get(
        "IPROTEINSTUDIO_TEST_SUPPORT_ROOT"
    )
    return Path(configured).expanduser().resolve() if configured else (Path.home() / ".iproteinstudio").resolve()


def bridge_root() -> Path:
    return Path(__file__).resolve().parents[1]


def agent_root() -> Path:
    configured = os.environ.get("IPROTEINSTUDIO_AGENT_ROOT")
    root = Path(configured).expanduser().resolve() if configured else runtime_root() / "agent"
    for child in (root, root / "plans", root / "jobs", root / "audit"):
        child.mkdir(parents=True, exist_ok=True)
    return root


def projects_root() -> Path:
    root = runtime_root() / "projects"
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_slug(value: str, label: str = "project") -> str:
    value = str(value).strip()
    if not SAFE_SLUG.fullmatch(value):
        raise StudioError(
            f"{label} must start with a letter or number and contain only letters, numbers, '.', '_' or '-'."
        )
    return value


def project_root(project: str, create: bool = False) -> Path:
    path = projects_root() / validate_slug(project)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    elif not path.is_dir():
        raise StudioError(f"Unknown project '{project}'. Create it in iProteinStudio first.")
    return path.resolve()


def project_uuid(project: str) -> str:
    """Return the UUID persisted by the Swift app, with a stable fallback for CLI-only projects."""
    config = runtime_root() / "config.json"
    try:
        payload = json.loads(config.read_text(encoding="utf-8"))
        for record in payload.get("projects", []):
            if record.get("slug") == project and record.get("id"):
                return str(uuid.UUID(str(record["id"])))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"iproteinstudio-project:{project}"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def load_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StudioError(f"Required file is missing: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise StudioError(f"Could not read JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StudioError(f"Expected a JSON object in {path}.")
    return value


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def policy() -> Dict[str, Any]:
    path = agent_root() / "policy.json"
    if not path.exists():
        return {"schema_version": 1, "import_roots": []}
    return load_json(path)


def allowed_import_roots() -> List[Path]:
    roots = [runtime_root(), projects_root()]
    home = Path.home()
    roots.extend(home / name for name in ("Downloads", "Desktop", "Documents"))
    for value in policy().get("import_roots", []):
        if isinstance(value, str) and value.strip():
            roots.append(Path(value).expanduser())
    return [root.resolve() for root in roots if root.exists()]


def is_within(path: Path, roots: Iterable[Path]) -> bool:
    candidate = path.resolve()
    return any(candidate == root or root in candidate.parents for root in roots)


def approved_input(path_text: str) -> Path:
    path = Path(path_text).expanduser().resolve()
    if not path.is_file():
        raise StudioError(f"Input file does not exist: {path_text}")
    if not is_within(path, allowed_import_roots()):
        raise StudioError(
            "Input is outside the managed runtime and configured import roots. "
            "Add its parent to agent/policy.json rather than granting arbitrary filesystem access."
        )
    return path


def import_artifact(path_text: str) -> Dict[str, Any]:
    source = approved_input(path_text)
    digest = file_digest(source)
    destination_dir = runtime_root() / "objects" / "agent" / "sha256" / digest
    destination_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", source.name) or "input"
    destination = destination_dir / safe_name
    if destination.exists():
        if file_digest(destination) != digest:
            raise StudioError(f"Stored artifact failed checksum verification: {destination}")
    else:
        temporary = destination.with_name(f".{destination.name}.{os.getpid()}.part")
        shutil.copy2(source, temporary)
        if file_digest(temporary) != digest:
            temporary.unlink(missing_ok=True)
            raise StudioError("Imported artifact checksum did not match its source.")
        os.replace(temporary, destination)
    return {
        "uri": f"iprotein://artifacts/{digest}/{safe_name}",
        "sha256": digest,
        "name": safe_name,
        "path": str(destination),
        "bytes": destination.stat().st_size,
    }


def safe_managed_path(path_text: str, *, must_exist: bool = True) -> Path:
    path = Path(path_text).expanduser().resolve()
    if not is_within(path, [runtime_root()]):
        raise StudioError("Run and artifact paths must stay under the managed iProteinStudio root.")
    if must_exist and not path.exists():
        raise StudioError(f"Path does not exist: {path}")
    return path


def process_alive(pid: Any) -> bool:
    try:
        number = int(pid)
        if number <= 1:
            return False
        os.kill(number, 0)
        return True
    except (TypeError, ValueError, ProcessLookupError, PermissionError):
        return False


def tail_text(path: Path, lines: int = 80, max_bytes: int = 128_000) -> List[str]:
    if not path.is_file():
        return []
    with path.open("rb") as handle:
        size = path.stat().st_size
        handle.seek(max(0, size - max_bytes))
        data = handle.read(max_bytes)
    return data.decode("utf-8", errors="replace").splitlines()[-max(0, min(lines, 500)) :]


def csv_rows(path: Path, limit: int = 200) -> List[Dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        return list(row for _, row in zip(range(max(0, min(limit, 1000))), csv.DictReader(handle)))


def append_audit(tool: str, arguments: Dict[str, Any], result: Dict[str, Any]) -> None:
    record = {
        "at": utc_now(),
        "pid": os.getpid(),
        "tool": tool,
        "arguments_sha256": canonical_digest(arguments),
        "result": result,
    }
    path = agent_root() / "audit" / f"{datetime.now(timezone.utc).strftime('%Y-%m')}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def stable_environment(overrides: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    root = runtime_root()
    env = dict(os.environ)
    env.update(
        {
            "NANOHUNTER_ROOT": str(root),
            "NANOHUNTER_VENV_PREFIX": "NanoHunter",
            "NANOHUNTER_TARGET_MSA_CACHE_DIR_DEFAULT": str(root / "msa_cache"),
            "NANOHUNTER_SCAFFOLD_MSA_CACHE_DIR_DEFAULT": str(root / "scaffold_msa_cache"),
            "BOLTZ_CACHE": str(root / "models" / "boltz2"),
            "NUMBA_CACHE_DIR": str(root / "numba_cache"),
            "INTELLIFOLD_CACHE": str(root / "models" / "intellifold"),
            "PYTORCH_ENABLE_MPS_FALLBACK": "0",
            "PATH": os.pathsep.join(
                [str(Path.home() / ".local" / "bin"), "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
            ),
        }
    )
    if overrides:
        allowed = {"LASERMPNN_SEQ_TEMP", "LASERMPNN_FS_TEMP"}
        unknown = sorted(set(overrides) - allowed)
        if unknown:
            raise StudioError(f"Unsupported environment override(s): {', '.join(unknown)}")
        env.update({key: str(value) for key, value in overrides.items()})
    return env


def validate_schema(value: Any, definition: Dict[str, Any], location: str = "arguments") -> None:
    """Validate the JSON-Schema subset used by this bridge without a runtime dependency."""
    if "const" in definition and value != definition["const"]:
        raise StudioError(f"{location} must equal {definition['const']!r}.")
    if "enum" in definition and value not in definition["enum"]:
        raise StudioError(f"{location} must be one of {definition['enum']}.")
    expected = definition.get("type")
    allowed_types = expected if isinstance(expected, list) else [expected] if expected else []
    type_ok = not allowed_types
    for kind in allowed_types:
        if kind == "null" and value is None: type_ok = True
        elif kind == "object" and isinstance(value, dict): type_ok = True
        elif kind == "array" and isinstance(value, list): type_ok = True
        elif kind == "string" and isinstance(value, str): type_ok = True
        elif kind == "boolean" and isinstance(value, bool): type_ok = True
        elif kind == "integer" and isinstance(value, int) and not isinstance(value, bool): type_ok = True
        elif kind == "number" and isinstance(value, (int, float)) and not isinstance(value, bool): type_ok = True
    if not type_ok:
        raise StudioError(f"{location} has the wrong JSON type; expected {expected}.")
    if value is None:
        return
    if isinstance(value, dict):
        properties = definition.get("properties", {})
        missing = [name for name in definition.get("required", []) if name not in value]
        if missing:
            raise StudioError(f"{location} is missing required field(s): {', '.join(missing)}")
        if definition.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise StudioError(f"{location} has unknown field(s): {', '.join(unknown)}")
        extra_rule = definition.get("additionalProperties")
        for name, child in value.items():
            child_definition = properties.get(name)
            if child_definition is None and isinstance(extra_rule, dict):
                child_definition = extra_rule
            if child_definition is not None:
                validate_schema(child, child_definition, f"{location}.{name}")
    elif isinstance(value, list):
        minimum = definition.get("minItems")
        maximum = definition.get("maxItems")
        if minimum is not None and len(value) < minimum:
            raise StudioError(f"{location} must contain at least {minimum} item(s).")
        if maximum is not None and len(value) > maximum:
            raise StudioError(f"{location} must contain at most {maximum} item(s).")
        if definition.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            raise StudioError(f"{location} must not contain duplicates.")
        item_definition = definition.get("items")
        if isinstance(item_definition, dict):
            for index, child in enumerate(value):
                validate_schema(child, item_definition, f"{location}[{index}]")
    elif isinstance(value, str):
        if "minLength" in definition and len(value) < definition["minLength"]:
            raise StudioError(f"{location} is too short.")
        if "pattern" in definition and not re.fullmatch(definition["pattern"], value):
            raise StudioError(f"{location} does not match the required format.")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in definition and value < definition["minimum"]:
            raise StudioError(f"{location} must be at least {definition['minimum']}.")
        if "maximum" in definition and value > definition["maximum"]:
            raise StudioError(f"{location} must be at most {definition['maximum']}.")
