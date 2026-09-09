#!/usr/bin/env python3
"""Record backbone-distance diagnostics; reject only unusable coordinates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
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


def inspect_geometry(path: Path) -> dict:
    """Keep advisory distance violations separate from coordinate input errors."""
    try:
        residues = read_residues(path)
    except (OSError, ValueError) as exc:
        return {"violations": [], "errors": [f"could not parse coordinates: {exc}"]}
    violations: list[dict] = []
    errors: list[str] = []
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
            pairs = [("CA-CA", ca_distance, MAX_CA_CA)]
            carbon, nitrogen = previous_atoms.get("C"), atoms.get("N")
            if carbon is not None and nitrogen is not None:
                pairs.append(("C-N", math.dist(carbon, nitrogen), MAX_PEPTIDE_CN))
            for atoms_name, distance, threshold in pairs:
                if distance > threshold:
                    violations.append({
                        "model": model, "chain": chain,
                        "residue_1": previous_id, "residue_2": residue_id,
                        "atoms": atoms_name, "distance_angstrom": distance,
                        "threshold_angstrom": threshold,
                        "message": f"{chain}:{previous_id}-{residue_id} {atoms_name}={distance:.2f} A (>{threshold:.1f})",
                    })
        previous_by_chain[(model, chain)] = (key, atoms)
    if protein_residues == 0:
        errors.append("contains no protein alpha-carbon atoms")
    return {"violations": violations, "errors": errors}


def validate(path: Path) -> list[str]:
    """Diagnostic compatibility API for historical audits; does not reject output."""
    result = inspect_geometry(path)
    return result["errors"] + [v["message"] for v in result["violations"]]



def discover_structures(path: Path) -> list[Path]:
    """Find predictor outputs without treating staged coordinate inputs as results.

    Plain Predict stages YAML inputs in ``_inputs``. IntelliFold also writes its
    canonical predictions below ``_inputs/predictions`` because its upstream
    output layout includes the input-directory name. The old blanket exclusion
    of every path containing ``_inputs`` therefore rejected successful
    IntelliFold runs after inference. Keep excluding arbitrary staged structures,
    but admit the upstream predictor's explicit results subtree.
    """
    if path.is_file():
        return [path]
    structures: list[Path] = []
    for pattern in ("*.cif", "*.pdb"):
        for candidate in path.rglob(pattern):
            relative_parts = candidate.relative_to(path).parts
            if ".prediction_resume" in relative_parts:
                # Interrupted items are retained for audit, not predictions.
                continue
            if "_inputs" in relative_parts:
                input_index = relative_parts.index("_inputs")
                if (input_index + 1 >= len(relative_parts)
                        or relative_parts[input_index + 1] != "predictions"):
                    continue
            structures.append(candidate)
    return sorted(structures)


def write_report(path: Path, report_path: Path | None = None) -> dict:
    """Write one atomic, hash-linked report without changing any coordinates."""
    # Keep the supplied path (including a normalized output symlink) in the report.
    path = path.absolute()
    directory = path.parent if path.is_file() else path
    destination = report_path or directory / "geometry_report.json"
    structures = discover_structures(path)
    records = []
    for structure in structures:
        record = inspect_geometry(structure)
        record.update(path=str(structure.relative_to(directory)),
                      sha256=hashlib.sha256(structure.read_bytes()).hexdigest())
        records.append(record)
    errors = [] if structures else ["No predicted structures found"]
    report = {
        "schema_version": 1, "policy": "record_only",
        "thresholds_angstrom": {"CA-CA": MAX_CA_CA, "C-N": MAX_PEPTIDE_CN},
        "structures": records, "errors": errors,
        "violation_count": sum(len(r["violations"]) for r in records),
        "error_count": len(errors) + sum(len(r["errors"]) for r in records),
    }
    report["coordinate_input_usable"] = report["error_count"] == 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".geometry-", dir=destination.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = write_report(args.path, args.report)
    for record in report["structures"]:
        for violation in record["violations"]:
            print(f"IPROTEINSTUDIO_GEOMETRY_WARNING|{record['path']}|{violation['message']}", flush=True)
    print(f"IPROTEINSTUDIO_GEOMETRY_RECORDED|policy=record_only|violations={report['violation_count']}|errors={report['error_count']}", flush=True)
    if not report["coordinate_input_usable"]:
        errors = report["errors"] + [f"{r['path']}: {e}" for r in report["structures"] for e in r["errors"]]
        raise SystemExit("Unusable prediction coordinates: " + "; ".join(errors))


if __name__ == "__main__":
    main()
