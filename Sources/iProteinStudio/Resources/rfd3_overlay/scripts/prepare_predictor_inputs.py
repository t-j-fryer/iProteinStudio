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


def prediction_name(row: dict) -> str:
    design = row["design"]
    index = str(row.get("seq_index", "")).strip()
    return f"{design}_{index}" if index else design


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sequences", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-msa", type=Path)
    parser.add_argument("--target-msa-map", type=Path,
                        help="JSON object mapping each target chain ID to its exact A3M")
    parser.add_argument("--monomer", action="store_true",
                        help="binder-only prediction: template contains only chain A")
    args = parser.parse_args()

    template = yaml.safe_load(args.template.read_text())
    entries = template.get("sequences", [])
    proteins = [entry["protein"] for entry in entries if "protein" in entry]
    ligands = [entry["ligand"] for entry in entries if "ligand" in entry]
    if not proteins or proteins[0].get("id") != "A":
        raise SystemExit("Template must contain binder protein chain A first")
    target_proteins = proteins[1:]
    if not args.monomer and bool(target_proteins) == bool(ligands):
        raise SystemExit("Template must contain one or more protein targets, or one ligand target")
    if args.monomer and (target_proteins or ligands or len(proteins) != 1):
        raise SystemExit("--monomer requires a template containing only binder chain A")

    target_msas = {}
    msa_records = {}
    if target_proteins:
        if args.target_msa_map:
            try:
                raw_map = json.loads(args.target_msa_map.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise SystemExit(f"Could not read target MSA map: {exc}")
        elif args.target_msa and len(target_proteins) == 1:
            raw_map = {str(target_proteins[0].get("id", "B")): str(args.target_msa)}
        else:
            raise SystemExit("Protein targets require one exact MSA path per target chain")
        expected = {str(protein.get("id", "")) for protein in target_proteins}
        if set(raw_map) != expected:
            raise SystemExit(f"Target MSA map chains {sorted(raw_map)} do not match template chains {sorted(expected)}")
        for target_protein in target_proteins:
            chain = str(target_protein.get("id", ""))
            target_msa = Path(raw_map[chain]).resolve()
            if not target_msa.exists():
                raise SystemExit(f"Target MSA does not exist for chain {chain}: {target_msa}")
            query, records = a3m_query(target_msa)
            target_sequence = str(target_protein.get("sequence", "")).upper()
            if query != target_sequence:
                raise SystemExit(
                    f"Target MSA query mismatch for chain {chain}: query length {len(query)}, target length {len(target_sequence)}"
                )
            target_msas[chain] = target_msa
            msa_records[chain] = records

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(args.sequences.open()))
    for row in rows:
        data = json.loads(json.dumps(template))
        data["sequences"][0]["protein"]["sequence"] = row["sequence"]
        data["sequences"][0]["protein"]["msa"] = "empty"
        if target_proteins:
            for entry in data["sequences"][1:]:
                if "protein" in entry:
                    chain = str(entry["protein"].get("id", ""))
                    entry["protein"]["msa"] = str(target_msas[chain])
        (output / f"{prediction_name(row)}.yaml").write_text(yaml.safe_dump(data, sort_keys=False))

    manifest = {
        "template": str(args.template.resolve()),
        "sequences_csv": str(args.sequences.resolve()),
        "num_designs": len(rows),
        "target_type": "monomer" if args.monomer else ("protein" if target_proteins else "ligand"),
        "binder_msa": "empty",
        "target_msas": {chain: str(path) for chain, path in target_msas.items()},
        "target_msa_records": msa_records,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {len(rows)} predictor YAMLs -> {output}")


if __name__ == "__main__":
    main()
