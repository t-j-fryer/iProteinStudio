#!/usr/bin/env python3
"""Normalize unknown residues before an iterative inverse-folding handoff.

Protenix represents an unknown amino acid with alanine backbone/CB coordinates plus
a generic CG pseudo-atom.  Renaming that residue to ALA without removing CG creates
an invalid ALA-CG record.  This module performs a chain-aware Protenix repair while
retaining the legacy placeholder substitution for predictors whose UNK records do
not contain the pseudo-atom.
"""

from __future__ import annotations

import argparse
import random
import re
import shlex
from pathlib import Path
from typing import Callable, Iterable


PROTENIX_PREDICTORS = {"protenix-v2", "protenix-mini"}
PROTENIX_ALA_ATOMS = {"N", "CA", "C", "O", "CB", "OXT"}
REQUIRED_ALA_ATOMS = {"N", "CA", "C", "O", "CB"}


class CifLoop:
    def __init__(
        self,
        start: int,
        end: int,
        data_start: int,
        data_end: int,
        tags: list[str],
        rows: list[list[str]],
    ) -> None:
        self.start = start
        self.end = end
        self.data_start = data_start
        self.data_end = data_end
        self.tags = tags
        self.rows = rows

    @property
    def category(self) -> str:
        return self.tags[0].split(".", 1)[0] if self.tags else ""

    def index(self, *names: str) -> int | None:
        lowered = {tag.lower(): i for i, tag in enumerate(self.tags)}
        for name in names:
            full = name.lower()
            if not full.startswith("_"):
                full = f"{self.category}.{full}"
            if full in lowered:
                return lowered[full]
        return None


def _tokenize_rows(lines: list[str], width: int, category: str) -> list[list[str]]:
    tokens: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(";"):
            raise ValueError(
                f"Unsupported multiline value in {category}; refusing to rewrite CIF"
            )
        tokens.extend(shlex.split(line, comments=False, posix=True))
    if len(tokens) % width:
        raise ValueError(
            f"Malformed {category} loop: {len(tokens)} values for {width} columns"
        )
    return [tokens[i:i + width] for i in range(0, len(tokens), width)]


def parse_loops(lines: list[str]) -> list[CifLoop]:
    loops: list[CifLoop] = []
    i = 0
    while i < len(lines):
        if lines[i].strip().lower() != "loop_":
            i += 1
            continue
        start = i
        i += 1
        tags: list[str] = []
        while i < len(lines) and lines[i].lstrip().startswith("_"):
            tags.append(lines[i].strip().split()[0])
            i += 1
        data_start = i
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped == "#" or stripped.lower() == "loop_":
                break
            if stripped.startswith("_") or stripped.lower().startswith(("data_", "save_")):
                break
            i += 1
        data_end = i
        if tags:
            category = tags[0].split(".", 1)[0]
            if all(tag.split(".", 1)[0] == category for tag in tags):
                loops.append(CifLoop(
                    start=start,
                    end=i,
                    data_start=data_start,
                    data_end=data_end,
                    tags=tags,
                    rows=_tokenize_rows(lines[data_start:data_end], len(tags), category),
                ))
    return loops


def _quote(value: str) -> str:
    if value in {".", "?"} or re.fullmatch(r"[A-Za-z0-9_+.,:/()\-]+", value):
        return value
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    raise ValueError(f"Cannot safely serialize CIF value containing both quote types: {value!r}")


def _render_rows(rows: Iterable[list[str]]) -> list[str]:
    return [" ".join(_quote(value) for value in row) + "\n" for row in rows]


def _value(row: list[str], index: int | None) -> str:
    return row[index].strip() if index is not None else ""


def _replace_unk(row: list[str], indices: Iterable[int | None], replacement: str) -> None:
    for index in indices:
        if index is not None and row[index].upper() == "UNK":
            row[index] = replacement


