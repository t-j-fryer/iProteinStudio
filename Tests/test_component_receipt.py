#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Sources/iProteinStudio/Resources/pipeline/scripts/component_receipt.py"

with tempfile.TemporaryDirectory(prefix="iproteinstudio-receipt-") as raw:
    root = Path(raw)
    artifact = root / "checkpoint.pt"
    artifact.write_bytes(b"checkpoint fixture\n")
    digest = subprocess.check_output(["shasum", "-a", "256", str(artifact)], text=True).split()[0]
    receipt = root / "receipt.json"
    source = root / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "config", "user.name", "Receipt Test"], check=True)
    subprocess.run(["git", "-C", str(source), "config", "user.email", "receipt@example.invalid"], check=True)
    tracked = source / "engine.py"
    tracked.write_text("validated = True\n")
    subprocess.run(["git", "-C", str(source), "add", "engine.py"], check=True)
    subprocess.run(["git", "-C", str(source), "commit", "-qm", "fixture"], check=True)
    revision = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    subprocess.run([
        sys.executable, str(SCRIPT), "write",
        "--output", str(receipt), "--component", "fixture", "--version", "1",
        "--python", sys.executable, "--device-policy", "test-only",
        "--artifact", f"{artifact}={digest}", "--metadata", "purpose=transaction-test",
        "--source", f"{source}={revision}",
    ], check=True)
    subprocess.run([sys.executable, str(SCRIPT), "verify", "--receipt", str(receipt),
                    "--packages"], check=True)
    payload = json.loads(receipt.read_text())
    assert payload["component"] == "fixture"
    assert payload["python"]["resolved_packages"]
    tracked.write_text("validated = False\n")
    failed = subprocess.run(
        [sys.executable, str(SCRIPT), "verify", "--receipt", str(receipt)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    assert failed.returncode != 0
    subprocess.run(["git", "-C", str(source), "checkout", "--", "engine.py"], check=True)
    artifact.write_bytes(b"corrupt\n")
    failed = subprocess.run(
        [sys.executable, str(SCRIPT), "verify", "--receipt", str(receipt)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    assert failed.returncode != 0

print("PASS immutable component receipt contract")
