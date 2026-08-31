#!/usr/bin/env python3
"""Safely consolidate immutable assets duplicated by older Studio installs.

Only byte-for-byte verified, enumerated Protenix common-data files are ever
discarded. Unknown or changed content is retained in a timestamped backup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path


COMMON = {
    "components.cif": "bb31ae5cf6c8bc669924313077cb4231ee5ffefd3a20118cd14f3ec89f8bb6a5",
    "components.cif.rdkit_mol.pkl": "d1cfb71f5993a3ebea7c47877022d7f597bbfbaf86e28a4770e957da6c50cd35",
    "obsolete_release_date.csv": "a4f3f63ac5d7eebd78b07995cc669b9eccd6f5d8813c9492c9df02868893cf33",
    "clusters-by-entity-40.txt": "1ab4af905e75b382eda8dec59917dc3608bee0729e36b9e71baf860bbe86850c",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def allocated(path: Path) -> int:
    if path.is_symlink() or not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_blocks * 512
    return sum(item.stat().st_blocks * 512 for item in path.rglob("*")
               if item.is_file() and not item.is_symlink())


def expected_files_valid(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink() and all(
        (path / name).is_file() and digest(path / name) == expected
        for name, expected in COMMON.items()
    )


def exact_generated_copy(path: Path) -> bool:
    if not expected_files_valid(path):
        return False
    present = {
        item.relative_to(path).as_posix() for item in path.rglob("*")
        if item.is_file() and item.name != ".DS_Store"
    }
    return present == set(COMMON)


def verify_shared(shared: Path) -> None:
    if not expected_files_valid(shared):
        raise ValueError(f"shared Protenix data is incomplete or changed: {shared}")


def seed_shared(shared: Path, candidates: list[Path]) -> None:
    if expected_files_valid(shared):
        return
    source = next((item for item in candidates if expected_files_valid(item)), None)
    if source is None:
        raise ValueError("no complete, verified Protenix common-data copy is available")
    shared.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".protenix-common-", dir=shared.parent))
    try:
        for name in COMMON:
            # copy2 uses clonefile on modern macOS Python where available;
            # correctness does not depend on copy-on-write support.
            shutil.copy2(source / name, stage / name)
        verify_shared(stage)
        if shared.exists() or shared.is_symlink():
            raise ValueError(f"refusing to replace unverified shared data: {shared}")
        os.replace(stage, shared)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def consolidate(root: Path, dry_run: bool) -> dict[str, object]:
    root = root.resolve()
    shared = root / "shared" / "protenix-common" / "v0.5"
    targets = [root / "models" / "protenix" / "common",
               root / "models" / "protenix_constraint" / "common"]
    candidates = [item for item in targets if item.is_dir() and not item.is_symlink()]
    valid_targets = [item for item in candidates if expected_files_valid(item)]
    if not valid_targets and not expected_files_valid(shared):
        return {"changed": False, "reclaimed_bytes": 0, "detail": "no verified duplicate assets found"}

    reclaimable = sum(allocated(item) for item in valid_targets)
    if not expected_files_valid(shared) and valid_targets:
        # One copy remains in shared storage, so it is not reclaimable.
        reclaimable -= allocated(valid_targets[0])
    if dry_run:
        return {"changed": False, "reclaimable_bytes": max(0, reclaimable),
                "verified_copies": len(valid_targets)}

    before = allocated(shared) + sum(allocated(item) for item in targets)
    seed_shared(shared, candidates)
    verify_shared(shared)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    retained: list[str] = []
    linked: list[str] = []
    for target in targets:
        if target.is_symlink() and target.resolve() == shared.resolve():
            continue
        if not target.exists() and not target.is_symlink():
            continue
        if target.is_dir() and not target.is_symlink() and not expected_files_valid(target):
            # Never alter a partial or modified directory automatically.
            retained.append(str(target))
            continue
        backup_root = root / "backups" / "protenix-common"
        backup_root.mkdir(parents=True, exist_ok=True)
        backup = backup_root / f"{target.parent.name}-{stamp}-{os.getpid()}"
        temporary = target.with_name(f".common-link-{os.getpid()}")
        temporary.symlink_to(shared)
        os.replace(target, backup)
        try:
            os.replace(temporary, target)
            if target.resolve() != shared.resolve():
                raise ValueError(f"shared link verification failed: {target}")
        except BaseException:
            temporary.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            os.replace(backup, target)
            raise
        if exact_generated_copy(backup):
            shutil.rmtree(backup)
        else:
            retained.append(str(backup))
        linked.append(str(target))

    after = allocated(shared) + sum(allocated(item) for item in targets)
    return {"changed": bool(linked), "reclaimed_bytes": max(0, before - after),
            "linked": linked, "retained_for_safety": retained}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(consolidate(args.root, args.dry_run), sort_keys=True))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
