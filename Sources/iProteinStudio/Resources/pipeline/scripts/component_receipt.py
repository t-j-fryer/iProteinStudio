#!/usr/bin/env python3
"""Create and verify immutable managed-component installation receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


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
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def parse_pairs(values: list[str], label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"{label} must use PATH=VALUE: {value}")
        path, expected = value.split("=", 1)
        result[path] = expected
    return result


def source_worktree_digest(path: str) -> str:
    """Fingerprint tracked changes applied on top of the pinned revision."""
    patch = subprocess.check_output(
        ["git", "-C", path, "diff", "--binary", "--no-ext-diff", "HEAD", "--"]
    )
    return hashlib.sha256(patch).hexdigest()


def write(args: argparse.Namespace) -> None:
    artifacts = parse_pairs(args.artifact, "artifact")
    sources = parse_pairs(args.source, "source")
    for raw_path, expected in artifacts.items():
        path = Path(raw_path)
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"artifact does not match its pinned SHA-256: {path}")
    for raw_path, expected in sources.items():
        actual = subprocess.check_output(
            ["git", "-C", raw_path, "rev-parse", "HEAD"], text=True
        ).strip()
        if actual != expected:
            raise ValueError(f"source revision mismatch for {raw_path}: {actual} != {expected}")
    source_worktrees = {
        raw_path: source_worktree_digest(raw_path) for raw_path in sources
    }

    python: dict[str, object] | None = None
    packages: list[str] = []
    if args.python:
        executable = Path(args.python).resolve()
        if not executable.is_file():
            raise ValueError(f"Python executable is absent: {executable}")
        version = subprocess.check_output(
            [str(executable), "-c", "import platform; print(platform.python_version())"], text=True
        ).strip()
        packages = sorted(line for line in subprocess.check_output(
            [str(executable), "-m", "pip", "freeze", "--exclude-editable"], text=True
        ).splitlines() if line and not line.startswith("#"))
        python = {
            "executable": str(executable),
            "version": version,
            "resolved_packages": packages,
            "resolved_packages_sha256": hashlib.sha256(
                ("\n".join(packages) + "\n").encode()
            ).hexdigest(),
        }

    payload: dict[str, object] = {
        "schema_version": 1,
        "component": args.component,
        "component_version": args.version,
        "device_policy": args.device_policy,
        "python": python,
        "sources": sources,
        "source_worktree_sha256": source_worktrees,
        "artifacts": artifacts,
        "metadata": parse_pairs(args.metadata, "metadata"),
    }
    atomic_json(args.output, payload)


def verify(receipt: Path, verify_packages: bool) -> None:
    data = json.loads(receipt.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError(f"unsupported receipt schema: {receipt}")
    for raw_path, expected in data.get("artifacts", {}).items():
        path = Path(raw_path)
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"artifact verification failed: {path}")
    for raw_path, expected in data.get("sources", {}).items():
        actual = subprocess.check_output(
            ["git", "-C", raw_path, "rev-parse", "HEAD"], text=True
        ).strip()
        if actual != expected:
            raise ValueError(f"source verification failed: {raw_path}")
        recorded_worktree = data.get("source_worktree_sha256", {}).get(raw_path)
        if recorded_worktree and source_worktree_digest(raw_path) != recorded_worktree:
            raise ValueError(f"source worktree changed after receipt creation: {raw_path}")
    python = data.get("python")
    if python:
        executable = Path(python["executable"])
        if not executable.is_file():
            raise ValueError(f"recorded Python is absent: {executable}")
        actual_version = subprocess.check_output(
            [str(executable), "-c", "import platform; print(platform.python_version())"], text=True
        ).strip()
        if actual_version != python["version"]:
            raise ValueError(f"Python version changed: {actual_version} != {python['version']}")
        if verify_packages:
            packages = sorted(line for line in subprocess.check_output(
                [str(executable), "-m", "pip", "freeze", "--exclude-editable"], text=True
            ).splitlines() if line and not line.startswith("#"))
            digest = hashlib.sha256(("\n".join(packages) + "\n").encode()).hexdigest()
            if digest != python["resolved_packages_sha256"]:
                raise ValueError("installed package graph changed after receipt creation")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    writer = subparsers.add_parser("write")
    writer.add_argument("--output", type=Path, required=True)
    writer.add_argument("--component", required=True)
    writer.add_argument("--version", required=True)
    writer.add_argument("--python")
    writer.add_argument("--device-policy", default="unspecified")
    writer.add_argument("--artifact", action="append", default=[])
    writer.add_argument("--source", action="append", default=[])
    writer.add_argument("--metadata", action="append", default=[])
    verifier = subparsers.add_parser("verify")
    verifier.add_argument("--receipt", type=Path, required=True)
    verifier.add_argument("--packages", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "write":
            write(args)
        else:
            verify(args.receipt, args.packages)
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
