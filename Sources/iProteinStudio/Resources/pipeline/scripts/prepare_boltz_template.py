#!/usr/bin/env python3
"""Normalize a user PDB/mmCIF into a Boltz-compatible template mmCIF.

Boltz advertises PDB templates, but its PDB-to-mmCIF path can receive an empty
polymer sequence when an atom-only PDB has no SEQRES records. Preserve the
user's original file separately for provenance and add only missing entity
sequences to this derived prediction input.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import gemmi


def observed_sequence(structure: gemmi.Structure, subchains: set[str]) -> list[str]:
    sequence: list[str] = []
    seen: set[tuple[str, int, str]] = set()
    if not structure:
        return sequence
    for chain in structure[0]:
        for residue in chain:
            if residue.subchain not in subchains:
                continue
            info = gemmi.find_tabulated_residue(residue.name)
            if not info.is_amino_acid():
                continue
            key = (chain.name, residue.seqid.num, residue.seqid.icode)
            if key in seen:
                continue
            seen.add(key)
            sequence.append(residue.name)
    return sequence


def normalize(source: Path, destination: Path) -> None:
    try:
        structure = gemmi.read_structure(str(source))
    except Exception as exc:
        raise SystemExit(f"Could not read target template {source}: {exc}") from exc
    if len(structure) == 0:
        raise SystemExit(f"Target template contains no structural model: {source}")

    structure.setup_entities()
    protein_entities = 0
    for entity in structure.entities:
        if entity.entity_type != gemmi.EntityType.Polymer:
            continue
        if entity.polymer_type not in {gemmi.PolymerType.PeptideL, gemmi.PolymerType.PeptideD}:
            continue
        protein_entities += 1
        if not entity.full_sequence:
            sequence = observed_sequence(structure, set(entity.subchains))
            if not sequence:
                raise SystemExit(
                    f"Could not derive a protein sequence for template entity {entity.name!r}."
                )
            entity.full_sequence = sequence
    if protein_entities == 0:
        raise SystemExit("Target template contains no protein polymer chain.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.part")
    structure.make_mmcif_document().write_file(str(temporary))
    os.replace(temporary, destination)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    normalize(args.source.resolve(), args.destination.resolve())


if __name__ == "__main__":
    main()
