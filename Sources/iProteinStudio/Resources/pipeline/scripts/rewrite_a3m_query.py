#!/usr/bin/env python3
"""Replace the first A3M record with an exact query and retain support rows."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def read_records(path: Path) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    header: str | None = None
    sequence: list[str] = []
    for raw in path.read_text(errors="ignore").replace("\x00", "").splitlines():
        if raw.startswith(">"):
            if header is not None:
                records.append((header, "".join(sequence)))
            header = raw[1:].strip() or "sequence"
            sequence = []
        elif raw.strip():
            sequence.append(raw.strip())
    if header is not None:
        records.append((header, "".join(sequence)))
    if not records:
        raise ValueError(f"A3M contains no records: {path}")
    return records


def rewrite_query(input_path: Path, output_path: Path, query: str) -> None:
    query = re.sub(r"[^A-Za-z]", "", query).upper()
    if not query:
        raise ValueError("Query sequence is empty")
    records = read_records(input_path)
    records[0] = ("query", query)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as handle:
        for header, sequence in records:
            handle.write(f">{header}\n{sequence}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--query", required=True)
    args = parser.parse_args()
    rewrite_query(args.input, args.output, args.query)


if __name__ == "__main__":
    main()
