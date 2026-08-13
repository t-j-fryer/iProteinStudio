#!/usr/bin/env python3
"""Write Boltz YAML inputs for the holo (ligand + affinity) or apo (protein-only) fold.

Holo mode reuses ``nise_lib.write_boltz_yaml`` unchanged (protein A + ligand
B, empty MSA, ``properties: affinity: {binder: B}``) -- the exact YAML shape
NISE folds with. Apo mode has no NISE precedent (NISE never folds without its
ligand), so it's a small local variant: protein-only, no ligand entry, no
affinity block, so Boltz-2's affinity module and pocket-constraint logic never
engage. Both are folded unconstrained (no pocket constraint) -- RFD3's
diffusion-time hotspot/exposed/buried conditioning already did the geometric
biasing; constraining Boltz at fold time would inflate confidence for designs
that don't actually reproduce that geometry on their own.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def write_apo_yaml(path: Path, sequence: str) -> None:
    lines = [
        "sequences:",
        "  - protein:",
        "      id: A",
        f"      sequence: {sequence}",
        "      msa: empty",
        "version: 1",
        "",
    ]
    path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequences", type=Path, required=True, help="sequences.csv or top100.csv")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["holo", "apo"], required=True)
    parser.add_argument("--smiles", required=False, help="required for --mode holo")
    parser.add_argument("--nanohunter-root", type=Path, default=Path("/Users/thomasfryer/NanoHunter"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.mode == "holo" and not args.smiles:
        raise SystemExit("--smiles is required for --mode holo")

    nise_dir = args.nanohunter_root.resolve() / "scripts" / "nise"
    sys.path.insert(0, str(nise_dir))
    import nise_lib  # noqa: E402

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(args.sequences.open()))
    if not rows:
        raise SystemExit(f"No rows in {args.sequences}")

    manifest = {}
    for row in rows:
        name = f"{row['design']}_{row['seq_index']}"
        yaml_path = output / f"{name}.yaml"
        if args.overwrite or not yaml_path.exists():
            if args.mode == "holo":
                nise_lib.write_boltz_yaml(yaml_path, row["sequence"], args.smiles, affinity=True)
            else:
                write_apo_yaml(yaml_path, row["sequence"])
        manifest[name] = {
            "design": row["design"], "seq_index": row["seq_index"],
            "sequence": row["sequence"], "backbone_pdb": row.get("backbone_pdb", ""),
            "yaml": str(yaml_path),
        }

    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {len(manifest)} {args.mode} YAMLs -> {output}")


if __name__ == "__main__":
    main()
