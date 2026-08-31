#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Sources/iProteinStudio/Resources/pipeline/scripts/runtime_transaction.py"


def run(*arguments: str) -> str:
    return subprocess.check_output([sys.executable, str(SCRIPT), *arguments], text=True).strip()


with tempfile.TemporaryDirectory(prefix="iproteinstudio-transaction-") as raw:
    root = Path(raw)
    legacy = root / "venvs/Test_engine"
    legacy.mkdir(parents=True)
    (legacy / "identity.txt").write_text("old\n")

    abandoned = Path(run("prepare", "--root", str(root), "--component", "engine",
                         "--version", "2"))
    (abandoned / "venv").mkdir()
    (abandoned / "venv/identity.txt").write_text("incomplete\n")
    assert (legacy / "identity.txt").read_text() == "old\n"

    stage = Path(run("prepare", "--root", str(root), "--component", "engine",
                     "--version", "2"))
    (stage / "venv").mkdir()
    (stage / "venv/identity.txt").write_text("new\n")
    run("commit", "--root", str(root), "--component", "engine", "--version", "2",
        "--stage", str(stage), "--mapping", f"{legacy}=venv")
    assert legacy.is_symlink()
    assert (legacy / "identity.txt").read_text() == "new\n"
    backups = list((root / "backups/components/engine").glob("*/Test_engine/identity.txt"))
    assert len(backups) == 1 and backups[0].read_text() == "old\n"

    failed = Path(run("prepare", "--root", str(root), "--component", "engine",
                      "--version", "3"))
    result = subprocess.run([
        sys.executable, str(SCRIPT), "commit", "--root", str(root),
        "--component", "engine", "--version", "3", "--stage", str(failed),
        "--mapping", f"{legacy}=venv",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert result.returncode != 0
    assert (legacy / "identity.txt").read_text() == "new\n"

print("PASS versioned runtime transaction, interruption, switch and rollback contract")
