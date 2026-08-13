#!/usr/bin/env python3
"""Extract the aCbx target chain from a NanoHunter calibration PDB."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


DEFAULT_SOURCE = Path(
    os.environ.get("ACBX_SOURCE_PDB", "")
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=(DEFAULT_SOURCE or None),
                        required=not DEFAULT_SOURCE)
    parser.add_argument("--source-chain", default="B")
    parser.add_argument("--output", type=Path, default=Path("assets/acbx/aCbx_target.pdb"))
    args = parser.parse_args()
    lines = [
        line
        for line in args.source.read_text().splitlines()
        if line.startswith("ATOM") and line[21:22] == args.source_chain
    ]
    residues = {(line[22:26], line[26:27]) for line in lines}
    if len(residues) != 71:
        raise SystemExit(f"Expected 71 aCbx residues, found {len(residues)}")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines + ["TER", "END"]) + "\n")
    print(f"wrote {len(lines)} atoms / {len(residues)} residues -> {output}")


if __name__ == "__main__":
    main()