def normalize_protenix(
    text: str,
    binder_chain: str,
) -> tuple[str, int, int]:
    """Return a chain-aware Protenix repair and residue/atom counts."""
    lines = text.splitlines(keepends=True)
    loops = parse_loops(lines)
    atom_loop = next((loop for loop in loops if loop.category.lower() == "_atom_site"), None)
    if atom_loop is None:
        raise ValueError("No _atom_site loop found in Protenix CIF")

    label_chain_i = atom_loop.index("label_asym_id")
    auth_chain_i = atom_loop.index("auth_asym_id")
    label_comp_i = atom_loop.index("label_comp_id")
    auth_comp_i = atom_loop.index("auth_comp_id")
    label_atom_i = atom_loop.index("label_atom_id")
    auth_atom_i = atom_loop.index("auth_atom_id")
    entity_i = atom_loop.index("label_entity_id")
    label_seq_i = atom_loop.index("label_seq_id")
    auth_seq_i = atom_loop.index("auth_seq_id")
    model_i = atom_loop.index("pdbx_PDB_model_num")
    insertion_i = atom_loop.index("pdbx_PDB_ins_code")

    required = {
        "chain": label_chain_i if label_chain_i is not None else auth_chain_i,
        "component": label_comp_i if label_comp_i is not None else auth_comp_i,
        "atom": label_atom_i if label_atom_i is not None else auth_atom_i,
        "sequence": auth_seq_i if auth_seq_i is not None else label_seq_i,
    }
    missing = [name for name, index in required.items() if index is None]
    if missing:
        raise ValueError(f"Protenix _atom_site loop is missing: {', '.join(missing)}")

    binder_chain = binder_chain.strip()
    if not binder_chain:
        raise ValueError("Binder chain must not be empty")

    targeted_atoms: dict[tuple[str, ...], set[str]] = {}
    targeted_entities: set[str] = set()
    kept_rows: list[list[str]] = []
    removed_cg = 0

    for original in atom_loop.rows:
        row = list(original)
        chains = {_value(row, label_chain_i), _value(row, auth_chain_i)} - {"", ".", "?"}
        comps = {_value(row, label_comp_i).upper(), _value(row, auth_comp_i).upper()} - {""}
        if binder_chain not in chains or "UNK" not in comps:
            kept_rows.append(row)
            continue

        atom = (_value(row, auth_atom_i) or _value(row, label_atom_i)).upper()
        residue_key = (
            _value(row, model_i) or "1",
            binder_chain,
            _value(row, auth_seq_i) or _value(row, label_seq_i),
            _value(row, insertion_i) or ".",
        )
        targeted_atoms.setdefault(residue_key, set()).add(atom)
        entity = _value(row, entity_i)
        if entity not in {"", ".", "?"}:
            targeted_entities.add(entity)

        if atom == "CG":
            removed_cg += 1
            continue
        if atom not in PROTENIX_ALA_ATOMS:
            raise ValueError(
                f"Unexpected Protenix UNK atom {atom!r} on chain {binder_chain} "
                f"residue {residue_key[2]}; refusing to create an invalid alanine"
            )
        _replace_unk(row, (label_comp_i, auth_comp_i), "ALA")
        kept_rows.append(row)

    for residue_key, atoms in targeted_atoms.items():
        missing_atoms = REQUIRED_ALA_ATOMS - atoms
        if missing_atoms:
            raise ValueError(
                f"Protenix UNK chain {binder_chain} residue {residue_key[2]} lacks "
                f"alanine atoms: {', '.join(sorted(missing_atoms))}"
            )

    atom_loop.rows = kept_rows

    # Keep polymer sequence metadata consistent with the repaired coordinates.
    for loop in loops:
        category = loop.category.lower()
        if category == "_entity_poly_seq":
            entity_index = loop.index("entity_id")
            mon_index = loop.index("mon_id")
            for row in loop.rows:
                if _value(row, entity_index) in targeted_entities:
                    _replace_unk(row, (mon_index,), "ALA")
        elif category == "_pdbx_poly_seq_scheme":
            entity_index = loop.index("entity_id")
            chain_indices = (
                loop.index("asym_id"), loop.index("pdb_strand_id"),
                loop.index("auth_asym_id"),
            )
            comp_indices = (
                loop.index("mon_id"), loop.index("pdb_mon_id"),
                loop.index("auth_mon_id"),
            )
            for row in loop.rows:
                chains = {_value(row, index) for index in chain_indices} - {"", ".", "?"}
                if binder_chain in chains or _value(row, entity_index) in targeted_entities:
                    _replace_unk(row, comp_indices, "ALA")
        elif category == "_struct_conn":
            # Protenix records the polymer bonds explicitly. Keep their partner
            # component names aligned with the repaired _atom_site rows.
            for row in loop.rows:
                for partner in ("ptnr1", "ptnr2"):
                    chain_indices = (
                        loop.index(f"{partner}_label_asym_id"),
                        loop.index(f"{partner}_auth_asym_id"),
                    )
                    chains = {
                        _value(row, index) for index in chain_indices
                    } - {"", ".", "?"}
                    if binder_chain in chains:
                        _replace_unk(
                            row,
                            (
                                loop.index(f"{partner}_label_comp_id"),
                                loop.index(f"{partner}_auth_comp_id"),
                            ),
                            "ALA",
                        )

    # Remove the unused generic chemical definition only when no UNK atom remains.
    remaining_unk_atoms = any(
        "UNK" in {
            _value(row, label_comp_i).upper(),
            _value(row, auth_comp_i).upper(),
        }
        for row in atom_loop.rows
    )
    if not remaining_unk_atoms:
        for loop in loops:
            if loop.category.lower() == "_chem_comp":
                comp_id_i = loop.index("id")
                loop.rows = [row for row in loop.rows if _value(row, comp_id_i).upper() != "UNK"]

    replacements = sorted(loops, key=lambda loop: loop.data_start, reverse=True)
    for loop in replacements:
        lines[loop.data_start:loop.data_end] = _render_rows(loop.rows)

    return "".join(lines), len(targeted_atoms), removed_cg


def normalize_legacy(text: str, mode: str, chooser: Callable[[tuple[str, ...]], str] | None = None) -> str:
    """Retain the historical non-Protenix placeholder substitution."""
    pattern = re.compile(r"(?<!\S)UNK(?!\S)")
    if mode == "ala":
        return pattern.sub("ALA", text)
    choices = {"ala_gly": ("ALA", "GLY"), "ala_gly_ser": ("ALA", "GLY", "SER")}
    if mode not in choices:
        raise ValueError(f"Unknown mode: {mode}")
    pick = chooser or random.choice
    return pattern.sub(lambda _: pick(choices[mode]), text)


def normalize_text(text: str, predictor: str, binder_chain: str, mode: str) -> tuple[str, int, int]:
    predictor = predictor.strip().lower()
    if predictor in PROTENIX_PREDICTORS:
        return normalize_protenix(text, binder_chain)
    return normalize_legacy(text, mode), 0, 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--predictor", required=True)
    parser.add_argument("--binder-chain", required=True)
    parser.add_argument("--mode", required=True, choices=("ala", "ala_gly", "ala_gly_ser"))
    args = parser.parse_args()

    source = args.input.read_text()
    normalized, residues, removed = normalize_text(
        source, args.predictor, args.binder_chain, args.mode
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(normalized)
    if args.predictor.lower() in PROTENIX_PREDICTORS:
        print(
            f"Protenix handoff normalized {residues} UNK residue(s) on chain "
            f"{args.binder_chain} to ALA and removed {removed} CG pseudo-atom(s)",
        )


if __name__ == "__main__":
    main()
