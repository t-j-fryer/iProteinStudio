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
import re
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
        fsync_directory(path.parent)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def _phase(name):
    """Test seam for hard process termination at filesystem boundaries."""


def identity(component, version=None):
    for value in (component, version):
        if value is not None and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]*', value):
            raise ValueError('Unsafe runtime component/version identity')


def restore(root, journal, record):
    """Idempotent rollback, including a kill between old rename and new symlink."""
    root = root.resolve()
    for item in reversed(record['mappings']):
        legacy, backup = Path(item['legacy']), Path(item['backup'])
        if root not in legacy.parent.resolve().parents and legacy.parent.resolve() != root:
            raise ValueError('Runtime recovery path escapes managed root')
        if root not in backup.parent.resolve().parents:
            raise ValueError('Runtime backup path escapes managed root')
        if backup.exists() or backup.is_symlink():
            if legacy.is_symlink(): legacy.unlink()
            elif legacy.exists(): raise ValueError('Recovery refuses to overwrite an unexpected directory')
            os.replace(backup, legacy); fsync_directory(legacy.parent)
        elif not item['existed'] and legacy.is_symlink() and str(legacy.resolve()) == item['new_target']:
            legacy.unlink(); fsync_directory(legacy.parent)
    current = root/'components'/record['component']/'current'
    if record['old_current'] is not None:
        temporary = current.with_name('.recover-'+uuid.uuid4().hex)
        temporary.symlink_to(record['old_current']); os.replace(temporary,current)
    elif current.is_symlink() and str(current.resolve()) == record['final']:
        current.unlink()
    fsync_directory(current.parent)
    for name, payload in record.get('old_receipts', {}).items():
        path=root/'receipts'/name
        if payload is None:path.unlink(missing_ok=True)
        else:atomic_json(path,payload)
    record['state']='rolled_back'; atomic_json(journal,record)


def recover(root, component):
    identity(component)
    for journal in sorted((root/'components'/component/'transactions').glob('*.json')):
        record=json.loads(journal.read_text())
        if record['state']=='switching': restore(root,journal,record)


def rollback(root, component):
    identity(component); recover(root,component)
    journals=root/'components'/component/'transactions'
    current=(root/'components'/component/'current').resolve()
    for journal in sorted(journals.glob('*.json'),reverse=True):
        record=json.loads(journal.read_text())
        if record['state']=='committed' and record['final']==str(current):
            restore(root,journal,record); return
    raise ValueError('No retained activation journal for the current runtime')


def prepare(root: Path, component: str, version: str) -> Path:
    identity(component, version)
    root = root.resolve()
    recover(root, component)
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
    identity(component, version)
    root = root.resolve()
    recover(root, component)
    component_root = root / "components" / component
    versions = component_root / "versions"
    resolved_stage = stage.resolve()
    if resolved_stage.parent != versions.resolve() or not stage.name.startswith(".staging-"):
        raise ValueError("stage is not a transaction owned by this component")
    transaction = json.loads((stage / "transaction.json").read_text())
    if transaction.get("component") != component or transaction.get("version") != version:
        raise ValueError("stage transaction identity mismatch")
    parsed = mappings(mapping_values)
    for legacy, relative in parsed:
        if not legacy.is_absolute() or (legacy.parent.resolve() != root and root not in legacy.parent.resolve().parents):
            raise ValueError('Runtime mapping escapes managed root')
        if not (stage / relative).exists():
            raise ValueError(f"staged mapping is absent: {relative}")

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    final = versions / f"{version}-{stamp}-{uuid.uuid4().hex[:8]}"
    backups = root / "backups" / "components" / component / f"{stamp}-{uuid.uuid4().hex[:8]}"
    backups.mkdir(parents=True, exist_ok=True)
    current=component_root/'current'
    if current.exists() and not current.is_symlink():raise ValueError('Current runtime pointer is not a symlink')
    journal=component_root/'transactions'/(stamp+'-'+uuid.uuid4().hex+'.json')
    record=dict(schema_version=2,component=component,version=version,state='switching',final=str(final),
                old_current=os.readlink(current) if current.is_symlink() else None,
                old_receipts={name:json.loads((root/'receipts'/name).read_text()) if (root/'receipts'/name).is_file() else None
                              for name in (component+'.json',component+'-runtime.json')},
                mappings=[dict(legacy=str(legacy),backup=str(backups/(legacy.name if sum(p.name==legacy.name for p,_ in parsed)==1 else str(i)+'-'+legacy.name)),
                               existed=legacy.exists() or legacy.is_symlink(),new_target=str(final/relative))
                          for i,(legacy,relative) in enumerate(parsed)])
    atomic_json(journal,record)
    os.replace(stage, final); fsync_directory(versions); _phase('final_renamed')
    atomic_json(final / "transaction.json", {
        "schema_version": 1,
        "component": component,
        "version": version,
        "state": "ready",
        "committed_at": stamp,
    })

    try:
        for i,(legacy, relative) in enumerate(parsed):
            legacy.parent.mkdir(parents=True, exist_ok=True)
            old: Path | None = None
            if legacy.exists() or legacy.is_symlink():
                old = Path(record['mappings'][i]['backup'])
                os.replace(legacy, old); fsync_directory(legacy.parent); fsync_directory(backups)
                _phase('old_moved_'+str(i))
            temporary = legacy.with_name(f".{legacy.name}.new-{uuid.uuid4().hex}")
            temporary.symlink_to(final / relative)
            os.replace(temporary, legacy)
            fsync_directory(legacy.parent); _phase('new_link_'+str(i))
        current_new = component_root / f".current-{uuid.uuid4().hex}"
        current_new.symlink_to(final.relative_to(component_root))
        os.replace(current_new, component_root / "current")
        fsync_directory(component_root); _phase('current_switched')
        record['state']='committed'; atomic_json(journal,record)
    except BaseException:
        restore(root,journal,record)
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
    for operation in ('recover','rollback'):
        sub=subparsers.add_parser(operation); sub.add_argument('--root',type=Path,required=True); sub.add_argument('--component',required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print(prepare(args.root, args.component, args.version))
        elif args.command == 'commit':
            print(commit(args.root, args.component, args.version, args.stage, args.mapping))
        elif args.command == 'recover':recover(args.root,args.component)
        else:rollback(args.root,args.component)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
