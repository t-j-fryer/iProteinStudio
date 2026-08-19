#!/usr/bin/env python3
"""Write Boltz YAML inputs for a holo ligand fold or apo protein-only fold.

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
import os
from pathlib import Path

import studio_runtime


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


def default_root() -> Path:
    """Where venvs/ and src/ live.

    From the environment the app sets, else this checkout's parent -- rfd3 is
    installed inside the pipeline root. Never a hard-coded home directory:
    that is one developer's machine, not the user's.
    """
    env = os.environ.get("NANOHUNTER_ROOT") or os.environ.get("IPROTEIN_ROOT")
    if env:
        return Path(env)
    # Installed layout is <root>/rfd3/scripts/, so the root is two levels up.
    # Verify rather than assume: a standalone checkout has no venvs/ above it,
    # and silently pointing at a home directory would be worse than saying so.
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "venvs").is_dir():
        return candidate
    raise SystemExit(
        "Cannot locate the pipeline root (no venvs/ found). "
        "Set NANOHUNTER_ROOT, or pass --nanohunter-root explicitly.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequences", type=Path, required=True, help="sequences.csv or top100.csv")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["holo", "apo"], required=True)
    parser.add_argument("--smiles", required=False, help="required for --mode holo")
    parser.add_argument("--affinity", action="store_true", default=True)
    parser.add_argument("--no-affinity", dest="affinity", action="store_false")
    parser.add_argument("--nanohunter-root", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.mode == "holo" and not args.smiles:
        raise SystemExit("--smiles is required for --mode holo")

    pipeline_root = args.nanohunter_root or default_root()
    studio_runtime.configure(pipeline_root)
    nise_lib = studio_runtime

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
                nise_lib.write_boltz_yaml(yaml_path, row["sequence"], args.smiles,
                                          affinity=args.affinity)
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
