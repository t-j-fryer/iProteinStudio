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
import copy
import json
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
    if not re.fullmatch(r"[0-9a-fA-F]{64}", args.sha256):
        raise ValueError("--sha256 must be exactly 64 hexadecimal characters")
    args.sha256 = args.sha256.lower()
    if target.is_file() and digest(target) == args.sha256:
        print(f"NHSTEP|{args.progress_key}|{args.progress_end}|Have {args.label}", flush=True)
        return
    # Older installers sometimes exposed an interrupted transfer under its
    # final name. Preserve those bytes as the resumable partial instead of
    # throwing away gigabytes merely because the previous filename was wrong.
    if target.is_file():
        if not partial.exists():
            os.replace(target, partial)
        else:
            target.unlink()
    if partial.is_file() and digest(partial) == args.sha256:
        os.replace(partial, target)
        progress(args.progress_key, args.progress_start, args.progress_end, args.label,
                 target.stat().st_size, target.stat().st_size, force=True)
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
                content_range = response.headers.get("Content-Range", "")
                range_match = re.match(r"bytes\s+(\d+)-", content_range)
                if append and (not range_match or int(range_match.group(1)) != offset):
                    append = False
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
                    os.fsync(handle.fileno())
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
            if (isinstance(error, urllib.error.HTTPError) and error.code == 416
                    and partial.is_file()):
                if digest(partial) == args.sha256:
                    os.replace(partial, target)
                    progress(args.progress_key, args.progress_start, args.progress_end,
                             args.label, target.stat().st_size, target.stat().st_size,
                             force=True)
                    return
                # The saved offset is beyond or incompatible with the remote
                # object. It cannot be resumed safely; retry once from zero.
                partial.unlink()
            if attempt >= args.retries:
                raise RuntimeError(
                    f"{args.label} download failed after {attempt} attempts: {error}"
                ) from error
            delay = min(15.0, 1.5 * attempt) + random.random()
            kept = partial.stat().st_size if partial.is_file() else 0
            print(
                f"NHSTEP|{args.progress_key}|{global_pct(args.progress_start, args.progress_end, kept, None)}|"
                f"Connection paused; retrying {args.label} from {human(kept)} "
                f"in {delay:.0f}s (attempt {attempt + 1}/{args.retries}): {error}",
                flush=True,
            )
            time.sleep(delay)


def download_sources(args) -> None:
    """Try explicitly equivalent, separately checksummed serializations.

    Each source owns its partial file: different serializations must never
    share Range offsets. Existing accepted variants are reused without network.
    The receipt records a pinned source identity, not an inferred current URL.
    """
    sources = json.loads(args.sources.read_text())["sources"]
    if not sources or any(not re.fullmatch(r"[0-9a-f]{64}", s["sha256"]) for s in sources):
        raise ValueError("Every source needs a pinned SHA-256")
    target = args.output.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    actual = digest(target) if target.is_file() else None

    def finish(source, cached):
        if args.provenance:
            record = {"schema_version": 1, "url": source["url"],
                      "sha256": source["sha256"], "source": source["name"],
                      "cached": cached, "notice": source.get("notice")}
            temp = args.provenance.with_suffix(args.provenance.suffix + ".tmp")
            temp.parent.mkdir(parents=True, exist_ok=True)
            temp.write_text(json.dumps(record, indent=2) + "\n")
            os.replace(temp, args.provenance)
        print(f"NHSTEP|{args.progress_key}|{args.progress_end}|Verified {args.label} ({source['name']})", flush=True)

    for source in sources:
        if actual == source["sha256"]:
            finish(source, True)
            return
    # Do not leave an unverified file exposed under the runtime filename.
    if target.is_file():
        os.replace(target, target.with_name(target.name + ".unverified"))
    if args.provenance:
        args.provenance.unlink(missing_ok=True)
    errors = []
    for source in sources:
        attempt = copy.copy(args)
        attempt.url, attempt.sha256 = source["url"], source["sha256"]
        attempt.output = target.with_name(target.name + "." + source["sha256"])
        attempt.retries = source.get("retries", 2)
        attempt.timeout = source.get("timeout", 15)
        # Preserve resumable bytes from older single-source installers only
        # for the original serialization, never for its alternative.
        legacy = target.with_suffix(target.suffix + ".part")
        partial = attempt.output.with_suffix(attempt.output.suffix + ".part")
        if source is sources[0] and legacy.is_file() and not partial.exists():
            os.replace(legacy, partial)
        try:
            download(attempt)
        except (RuntimeError, OSError, urllib.error.URLError) as error:
            errors.append(f"{source['name']}: {error}")
            print(f"NHSTEP|{args.progress_key}|{args.progress_start}|{source['name']} unavailable or failed verification; checking remaining approved sources. {error}", flush=True)
            continue
        os.replace(attempt.output, target)
        finish(source, False)
        return
    raise RuntimeError(f"No approved source supplied a verified {args.label}: " + "; ".join(errors))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url")
    source.add_argument("--sources", type=Path, help="Manifest of approved equivalent artifacts")
    parser.add_argument("--sha256")
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--progress-key", default="download")
    parser.add_argument("--progress-start", type=int, default=50)
    parser.add_argument("--progress-end", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=20)
    args = parser.parse_args()
    if args.sources:
        download_sources(args)
    else:
        if not args.sha256:
            parser.error("--url requires --sha256")
        download(args)


if __name__ == "__main__":
    main()
