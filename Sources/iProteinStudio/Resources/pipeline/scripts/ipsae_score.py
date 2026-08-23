#!/usr/bin/env python3
"""Calculate and persist conservative ipSAE(min) interface confidence.

The numerical definition is a compact port of DunbrackLab/IPSAE version 4
(commit 6174cf9e71cb1bd660cc805856a18c4871a6dec3, MIT License): for every
directed protein-chain pair, keep PAE values below 10 A, recompute d0 from the
number retained in each row, average the resulting TM-like values, and take the
best row. Studio's ``ipSAE(min)`` is the conservative minimum of the two
directional values. The official script reports both directional rows and a
maximum row; Studio retains every directional value in JSON and deliberately
uses the minimum requested by the product owner.

This module annotates existing engine confidence JSON rather than inventing a
second results format. Boltz supplies ``pae_*.npz``; IntelliFold supplies
``pae`` plus token chain IDs; Protenix supplies ``token_pair_pae`` plus internal
chain IDs when ``--need_atom_confidence True`` is requested.

Copyright (c) 2025 Lab of Dr. Roland Dunbrack
Original implementation: https://github.com/DunbrackLab/IPSAE
SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import yaml


PAE_CUTOFF = 10.0
METHOD = "DunbrackLab/IPSAE v4 d0res; conservative directional minimum"


class IPSAEError(RuntimeError):
    """An input cannot support a reproducible ipSAE calculation."""


def _ordered_unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values))


def _d0_res(counts: np.ndarray) -> np.ndarray:
    """Dunbrack v4 calc_d0_array(), including its 2026 minimum fix."""
    lengths = np.maximum(26.0, np.asarray(counts, dtype=float))
    return np.maximum(1.0, 1.24 * np.cbrt(lengths - 15.0) - 1.8)


def calculate_ipsae(
    pae: Sequence[Sequence[float]] | np.ndarray,
    token_chain_ids: Sequence[str],
    protein_chain_ids: Sequence[str] | None = None,
    pae_cutoff: float = PAE_CUTOFF,
) -> dict:
    """Return directional, pairwise-minimum and overall ipSAE values.

    ``ipsae_min`` is the minimum conservative pair score when more than two
    protein chains are present. The per-pair and directional values remain in
    the returned object so a weak or intentionally non-contacting pair is never
    hidden by the scalar summary.
    """
    matrix = np.asarray(pae, dtype=float)
    chains = np.asarray([str(value) for value in token_chain_ids], dtype=object)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise IPSAEError(f"PAE must be square; got shape {matrix.shape}")
    if matrix.shape[0] != len(chains):
        raise IPSAEError(
            f"PAE/token mapping mismatch: {matrix.shape[0]} PAE tokens, "
            f"{len(chains)} chain IDs"
        )
    if not np.isfinite(matrix).all():
        raise IPSAEError("PAE contains non-finite values")
    if not math.isfinite(pae_cutoff) or pae_cutoff <= 0:
        raise IPSAEError("PAE cutoff must be a finite positive number")

    available = _ordered_unique(chains.tolist())
    proteins = _ordered_unique(protein_chain_ids or available)
    missing = [chain for chain in proteins if chain not in available]
    if missing:
        raise IPSAEError("protein chain IDs are absent from token mapping: " + ", ".join(missing))
    if len(proteins) < 2:
        raise IPSAEError("ipSAE requires at least two protein chains")

    directional: dict[str, float] = {}
    directional_counts: dict[str, int] = {}
    for chain_1 in proteins:
        rows = np.flatnonzero(chains == chain_1)
        for chain_2 in proteins:
            if chain_1 == chain_2:
                continue
            columns = np.flatnonzero(chains == chain_2)
            block = matrix[np.ix_(rows, columns)]
            valid = block < pae_cutoff
            counts = valid.sum(axis=1)
            d0 = _d0_res(counts)
            ptm = 1.0 / (1.0 + np.square(block / d0[:, None]))
            row_scores = np.divide(
                np.where(valid, ptm, 0.0).sum(axis=1),
                counts,
                out=np.zeros(len(rows), dtype=float),
                where=counts > 0,
            )
            key = f"{chain_1}>{chain_2}"
            best = int(np.argmax(row_scores))
            directional[key] = float(row_scores[best])
            directional_counts[key] = int(counts[best])

    pair_minimums: dict[str, float] = {}
    pairs: dict[str, dict] = {}
    for index, chain_1 in enumerate(proteins):
        for chain_2 in proteins[index + 1 :]:
            forward_key = f"{chain_1}>{chain_2}"
            reverse_key = f"{chain_2}>{chain_1}"
            pair_key = f"{chain_1}:{chain_2}"
            pair_minimum = min(directional[forward_key], directional[reverse_key])
            pair_minimums[pair_key] = pair_minimum
            pairs[pair_key] = {
                "forward": directional[forward_key],
                "reverse": directional[reverse_key],
                "minimum": pair_minimum,
                "maximum": max(directional[forward_key], directional[reverse_key]),
            }

    return {
        "ipsae_min": min(pair_minimums.values()),
        "ipsae_pae_cutoff": float(pae_cutoff),
        "ipsae_method": METHOD,
        "ipsae_directional": directional,
        "ipsae_directional_n0res": directional_counts,
        "ipsae_pair_minimums": pair_minimums,
        "ipsae_pairs": pairs,
    }


def _write_annotation(path: Path, metrics: dict) -> None:
    try:
        document = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise IPSAEError(f"cannot read confidence JSON {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise IPSAEError(f"confidence JSON must contain an object: {path}")
    document.update(metrics)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


def _scalar_id(value, fallback: str) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else fallback
    return str(value or fallback)


def _boltz_layout(yaml_path: Path, token_count: int) -> tuple[list[str], list[str]]:
    """Map app-generated Boltz tokens without guessing ligand atom counts."""
    try:
        document = yaml.safe_load(yaml_path.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise IPSAEError(f"cannot read Boltz input {yaml_path}: {exc}") from exc

    entries = document.get("sequences") or []
    protein_ids = []
    layout: list[str] = []
    unresolved_ligand_seen = False
    for index, wrapped in enumerate(entries):
        if not isinstance(wrapped, dict) or len(wrapped) != 1:
            raise IPSAEError(f"unsupported sequence entry in {yaml_path}")
        kind, raw = next(iter(wrapped.items()))
        raw = raw or {}
        chain_id = _scalar_id(raw.get("id"), chr(ord("A") + index))
        if kind == "protein":
            if unresolved_ligand_seen:
                raise IPSAEError(
                    "cannot map a protein placed after a ligand to Boltz PAE tokens; "
                    "put protein chains before ligands"
                )
            sequence = "".join(str(raw.get("sequence", "")).split())
            if not sequence:
                raise IPSAEError(f"protein {chain_id} has no sequence")
            protein_ids.append(chain_id)
            layout.extend([chain_id] * len(sequence))
        elif kind in {"dna", "rna"}:
            if unresolved_ligand_seen:
                raise IPSAEError("cannot map a polymer placed after a ligand to Boltz PAE tokens")
            sequence = "".join(str(raw.get("sequence", "")).split())
            layout.extend([f"__{kind}_{chain_id}"] * len(sequence))
        elif kind == "ligand":
            unresolved_ligand_seen = True
        else:
            raise IPSAEError(f"unsupported entity type {kind!r} in {yaml_path}")

    if len(layout) > token_count:
        raise IPSAEError(
            f"input polymers contain {len(layout)} tokens but Boltz PAE has {token_count}"
        )
    layout.extend(["__nonprotein__"] * (token_count - len(layout)))
    return layout, protein_ids


def annotate_boltz(yaml_path: Path, output: Path) -> int:
    """Annotate every Boltz sample belonging to one YAML input."""
    document = yaml.safe_load(yaml_path.read_text()) or {}
    protein_count = sum(
        1 for wrapped in (document.get("sequences") or [])
        if isinstance(wrapped, dict) and "protein" in wrapped
    )
    if protein_count < 2:
        return 0

    stem = yaml_path.stem
    pae_files = sorted(output.rglob(f"pae_{stem}_model_*.npz"))
    if not pae_files:
        raise IPSAEError(f"no Boltz PAE output for multimer {stem} under {output}")
    annotated = 0
    for pae_path in pae_files:
        with np.load(pae_path) as archive:
            if "pae" not in archive:
                raise IPSAEError(f"Boltz archive has no 'pae' matrix: {pae_path}")
            pae = np.asarray(archive["pae"], dtype=float)
        chain_ids, proteins = _boltz_layout(yaml_path, pae.shape[0])
        metrics = calculate_ipsae(pae, chain_ids, proteins)
        confidence_name = pae_path.name.replace("pae_", "confidence_", 1).removesuffix(".npz") + ".json"
        confidence = pae_path.with_name(confidence_name)
        if not confidence.is_file():
            raise IPSAEError(f"Boltz confidence JSON is missing beside {pae_path}")
        _write_annotation(confidence, metrics)
        annotated += 1
    return annotated


def annotate_intellifold(output: Path) -> int:
    """Annotate IntelliFold summary confidence files from detailed PAE JSON."""
    detailed = sorted(
        path for path in output.rglob("*_confidences.json")
        if "summary_confidences" not in path.name
    )
    annotated = 0
    for path in detailed:
        data = json.loads(path.read_text())
        pae = data.get("pae")
        chains = data.get("token_chain_ids")
        if pae is None or chains is None:
            continue
        proteins = _ordered_unique(chains)
        if len(proteins) < 2:
            continue
        summary = path.with_name(path.name.replace("_confidences.json", "_summary_confidences.json"))
        if not summary.is_file():
            raise IPSAEError(f"IntelliFold summary confidence is missing beside {path}")
        metrics = calculate_ipsae(pae, chains, proteins)
        _write_annotation(summary, metrics)
        annotated += 1
    return annotated


def _protenix_chain_map(job: dict, token_asym_ids: Sequence[int]) -> tuple[list[str], list[str]]:
    entity_ids = []
    protein_ids = []
    for index, wrapped in enumerate(job.get("sequences") or []):
        if not isinstance(wrapped, dict) or len(wrapped) != 1:
            raise IPSAEError(f"unsupported Protenix entity in job {job.get('name', '')}")
        kind, entity = next(iter(wrapped.items()))
        chain_id = _scalar_id((entity or {}).get("id"), chr(ord("A") + index))
        entity_ids.append(chain_id)
        if kind == "proteinChain":
            protein_ids.append(chain_id)
    unique_asym = list(dict.fromkeys(int(value) for value in token_asym_ids))
    if len(unique_asym) != len(entity_ids):
        raise IPSAEError(
            f"Protenix job {job.get('name', '')} has {len(entity_ids)} entities but "
            f"full confidence contains {len(unique_asym)} chain IDs"
        )
    mapping = dict(zip(unique_asym, entity_ids))
    return [mapping[int(value)] for value in token_asym_ids], protein_ids


def annotate_protenix(output: Path, jobs: Sequence[dict]) -> int:
    """Annotate Protenix summaries using explicitly requested full confidence."""
    annotated = 0
    for job in jobs:
        proteins = [
            wrapped for wrapped in (job.get("sequences") or [])
            if isinstance(wrapped, dict) and "proteinChain" in wrapped
        ]
        if len(proteins) < 2:
            continue
        job_root = output / str(job.get("name", ""))
        full_files = sorted(job_root.rglob("*_full_data_sample_*.json"))
        if not full_files:
            raise IPSAEError(
                f"Protenix emitted no full confidence for multimer {job.get('name', '')}; "
                "--need_atom_confidence True is required"
            )
        for full_path in full_files:
            data = json.loads(full_path.read_text())
            pae = data.get("token_pair_pae")
            asym = data.get("token_asym_id")
            if pae is None or asym is None:
                raise IPSAEError(f"Protenix full confidence lacks PAE/chain IDs: {full_path}")
            chains, protein_ids = _protenix_chain_map(job, asym)
            metrics = calculate_ipsae(pae, chains, protein_ids)
            summary_name = full_path.name.replace("_full_data_sample_", "_summary_confidence_sample_")
            summary = full_path.with_name(summary_name)
            if not summary.is_file():
                raise IPSAEError(f"Protenix summary confidence is missing beside {full_path}")
            _write_annotation(summary, metrics)
            annotated += 1
    return annotated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="engine", required=True)
    boltz = subparsers.add_parser("boltz")
    boltz.add_argument("--yaml", type=Path, required=True)
    boltz.add_argument("--output", type=Path, required=True)
    intellifold = subparsers.add_parser("intellifold")
    intellifold.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        if args.engine == "boltz":
            count = annotate_boltz(args.yaml.resolve(), args.output.resolve())
        else:
            count = annotate_intellifold(args.output.resolve())
    except (IPSAEError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ipSAE scoring failed: {exc}") from exc
    print(f"ipSAE: annotated {count} multimer prediction(s)")


if __name__ == "__main__":
    main()
