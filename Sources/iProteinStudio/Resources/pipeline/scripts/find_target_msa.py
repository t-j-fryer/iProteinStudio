#!/usr/bin/env python3
"""Find the deepest real A3M whose query exactly matches a protein sequence."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


def canonical(sequence: str) -> str:
    return re.sub(r"[^A-Za-z]", "", sequence).upper()


def a3m_metadata(path: Path) -> tuple[str, int]:
    text = path.read_text(errors="ignore").replace("\x00", "")
    records = [record for record in text.split(">") if record.strip()]
    if not records:
        return "", 0
    body = "".join(records[0].splitlines()[1:])
    query = "".join(ch for ch in body if not ch.islower() and ch not in ".-").upper()
    return query, len(records)


def find_exact(sequence: str, roots: list[Path], limit: int = 40000) -> Path | None:
    target = canonical(sequence)
    best: tuple[int, Path] | None = None
    seen: set[Path] = set()
    scanned = 0
    for root in roots:
        if not root.is_dir():
            continue
        for directory, _, files in os.walk(root):
            for name in files:
                if not name.lower().endswith(".a3m"):
                    continue
                path = Path(directory) / name
                try:
                    resolved = path.resolve()
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    query, depth = a3m_metadata(path)
                except OSError:
                    continue
                scanned += 1
                if query == target and depth >= 2 and (best is None or depth > best[0]):
                    best = (depth, resolved)
                if scanned >= limit:
                    break
            if scanned >= limit:
                break
        if scanned >= limit:
            break
    return best[1] if best else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sequence", required=True)
    parser.add_argument("--roots", required=True,
                        help="Colon-separated alignment search roots")
    parser.add_argument("--limit", type=int, default=40000)
    args = parser.parse_args()
    roots = [Path(item).expanduser() for item in args.roots.split(":") if item]
    match = find_exact(args.sequence, roots, max(1, args.limit))
    if match:
        print(match)


if __name__ == "__main__":
    main()
