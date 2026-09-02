#!/usr/bin/env python3
from __future__ import annotations

import json
import importlib.metadata
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
    lock = root / "fixture-lock.txt"
    lock.write_text(f"pip=={importlib.metadata.version('pip')} \\\n+    --hash=sha256:{'0' * 64}\n")
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
        "--lock", str(lock),
        "--artifact", f"{artifact}={digest}", "--metadata", "purpose=transaction-test",
        "--source", f"{source}={revision}",
    ], check=True)
    subprocess.run([sys.executable, str(SCRIPT), "verify", "--receipt", str(receipt),
                    "--packages"], check=True)
    payload = json.loads(receipt.read_text())
    assert payload["component"] == "fixture"
    assert payload["python"]["resolved_packages"]
    assert payload["dependency_lock"]["requirements"]["pip"] == importlib.metadata.version("pip")
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

    # A venv interpreter is normally a symlink to its base Python. The receipt
    # must preserve the venv path; resolving it audits the base environment.
    venv = root / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    venv_python = venv / "bin/python"
    venv_pip = subprocess.check_output(
        [str(venv_python), "-c", "import importlib.metadata; print(importlib.metadata.version('pip'))"],
        text=True,
    ).strip()
    venv_lock = root / "venv-lock.txt"
    venv_lock.write_text(f"pip=={venv_pip} \\\n+    --hash=sha256:{'0' * 64}\n")
    venv_receipt = root / "venv-receipt.json"
    subprocess.run([
        sys.executable, str(SCRIPT), "write", "--output", str(venv_receipt),
        "--component", "venv", "--version", "1", "--python", str(venv_python),
        "--lock", str(venv_lock),
    ], check=True)
    assert json.loads(venv_receipt.read_text())["python"]["executable"] == str(venv_python)

    # RFdiffusion3 deliberately uses a lean uv environment with no pip module.
    # Receipt creation must inventory it through importlib.metadata rather than
    # turning a successful scientific installation into a setup failure.
    pipless = root / "pipless-venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(pipless)], check=True)
    pipless_python = pipless / "bin/python"
    purelib = Path(subprocess.check_output([
        str(pipless_python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"
    ], text=True).strip())
    metadata = purelib / "receipt_fixture-1.2.3.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: receipt-fixture\nVersion: 1.2.3\n"
    )
    pipless_receipt = root / "pipless-receipt.json"
    subprocess.run([
        sys.executable, str(SCRIPT), "write", "--output", str(pipless_receipt),
        "--component", "pipless", "--version", "1", "--python", str(pipless_python),
    ], check=True)
    pipless_payload = json.loads(pipless_receipt.read_text())
    assert pipless_payload["python"]["package_inventory_method"] == "importlib-metadata"
    assert pipless_payload["python"]["resolved_packages"] == ["receipt-fixture==1.2.3"]
    subprocess.run([
        sys.executable, str(SCRIPT), "verify", "--receipt", str(pipless_receipt),
        "--packages",
    ], check=True)

print("PASS immutable component receipt contract")
