#!/usr/bin/env python3
"""Headless equivalent of AppPaths asset staging; never installs into system paths."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
GENERATED = {"__pycache__", "numba_cache", ".DS_Store", ".git"}
RESERVED = {"agent", "models", "components", "venvs", "src", "toolchains", "receipts",
            "projects", "objects", "msa_cache", "scaffold_msa_cache", "config.json"}


def exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif exists(path):
        path.unlink()


def write_json(path: Path, value) -> None:
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    with temporary.open("rb") as stream:
        os.fsync(stream.fileno())
    os.replace(temporary, path)


@contextmanager
def execution_lease(root: Path):
    agent = root / "agent"
    if agent.is_symlink():
        raise ValueError("Managed agent directory must not be a symbolic link")
    agent.mkdir(parents=True, exist_ok=True)
    with (agent / "execution.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Studio is using this installation. Let active work finish before staging assets.") from None
        yield


@contextmanager
def installer_lock(root: Path):
    lock = root / ".install.lock"
    if lock.is_symlink():
        raise ValueError("Installer lock must not be a symbolic link")
    try:
        lock.mkdir()
    except FileExistsError:
        try:
            owner = int((lock / "pid").read_text().strip())
            if owner <= 0:
                raise ValueError("Invalid installer owner")
            os.kill(owner, 0)
        except ProcessLookupError:
            (lock / "pid").unlink()
            lock.rmdir()  # Refuse to remove unknown lock contents.
            lock.mkdir()
        except (OSError, ValueError):
            raise ValueError("Cannot establish installer ownership; another installation may be starting.") from None
        else:
            raise ValueError("Another Studio installation or repair is running.")
    (lock / "pid").write_text(str(os.getpid()) + "\n")
    try:
        yield
    finally:
        if (lock / "pid").read_text().strip() == str(os.getpid()):
            (lock / "pid").unlink()
            lock.rmdir()


def clean_copy(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise ValueError(f"Resource payload contains a symbolic link: {source.name}")
    if source.name in GENERATED or source.suffix in {".pyc", ".pyo"}:
        return
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for child in sorted(source.iterdir()):
            clean_copy(child, destination / child.name)
    elif source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    else:
        raise ValueError(f"Resource is not a regular file or directory: {source.name}")


def destination(root: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("Invalid staging destination")
    result = root / relative
    # Replacing a symlink itself is safe; traversing its parent is not.
    if not result.parent.resolve().is_relative_to(root):
        raise ValueError(f"Staging destination escapes the managed root: {name}")
    return result


def recover(root: Path) -> None:
    for transaction in sorted(root.glob(".headless-stage-*")):
        if transaction.is_symlink() or not transaction.is_dir():
            raise ValueError("Invalid asset staging transaction")
        journal = transaction / "journal.json"
        if not journal.exists():
            shutil.rmtree(transaction)  # Preparation never modifies live assets.
            continue
        data = json.loads(journal.read_text())
        if data["state"] != "committed":
            for index, item in reversed(list(enumerate(data["items"]))):
                target = destination(root, item["name"])
                old = transaction / "backup" / str(index)
                new = transaction / "payload" / str(index)
                if exists(old):
                    remove(target)
                    os.replace(old, target)
                elif not item["previous"] and not exists(new):
                    remove(target)
        shutil.rmtree(transaction)


def stage(resources: Path, root: Path) -> dict:
    pipeline = resources / "pipeline"
    for required in [pipeline / "PIPELINE_VERSION", pipeline / "mcp/server.py",
                     pipeline / "setup_pipeline.sh", resources / "rfd3/predict_batch.py",
                     resources / "rfd3_overlay/OVERLAY_VERSION", resources / "examples"]:
        if not required.exists():
            raise ValueError(f"Incomplete resource payload: {required.relative_to(resources)}")
    recover(root)
    transaction = root / (".headless-stage-" + uuid.uuid4().hex)
    payload = transaction / "payload"
    backup = transaction / "backup"
    payload.mkdir(parents=True)
    backup.mkdir()
    items = []
    try:
        sources = {p.name: p for p in pipeline.iterdir() if p.name not in GENERATED}
        if RESERVED.intersection(sources):
            raise ValueError("Pipeline payload attempts to replace managed user/runtime data")
        sources.update(rfd3_scripts=resources / "rfd3", rfd3_overlay=resources / "rfd3_overlay",
                       examples_data=resources / "examples")
        for name, source in sorted(sources.items()):
            if source.suffix in {".pyc", ".pyo"}:
                continue
            index = len(items)
            target = destination(root, name)
            clean_copy(source, payload / str(index))
            if name in {"setup_pipeline.sh", "nanohunter_run.sh", "install_cli.sh"}:
                (payload / str(index)).chmod(0o755)
            if name == "bin":
                for launcher in (payload / str(index)).iterdir():
                    launcher.chmod(0o755)
            items.append(dict(name=name, previous=exists(target)))

        resource_count = len(items)
        # Mirror AppPaths' seed-once caches. Existing/generated alignments win.
        seeds = []
        for example in (resources / "examples").iterdir():
            alignment = example / "target_msa.a3m"
            if alignment.is_file():
                seeds.append((alignment, f"msa_cache/example_{example.name}.a3m"))
        for alignment in sorted((pipeline / "examples/nanobody_scaffolds/msas").glob("*/full_msa.a3m")):
            seeds.append((alignment, f"scaffold_msa_cache/{alignment.parent.name}/full_msa.a3m"))
        for source, name in seeds:
            if not exists(destination(root, name)):
                clean_copy(source, payload / str(len(items)))
                items.append(dict(name=name, previous=False))

        inventory = {}
        for index, item in enumerate(items[:resource_count]):
            new = payload / str(index)
            files = sorted(new.rglob("*")) if new.is_dir() else [new]
            for file in files:
                if file.is_file():
                    suffix = str(file.relative_to(new)) if new.is_dir() else ""
                    name = str(Path(item["name"]) / suffix)
                    inventory[name] = hashlib.sha256(file.read_bytes()).hexdigest()
        digest = hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
        seed_inventory = {item["name"]: hashlib.sha256((payload / str(index)).read_bytes()).hexdigest()
                          for index, item in enumerate(items) if index >= resource_count}
        receipt = dict(schema=1, pipeline_version=(pipeline / "PIPELINE_VERSION").read_text().strip(),
                       assets_sha256=digest, files=inventory, created_msa_seeds=seed_inventory)
        receipt_name = "receipts/headless-assets.json"
        write_json(payload / str(len(items)), receipt)
        items.append(dict(name=receipt_name, previous=exists(destination(root, receipt_name))))
        journal = dict(schema=1, state="applying", items=items)
        write_json(transaction / "journal.json", journal)
        for index, item in enumerate(items):
            target = destination(root, item["name"])
            target.parent.mkdir(parents=True, exist_ok=True)
            if item["previous"]:
                os.replace(target, backup / str(index))
            os.replace(payload / str(index), target)
        journal["state"] = "committed"
        write_json(transaction / "journal.json", journal)
    except BaseException:
        recover(root)
        raise
    recover(root)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("setup_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    resources, root = args.resources.resolve(), args.root.expanduser().resolve()
    if root == Path.home().resolve() or root == Path("/") or root.is_relative_to(resources) or resources.is_relative_to(root):
        parser.error("Choose a separate managed installation directory, not home, /, or the resource/source tree")
    if any(c.isspace() for c in str(root)):
        parser.error("The installation path must not contain whitespace")
    setup_args = args.setup_args[1:] if args.setup_args[:1] == ["--"] else args.setup_args
    root.mkdir(parents=True, exist_ok=True)
    try:
        with execution_lease(root):
            with installer_lock(root):
                receipt = stage(resources, root)
            print("Staged Studio assets: " + receipt["assets_sha256"], flush=True)
            if args.install:
                result = subprocess.run(["/bin/bash", str(root / "setup_pipeline.sh"), *setup_args],
                                        env={**os.environ, "NANOHUNTER_ROOT": str(root)})
                if result.returncode:
                    return result.returncode
                # Stage-only installs the normal pinned control runtime too.
                subprocess.run([str(root / "bin/studioctl"), "doctor"], check=True)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Studio install: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
