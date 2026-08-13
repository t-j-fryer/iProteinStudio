#!/usr/bin/env python3
"""Create Boltz/IntelliFold YAMLs with no binder MSA and a cached target MSA."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import yaml


def a3m_query(path: Path) -> tuple[str, int]:
    records = [record for record in path.read_text().split(">") if record.strip()]
    if not records:
        raise ValueError(f"No A3M records in {path}")
    sequence = "".join(records[0].splitlines()[1:])
    query = "".join(c for c in sequence if not c.islower() and c not in "-.").upper()
    return query, len(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sequences", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-msa", type=Path)
    args = parser.parse_args()

    template = yaml.safe_load(args.template.read_text())
    entries = template.get("sequences", [])
    proteins = [entry["protein"] for entry in entries if "protein" in entry]
    ligands = [entry["ligand"] for entry in entries if "ligand" in entry]
    if not proteins or proteins[0].get("id") != "A":
        raise SystemExit("Template must contain binder protein chain A first")
    target_protein = proteins[1] if len(proteins) > 1 else None
    if bool(target_protein) == bool(ligands):
        raise SystemExit("Template must contain exactly one protein target or one ligand target")

    target_msa = None
    msa_records = 0
    if target_protein:
        if args.target_msa is None:
            raise SystemExit("Protein target requires --target-msa")
        target_msa = args.target_msa.resolve()
        if not target_msa.exists():
            raise SystemExit(f"Target MSA does not exist: {target_msa}")
        query, msa_records = a3m_query(target_msa)
        target_sequence = str(target_protein.get("sequence", "")).upper()
        if query != target_sequence:
            raise SystemExit(
                f"Target MSA query mismatch: query length {len(query)}, target length {len(target_sequence)}"
            )

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(args.sequences.open()))
    for row in rows:
        data = json.loads(json.dumps(template))
        data["sequences"][0]["protein"]["sequence"] = row["sequence"]
        data["sequences"][0]["protein"]["msa"] = "empty"
        if target_protein:
            for entry in data["sequences"][1:]:
                if "protein" in entry:
                    entry["protein"]["msa"] = str(target_msa)
        (output / f"{row['design']}.yaml").write_text(yaml.safe_dump(data, sort_keys=False))

    manifest = {
        "template": str(args.template.resolve()),
        "sequences_csv": str(args.sequences.resolve()),
        "num_designs": len(rows),
        "target_type": "protein" if target_protein else "ligand",
        "binder_msa": "empty",
        "target_msa": str(target_msa) if target_msa else None,
        "target_msa_records": msa_records,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {len(rows)} predictor YAMLs -> {output}")


if __name__ == "__main__":
    main()
