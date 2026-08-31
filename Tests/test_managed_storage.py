#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Sources/iProteinStudio/Resources/pipeline/scripts/managed_storage.py"
spec = importlib.util.spec_from_file_location("managed_storage", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


fixtures = {"components.cif": b"ccd", "components.pkl": b"rdkit",
            "obsolete.csv": b"obsolete", "clusters.txt": b"clusters"}
module.COMMON = {name: sha(data) for name, data in fixtures.items()}

with tempfile.TemporaryDirectory(prefix="iproteinstudio-storage-") as raw:
    root = Path(raw)
    standard = root / "models/protenix/common"
    constraint = root / "models/protenix_constraint/common"
    for directory in (standard, constraint):
        directory.mkdir(parents=True)
        for name, data in fixtures.items():
            (directory / name).write_bytes(data)
    (constraint / "user-note.txt").write_text("must survive")

    plan = module.consolidate(root, dry_run=True)
    assert plan["verified_copies"] == 2
    result = module.consolidate(root, dry_run=False)
    shared = root / "shared/protenix-common/v0.5"
    assert standard.is_symlink() and standard.resolve() == shared.resolve()
    assert constraint.is_symlink() and constraint.resolve() == shared.resolve()
    assert all((shared / name).read_bytes() == data for name, data in fixtures.items())
    backups = list((root / "backups/protenix-common").iterdir())
    assert len(backups) == 1, backups
    assert (backups[0] / "user-note.txt").read_text() == "must survive"
    assert result["changed"] is True and result["retained_for_safety"]

    repeated = module.consolidate(root, dry_run=False)
    assert repeated["changed"] is False

with tempfile.TemporaryDirectory(prefix="iproteinstudio-storage-invalid-") as raw:
    root = Path(raw)
    invalid = root / "models/protenix/common"
    invalid.mkdir(parents=True)
    (invalid / "components.cif").write_bytes(b"changed")
    result = module.consolidate(root, dry_run=False)
    assert result["changed"] is False
    assert (invalid / "components.cif").read_bytes() == b"changed"

print("PASS verified managed-storage consolidation")
