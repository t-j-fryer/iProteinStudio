#!/usr/bin/env python3
"""Repair legacy IntelliFold JAX CIF metadata containing NUL identifiers.

The original JAX converter preserved the AF3 schema's fixed-width empty model
identifier.  AF3's ModelCIF writer emitted those bytes inside a quoted software
version, which made otherwise valid coordinate files unreadable by ChimeraX and
strict mmCIF parsers.  This utility performs an atomic, metadata-only repair.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re


VERSION_LINE = re.compile(rb"(?m)^_software\.version[ \t]+.*$")
NAME_LINE = re.compile(rb"(?m)^_software\.name[ \t]+.*$")
DESCRIPTION_LINE = re.compile(rb"(?m)^_software\.description[ \t]+.*$")
MODEL_GROUP_LINE = re.compile(rb"(?m)^_ma_model_list\.model_group_name[ \t]+.*$")


def repaired_bytes(data: bytes) -> bytes:
    if b"\x00" not in data:
        return data
    data = VERSION_LINE.sub(
        b'_software.version        "IntelliFold-v2-flash JAX (legacy repaired)"',
        data,
        count=1,
    )
    data = NAME_LINE.sub(b"_software.name           IntelliFold", data, count=1)
    data = DESCRIPTION_LINE.sub(
        b'_software.description    "IntelliFold structure prediction using an AlphaFold 3-derived JAX engine"',
        data,
        count=1,
    )
    data = MODEL_GROUP_LINE.sub(
        b'_ma_model_list.model_group_name "IntelliFold-v2-flash JAX"',
        data,
        count=1,
    )
    if b"\x00" in data:
        raise ValueError("NUL bytes remain outside the expected metadata field")
    return data


def repair(path: Path, dry_run: bool = False) -> bool:
    original = path.read_bytes()
    updated = repaired_bytes(original)
    if updated == original:
        return False
    if not dry_run:
        temporary = path.with_name(f".{path.name}.repair-{os.getpid()}")
        temporary.write_bytes(updated)
        os.replace(temporary, path)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    paths = [args.root] if args.root.is_file() else sorted(args.root.rglob("*.cif"))
    changed = 0
    for path in paths:
        changed += int(repair(path, args.dry_run))
    print(f"scanned={len(paths)} repaired={changed} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
