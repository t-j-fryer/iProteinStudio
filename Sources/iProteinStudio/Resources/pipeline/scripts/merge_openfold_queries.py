#!/usr/bin/env python3
"""Merge single-query OpenFold-3 JSON files into one native query batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("inputs", nargs="+", type=Path)
    args = parser.parse_args()

    merged: dict[str, object] = {"seeds": [42], "queries": {}}
    queries = merged["queries"]
    assert isinstance(queries, dict)
    for path in args.inputs:
        payload = json.loads(path.read_text())
        for name, query in payload.get("queries", {}).items():
            if name in queries:
                raise SystemExit(f"Duplicate OpenFold query name {name!r}")
            queries[name] = query
    if not queries:
        raise SystemExit("No OpenFold queries found")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(merged, indent=2) + "\n")


if __name__ == "__main__":
    main()
