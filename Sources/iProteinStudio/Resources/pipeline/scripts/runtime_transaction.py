#!/usr/bin/env python3
"""Atomic version switches for managed runtime components.

The installer builds under the returned staging directory, validates there,
then commits one or more legacy-path mappings to a versioned component. Existing
content is retained in a recoverable backup; an interrupted stage is invisible.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path


def atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def prepare(root: Path, component: str, version: str) -> Path:
    versions = root / "components" / component / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    # The global installer lock guarantees that no live setup owns a stage when
    # a new invocation reaches this point. Remove only directories that carry
    # our own incomplete transaction marker for this component. Unknown or
    # malformed entries are preserved for inspection rather than guessed at.
    for candidate in versions.iterdir():
        if candidate.is_symlink() or not candidate.is_dir() \
                or not candidate.name.startswith(".staging-"):
            continue
        try:
            transaction = json.loads((candidate / "transaction.json").read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if transaction.get("component") == component \
                and transaction.get("state") == "staging":
            shutil.rmtree(candidate)
    stage = versions / f".staging-{version}-{uuid.uuid4().hex}"
    stage.mkdir()
    atomic_json(stage / "transaction.json", {
        "schema_version": 1,
        "component": component,
        "version": version,
        "state": "staging",
    })
    return stage


def mappings(values: list[str]) -> list[tuple[Path, Path]]:
    result: list[tuple[Path, Path]] = []
    for value in values:
        if "=" not in value:
            raise ValueError(f"mapping must be LEGACY=RELATIVE: {value}")
        legacy, relative = value.split("=", 1)
        if not legacy or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError(f"unsafe mapping: {value}")
        result.append((Path(legacy), Path(relative)))
    return result


def commit(root: Path, component: str, version: str, stage: Path,
           mapping_values: list[str]) -> Path:
    component_root = root / "components" / component
    versions = component_root / "versions"
    resolved_stage = stage.resolve()
    if resolved_stage.parent != versions.resolve() or not stage.name.startswith(".staging-"):
        raise ValueError("stage is not a transaction owned by this component")
    transaction = json.loads((stage / "transaction.json").read_text())
    if transaction.get("component") != component or transaction.get("version") != version:
        raise ValueError("stage transaction identity mismatch")
    parsed = mappings(mapping_values)
    for _, relative in parsed:
        if not (stage / relative).exists():
            raise ValueError(f"staged mapping is absent: {relative}")

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    final = versions / f"{version}-{stamp}-{uuid.uuid4().hex[:8]}"
    os.replace(stage, final)
    atomic_json(final / "transaction.json", {
        "schema_version": 1,
        "component": component,
        "version": version,
        "state": "ready",
        "committed_at": stamp,
    })

    backups = root / "backups" / "components" / component / f"{stamp}-{uuid.uuid4().hex[:8]}"
    backups.mkdir(parents=True, exist_ok=True)
    switched: list[tuple[Path, Path | None]] = []
    try:
        for legacy, relative in parsed:
            legacy.parent.mkdir(parents=True, exist_ok=True)
            old: Path | None = None
            if legacy.exists() or legacy.is_symlink():
                old = backups / legacy.name
                os.replace(legacy, old)
            temporary = legacy.with_name(f".{legacy.name}.new-{uuid.uuid4().hex}")
            temporary.symlink_to(final / relative)
            os.replace(temporary, legacy)
            switched.append((legacy, old))
        current_new = component_root / f".current-{uuid.uuid4().hex}"
        current_new.symlink_to(final.relative_to(component_root))
        os.replace(current_new, component_root / "current")
    except BaseException:
        for legacy, old in reversed(switched):
            legacy.unlink(missing_ok=True)
            if old is not None and (old.exists() or old.is_symlink()):
                os.replace(old, legacy)
        raise
    return final


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--root", type=Path, required=True)
    prepare_parser.add_argument("--component", required=True)
    prepare_parser.add_argument("--version", required=True)
    commit_parser = subparsers.add_parser("commit")
    commit_parser.add_argument("--root", type=Path, required=True)
    commit_parser.add_argument("--component", required=True)
    commit_parser.add_argument("--version", required=True)
    commit_parser.add_argument("--stage", type=Path, required=True)
    commit_parser.add_argument("--mapping", action="append", required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print(prepare(args.root, args.component, args.version))
        else:
            print(commit(args.root, args.component, args.version, args.stage, args.mapping))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
