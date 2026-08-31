#!/usr/bin/env python3
"""Static acceptance for complete, portable hash-locked engine graphs."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCKS = ROOT / "Sources/iProteinStudio/Resources/pipeline/locks"
EXPECTED = {
    "antifold.txt", "boltz.txt", "intellifold.txt", "lasermpnn.txt",
    "lasermpnn_bootstrap.txt", "mpnn.txt", "openfold3.txt",
    "protenix.txt", "protenix_constraint.txt",
}

assert {path.name for path in LOCKS.glob("*.txt")} == EXPECTED
for path in sorted(LOCKS.glob("*.txt")):
    text = path.read_text()
    assert "/Users/" not in text and "/private/" not in text
    requirement: str | None = None
    has_hash = False
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line[0].isspace():
            if requirement is not None:
                assert has_hash, f"{path.name}: {requirement} has no hash"
            requirement = stripped.removesuffix("\\").strip()
            assert re.fullmatch(r"[A-Za-z0-9_.-]+==[^ ;\\]+", requirement), (
                f"{path.name}: invalid or unpinned requirement {requirement!r}"
            )
            has_hash = False
            count += 1
        elif stripped.startswith("--hash=sha256:"):
            assert requirement is not None, f"{path.name}: orphaned hash before first package"
            assert re.fullmatch(r"--hash=sha256:[0-9a-f]{64}(?: \\)?", stripped)
            has_hash = True
    assert requirement is not None and has_hash
    assert count >= 5, f"{path.name}: suspiciously short resolution"

print(f"PASS installer hash-lock contract ({len(EXPECTED)} complete graphs)")
