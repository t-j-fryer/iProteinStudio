#!/usr/bin/env python3
"""Resumably download one checksummed artifact with machine-readable progress.

The standard-library URL reader can leave a dead TLS stream looking connected
forever. This helper gives every connect/read a timeout, retains `.part` bytes,
reopens with HTTP Range after transient failures, and only exposes the final
path after its SHA-256 matches.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import re
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path


CHUNK = 8 << 20


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            value.update(block)
    return value.hexdigest()


def human(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    number = float(value)
    for unit in units:
        if number < 1000 or unit == units[-1]:
            return f"{number:.1f} {unit}" if unit != "B" else f"{value} B"
        number /= 1000
    return f"{value} B"


def total_from_headers(response, offset: int) -> int | None:
    content_range = response.headers.get("Content-Range", "")
    match = re.search(r"/(\d+)$", content_range)
    if match:
        return int(match.group(1))
    length = response.headers.get("Content-Length")
    if length and length.isdigit():
        return offset + int(length) if response.status == 206 else int(length)
    return None


def global_pct(start: int, end: int, current: int, total: int | None) -> int:
    if not total:
        return start
    fraction = min(1.0, max(0.0, current / total))
    return int(round(start + fraction * (end - start)))


def progress(key: str, start: int, end: int, label: str, current: int,
             total: int | None, force: bool = False) -> None:
    if total:
        fraction = min(100, int(current * 100 / total))
        detail = f"{human(current)} / {human(total)} ({fraction}%)"
    else:
        detail = human(current)
    pct = global_pct(start, end, current, total)
    print(f"NHSTEP|{key}|{pct}|Downloading {label} — {detail}", flush=True)


def download(args) -> None:
    target = args.output.expanduser().resolve()
    partial = target.with_suffix(target.suffix + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and digest(target) == args.sha256:
        print(f"NHSTEP|{args.progress_key}|{args.progress_end}|Have {args.label}", flush=True)
        return

    last_report = 0.0
    for attempt in range(1, args.retries + 1):
        offset = partial.stat().st_size if partial.is_file() else 0
        headers = {"User-Agent": "iProteinStudio installer"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = urllib.request.Request(args.url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=args.timeout) as response:
                append = offset > 0 and response.status == 206
                if offset and not append:
                    offset = 0
                total = total_from_headers(response, offset)
                mode = "ab" if append else "wb"
                current = offset
                progress(args.progress_key, args.progress_start, args.progress_end, args.label,
                         current, total, force=True)
                with partial.open(mode) as handle:
                    while True:
                        block = response.read(CHUNK)
                        if not block:
                            break
                        handle.write(block)
                        handle.flush()
                        current += len(block)
                        now = time.monotonic()
                        if now - last_report >= 1.0:
                            progress(args.progress_key, args.progress_start, args.progress_end, args.label,
                                     current, total)
                            last_report = now
                if total is not None and current != total:
                    raise OSError(
                        f"connection ended at {human(current)} of {human(total)}"
                    )
            if digest(partial) != args.sha256:
                partial.unlink(missing_ok=True)
                raise RuntimeError(f"checksum mismatch for {args.label}")
            os.replace(partial, target)
            progress(args.progress_key, args.progress_start, args.progress_end, args.label,
                     target.stat().st_size, target.stat().st_size, force=True)
            return
        except (TimeoutError, socket.timeout, urllib.error.URLError,
                urllib.error.HTTPError, ConnectionError, OSError) as error:
            if attempt >= args.retries:
                raise RuntimeError(
                    f"{args.label} download failed after {attempt} attempts: {error}"
                ) from error
            delay = min(15.0, 1.5 * attempt) + random.random()
            kept = partial.stat().st_size if partial.is_file() else 0
            print(
                f"NHSTEP|{args.progress_key}|{global_pct(args.progress_start, args.progress_end, kept, None)}|"
                f"Connection paused; retrying {args.label} from {human(kept)} "
                f"in {delay:.0f}s (attempt {attempt + 1}/{args.retries})",
                flush=True,
            )
            time.sleep(delay)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--progress-key", default="download")
    parser.add_argument("--progress-start", type=int, default=50)
    parser.add_argument("--progress-end", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=20)
    args = parser.parse_args()
    download(args)


if __name__ == "__main__":
    main()
