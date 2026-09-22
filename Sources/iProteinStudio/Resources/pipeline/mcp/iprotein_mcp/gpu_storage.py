"""Explicit support diagnostic for Apple's shared MPSGraph temporary storage.

Normal job startup never imports or invokes this diagnostic.

Never enumerate, rename or clear the shared directory. The child only creates
and removes a uniquely named empty probe directory. Isolating filesystem calls
keeps the job broker responsive even if the filesystem blocks inside the kernel.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import uuid


def probe(directory: Path) -> dict:
    try:
        metadata = directory.lstat()
    except FileNotFoundError:
        return {"status": "not_created"}
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise RuntimeError("GPU temporary storage is not an owned, regular directory")
    path = directory / ("iproteinstudio-probe-" + uuid.uuid4().hex)
    path.mkdir(mode=0o700)
    path.rmdir()  # Only our own empty directory; never remove other contents.
    return {"status": "ok", "directory_metadata_bytes": metadata.st_size}


def check(timeout: float = 5.0, *, command=None) -> dict:
    """Return within timeout plus at most one second of child termination."""
    if command is None and sys.platform != "darwin":
        return {"status": "not_applicable"}
    command = command or [sys.executable, "-B", str(Path(__file__).resolve()), "--probe"]
    started = time.monotonic()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            # A filesystem syscall can remain uninterruptible until macOS
            # returns. Never wait indefinitely, retry or spawn more probes.
            process.stdout.close()
            process.stderr.close()
        return {"status": "timeout", "seconds": time.monotonic()-started, "probe_pid": process.pid}
    if process.returncode:
        return {"status": "error", "seconds": time.monotonic()-started, "detail": stderr[-2000:]}
    try:
        result = json.loads(stdout)
        if result.get("status") not in {"ok", "not_created"}:
            raise ValueError("Unexpected GPU storage probe response")
    except (ValueError, AttributeError) as error:
        return {"status": "error", "detail": str(error)}
    return dict(result, seconds=time.monotonic()-started)


def failure_message(result: dict) -> str | None:
    if result["status"] in {"ok", "not_created", "not_applicable"}:
        return None
    return ("macOS GPU temporary storage is not responding or is inaccessible. "
            "Save other work, restart your Mac, then retry the affected job. "
            "Completed results are preserved. If this continues, share the job diagnostic with support; "
            "Studio has not cleared or changed shared GPU files.")


def main(arguments=None) -> int:
    arguments = sys.argv[1:] if arguments is None else arguments
    if arguments == ["--diagnose"]:
        result = check()
        print(json.dumps(result))
        return 0 if failure_message(result) is None else 1
    if arguments != ["--probe"]:
        raise SystemExit("Use --diagnose for the bounded support diagnostic")
    temporary = subprocess.check_output(["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"], text=True, timeout=2).strip()
    if not temporary or not Path(temporary).is_absolute():
        raise RuntimeError("macOS did not return its user temporary directory")
    print(json.dumps(probe(Path(temporary)/"com.apple.MetalPerformanceShadersGraph")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
