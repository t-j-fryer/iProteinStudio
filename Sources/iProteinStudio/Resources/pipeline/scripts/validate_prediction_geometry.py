#!/usr/bin/env python3
"""Reject chemically discontinuous protein coordinates without extra packages."""

from __future__ import annotations

import argparse
from collections import OrderedDict
import math
from pathlib import Path
import shlex

MAX_CA_CA = 4.5
MAX_PEPTIDE_CN = 2.2
AMINO_ACIDS = {
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    "ASX", "GLX", "SEC", "PYL", "MSE", "UNK",
}

Atom = tuple[float, float, float]
ResidueKey = tuple[str, str, str]


def number(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"non-finite coordinate {value!r}")
    return result


def read_pdb(path: Path) -> OrderedDict[ResidueKey, dict[str, Atom]]:
    residues: OrderedDict[ResidueKey, dict[str, Atom]] = OrderedDict()
    model = "1"
    for raw in path.read_text(errors="replace").splitlines():
        if raw.startswith("MODEL"):
            model = raw[10:14].strip() or "1"
            continue
        if not raw.startswith(("ATOM  ", "HETATM")) or len(raw) < 54:
            continue
        residue_name = raw[17:20].strip().upper()
        if residue_name not in AMINO_ACIDS or raw[16:17] not in (" ", ".", "A"):
            continue
        atom_name = raw[12:16].strip().upper()
        chain = raw[21:22].strip() or "?"
        residue_id = (raw[22:26].strip() + raw[26:27].strip()) or "?"
        residues.setdefault((model, chain, residue_id), {})[atom_name] = (
            number(raw[30:38]), number(raw[38:46]), number(raw[46:54])
        )
    return residues


def cif_atom_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    """Read a possibly line-wrapped atom_site loop from predictor mmCIF."""
    lines = path.read_text(errors="replace").splitlines()
    index = 0
    while index < len(lines):
        if lines[index].strip() != "loop_":
            index += 1
            continue
        index += 1
        columns: list[str] = []
        while index < len(lines) and lines[index].strip().startswith("_"):
            columns.append(lines[index].strip())
            index += 1
        if not columns or not all(column.startswith("_atom_site.") for column in columns):
            continue
        rows: list[list[str]] = []
        pending: list[str] = []
        while index < len(lines):
            stripped = lines[index].strip()
            if not stripped or stripped.startswith("#"):
                if pending:
                    raise ValueError("incomplete _atom_site row")
                break
            if stripped == "loop_" or stripped.startswith("_") or stripped.startswith("data_"):
                if pending:
                    raise ValueError("incomplete _atom_site row")
                break
            pending.extend(shlex.split(stripped, comments=False, posix=True))
            while len(pending) >= len(columns):
                rows.append(pending[:len(columns)])
                pending = pending[len(columns):]
            index += 1
        return columns, rows
    raise ValueError("contains no _atom_site loop")


def read_cif(path: Path) -> OrderedDict[ResidueKey, dict[str, Atom]]:
    columns, rows = cif_atom_rows(path)
    lookup = {name.removeprefix("_atom_site."): position
              for position, name in enumerate(columns)}

    def field(row: list[str], *names: str, default: str = "") -> str:
        for name in names:
            if name in lookup:
                value = row[lookup[name]]
                if value not in (".", "?"):
                    return value
        return default

    if any(name not in lookup for name in ("Cartn_x", "Cartn_y", "Cartn_z")):
        raise ValueError("_atom_site loop has no Cartesian coordinates")
    residues: OrderedDict[ResidueKey, dict[str, Atom]] = OrderedDict()
    for row in rows:
        if field(row, "group_PDB", default="ATOM").upper() not in ("ATOM", "HETATM"):
            continue
        residue_name = field(row, "auth_comp_id", "label_comp_id").upper()
        alt = field(row, "label_alt_id", "auth_alt_id", default=".")
        if residue_name not in AMINO_ACIDS or alt not in (".", "?", "A"):
            continue
        model = field(row, "pdbx_PDB_model_num", default="1")
        chain = field(row, "auth_asym_id", "label_asym_id", default="?")
        residue_id = field(row, "auth_seq_id", "label_seq_id", default="?")
        residue_id += field(row, "pdbx_PDB_ins_code")
        atom_name = field(row, "auth_atom_id", "label_atom_id").upper()
        residues.setdefault((model, chain, residue_id), {})[atom_name] = (
            number(row[lookup["Cartn_x"]]), number(row[lookup["Cartn_y"]]),
            number(row[lookup["Cartn_z"]]),
        )
    return residues


def read_residues(path: Path) -> OrderedDict[ResidueKey, dict[str, Atom]]:
    return read_pdb(path) if path.suffix.lower() == ".pdb" else read_cif(path)


def validate(path: Path) -> list[str]:
    try:
        residues = read_residues(path)
    except (OSError, ValueError) as exc:
        return [f"could not parse coordinates: {exc}"]
    failures: list[str] = []
    previous_by_chain: dict[tuple[str, str], tuple[ResidueKey, dict[str, Atom]]] = {}
    protein_residues = 0
    for key, atoms in residues.items():
        model, chain, residue_id = key
        ca = atoms.get("CA")
        if ca is None:
            continue
        protein_residues += 1
        previous = previous_by_chain.get((model, chain))
        if previous is not None:
            previous_key, previous_atoms = previous
            previous_id = previous_key[2]
            ca_distance = math.dist(previous_atoms["CA"], ca)
            if ca_distance > MAX_CA_CA:
                failures.append(
                    f"{chain}:{previous_id}-{residue_id} CA-CA={ca_distance:.2f} A "
                    f"(>{MAX_CA_CA:.1f})"
                )
            carbon, nitrogen = previous_atoms.get("C"), atoms.get("N")
            if carbon is not None and nitrogen is not None:
                peptide = math.dist(carbon, nitrogen)
                if peptide > MAX_PEPTIDE_CN:
                    failures.append(
                        f"{chain}:{previous_id}-{residue_id} C-N={peptide:.2f} A "
                        f"(>{MAX_PEPTIDE_CN:.1f})"
                    )
        previous_by_chain[(model, chain)] = (key, atoms)
    if protein_residues == 0:
        failures.append("contains no protein alpha-carbon atoms")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    path = args.path.resolve()
    structures = [path] if path.is_file() else sorted(
        candidate for pattern in ("*.cif", "*.pdb") for candidate in path.rglob(pattern)
        if "_inputs" not in candidate.parts
    )
    if not structures:
        raise SystemExit(f"Geometry validation found no structures under {path}")
    all_failures = [f"{structure}: {failure}" for structure in structures
                    for failure in validate(structure)]
    if all_failures:
        preview = "\n".join(all_failures[:20])
        suffix = "" if len(all_failures) <= 20 else f"\n... {len(all_failures) - 20} more"
        raise SystemExit(
            "Predictor returned invalid protein geometry; output was rejected.\n"
            + preview + suffix
        )
    print(f"IPROTEINSTUDIO_GEOMETRY_OK|structures={len(structures)}")


if __name__ == "__main__":
    main()
