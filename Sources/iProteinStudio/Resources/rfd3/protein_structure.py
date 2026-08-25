#!/usr/bin/env python3
"""Small dependency-free PDB/mmCIF reader for Studio's protein target handoff."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex


@dataclass(frozen=True)
class ProteinAtom:
    atom: str
    residue: str
    chain: str
    residue_number: int
    x: float
    y: float
    z: float
    element: str
    b_factor: float = 0.0
    occupancy: float = 1.0


def _first_index(columns: list[str], *names: str) -> int:
    for name in names:
        if name in columns:
            return columns.index(name)
    raise ValueError(f"mmCIF atom_site table lacks {names[0]}")


def _read_mmcif(path: Path) -> list[ProteinAtom]:
    lines = path.read_text(errors="replace").splitlines()
    atoms: list[ProteinAtom] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() != "loop_":
            index += 1
            continue
        index += 1
        columns = []
        while index < len(lines) and lines[index].lstrip().startswith("_"):
            columns.append(lines[index].split()[0])
            index += 1
        if not columns or not columns[0].startswith("_atom_site."):
            continue
        group_i = _first_index(columns, "_atom_site.group_PDB")
        atom_i = _first_index(columns, "_atom_site.auth_atom_id", "_atom_site.label_atom_id")
        residue_i = _first_index(columns, "_atom_site.auth_comp_id", "_atom_site.label_comp_id")
        chain_i = _first_index(columns, "_atom_site.auth_asym_id", "_atom_site.label_asym_id")
        number_i = _first_index(columns, "_atom_site.auth_seq_id", "_atom_site.label_seq_id")
        x_i = _first_index(columns, "_atom_site.Cartn_x")
        y_i = _first_index(columns, "_atom_site.Cartn_y")
        z_i = _first_index(columns, "_atom_site.Cartn_z")
        element_i = _first_index(columns, "_atom_site.type_symbol")
        b_i = columns.index("_atom_site.B_iso_or_equiv") if "_atom_site.B_iso_or_equiv" in columns else None
        occupancy_i = columns.index("_atom_site.occupancy") if "_atom_site.occupancy" in columns else None
        model_i = columns.index("_atom_site.pdbx_PDB_model_num") if "_atom_site.pdbx_PDB_model_num" in columns else None
        alt_i = columns.index("_atom_site.label_alt_id") if "_atom_site.label_alt_id" in columns else None
        while index < len(lines):
            raw = lines[index].strip()
            if not raw or raw.startswith("#") or raw == "loop_" or raw.startswith("_"):
                break
            fields = shlex.split(raw, comments=False, posix=True)
            index += 1
            if len(fields) != len(columns) or fields[group_i] != "ATOM":
                continue
            if model_i is not None and fields[model_i] not in {"1", ".", "?"}:
                continue
            if alt_i is not None and fields[alt_i] not in {".", "?", "A"}:
                continue
            try:
                atoms.append(ProteinAtom(
                    atom=fields[atom_i], residue=fields[residue_i],
                    chain=fields[chain_i] if fields[chain_i] not in {".", "?"} else "A",
                    residue_number=int(float(fields[number_i])),
                    x=float(fields[x_i]), y=float(fields[y_i]), z=float(fields[z_i]),
                    element=fields[element_i].upper(),
                    b_factor=float(fields[b_i]) if b_i is not None else 0.0,
                    occupancy=float(fields[occupancy_i]) if occupancy_i is not None else 1.0,
                ))
            except (ValueError, IndexError):
                continue
        return atoms
    return atoms


def _read_pdb(path: Path) -> list[ProteinAtom]:
    atoms = []
    for line in path.read_text(errors="replace").splitlines():
        if not line.startswith("ATOM") or (len(line) > 16 and line[16] not in {" ", "A"}):
            continue
        try:
            atoms.append(ProteinAtom(
                atom=line[12:16].strip(), residue=line[17:20].strip(),
                chain=line[21].strip() or "A", residue_number=int(line[22:26]),
                x=float(line[30:38]), y=float(line[38:46]), z=float(line[46:54]),
                occupancy=float(line[54:60] or 1.0), b_factor=float(line[60:66] or 0.0),
                element=(line[76:78].strip() or line[12:16].strip()[:1]).upper(),
            ))
        except (ValueError, IndexError):
            continue
    return atoms


def read_protein_atoms(path: str | Path) -> list[ProteinAtom]:
    source = Path(path)
    return _read_mmcif(source) if source.suffix.lower() in {".cif", ".mmcif"} else _read_pdb(source)


def write_selected_pdb(source: str | Path, destination: str | Path,
                       chain_map: dict[str, str]) -> Path:
    """Materialize selected target chains under backend-safe one-letter IDs."""
    atoms = [atom for atom in read_protein_atoms(source) if atom.chain in chain_map]
    present = {atom.chain for atom in atoms}
    missing = [chain for chain in chain_map if chain not in present]
    if missing:
        raise ValueError(f"Selected chain(s) absent from target structure: {', '.join(missing)}")
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for serial, atom in enumerate(atoms, 1):
        name = atom.atom[:4]
        atom_field = f" {name:<3}" if len(name) < 4 else name
        lines.append(
            f"ATOM  {serial:5d} {atom_field} {atom.residue[:3]:>3} {chain_map[atom.chain]}"
            f"{atom.residue_number:4d}    {atom.x:8.3f}{atom.y:8.3f}{atom.z:8.3f}"
            f"{atom.occupancy:6.2f}{atom.b_factor:6.2f}          {atom.element[:2]:>2}"
        )
    lines.append("END")
    output.write_text("\n".join(lines) + "\n")
    return output
