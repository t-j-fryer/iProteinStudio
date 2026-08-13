#!/usr/bin/env python3
"""Sample exact nanobody sequence positions from an AntiFold logits CSV."""

from __future__ import annotations

import argparse
import csv
import math
import random
import re
from pathlib import Path


AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"


def parse_positions(raw: str) -> list[int]:
    positions: list[int] = []
    for token in re.split(r"[\s,;]+", raw.strip()):
        if not token:
            continue
        range_match = re.fullmatch(
            r"(?:[A-Za-z]+)?(\d+)\s*-\s*(?:[A-Za-z]+)?(\d+)",
            token,
        )
        if range_match:
            start, end = map(int, range_match.groups())
            if start < 1 or end < start:
                raise ValueError(f"Invalid residue range {token!r}")
            for position in range(start, end + 1):
                if position not in positions:
                    positions.append(position)
            continue
        match = re.search(r"(\d+)$", token)
        if not match:
            raise ValueError(f"Invalid residue position {token!r}")
        position = int(match.group(1))
        if position < 1:
            raise ValueError(f"Residue positions must be >= 1: {token!r}")
        if position not in positions:
            positions.append(position)
    if not positions:
        raise ValueError("No residue positions were provided")
    return sorted(positions)


def load_chain_rows(path: Path, chain: str) -> dict[int, dict[str, str]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"pdb_chain", "pdb_pos", "pdb_res", "top_res", *AMINO_ACIDS}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"AntiFold CSV {path} is missing columns: {', '.join(sorted(missing))}"
            )
        rows: dict[int, dict[str, str]] = {}
        for row in reader:
            if (row.get("pdb_chain") or "").strip() != chain:
                continue
            position = int(float(row["pdb_pos"]))
            rows[position] = row
    if not rows:
        raise ValueError(f"No AntiFold rows found for chain {chain!r} in {path}")
    return rows


def temperature_probabilities(
    row: dict[str, str],
    temperature: float,
    omitted_amino_acids: set[str],
) -> list[float]:
    scale = max(temperature, 0.001)
    scaled = [
        float(row[amino_acid]) / scale
        if amino_acid not in omitted_amino_acids
        else -math.inf
        for amino_acid in AMINO_ACIDS
    ]
    maximum = max(scaled)
    if not math.isfinite(maximum):
        raise ValueError("All amino acids were removed by --omit-aa")
    weights = [math.exp(value - maximum) for value in scaled]
    total = sum(weights)
    if not math.isfinite(total) or total <= 0:
        raise ValueError("AntiFold logits produced invalid sampling probabilities")
    return [weight / total for weight in weights]


def sample_sequence(
    base_sequence: str,
    rows: dict[int, dict[str, str]],
    positions: list[int],
    temperature: float,
    rng: random.Random,
    limit_variation: bool,
    omitted_amino_acids: set[str],
) -> tuple[str, list[int]]:
    sequence = list(base_sequence.strip().upper())
    if not sequence:
        raise ValueError("Base sequence is empty")

    sampled_positions: list[int] = []
    top_mismatch_count = 0
    for position in positions:
        if position > len(sequence):
            raise ValueError(
                f"Selected position {position} exceeds sequence length {len(sequence)}"
            )
        row = rows.get(position)
        if row is None:
            raise ValueError(
                f"AntiFold logits do not contain chain position {position}"
            )
        probabilities = temperature_probabilities(
            row, temperature, omitted_amino_acids
        )
        sampled = rng.choices(list(AMINO_ACIDS), weights=probabilities, k=1)[0]
        sequence[position - 1] = sampled
        sampled_positions.append(position)
        if sampled != (row.get("top_res") or "").strip().upper():
            top_mismatch_count += 1

    if limit_variation:
        mutation_positions = [
            position
            for position in positions
            if sequence[position - 1] != base_sequence[position - 1].upper()
        ]
        revert_count = max(0, len(mutation_positions) - top_mismatch_count)
        for position in rng.sample(mutation_positions, min(revert_count, len(mutation_positions))):
            sequence[position - 1] = base_sequence[position - 1].upper()

    return "".join(sequence), sampled_positions


def write_fasta(
    path: Path,
    base_sequence: str,
    samples: list[str],
    positions: list[int],
    temperature: float,
    seed: int,
    omitted_amino_acids: set[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        handle.write(
            f">antifold_input exact_positions={','.join(map(str, positions))} "
            f"omit_aa={''.join(sorted(omitted_amino_acids)) or 'none'}\n"
        )
        handle.write(base_sequence + "\n")
        for index, sequence in enumerate(samples, start=1):
            mutations = sum(a != b for a, b in zip(base_sequence, sequence))
            handle.write(
                f">antifold_exact_sample_{index} temperature={temperature:g} "
                f"seed={seed} mutations={mutations}\n"
            )
            handle.write(sequence + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logits-csv", required=True, type=Path)
    parser.add_argument("--chain", required=True)
    parser.add_argument("--base-sequence", required=True)
    parser.add_argument("--positions", required=True)
    parser.add_argument("--temperature", required=True, type=float)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--num-sequences", type=int, default=1)
    parser.add_argument("--limit-variation", action="store_true")
    parser.add_argument(
        "--omit-aa",
        default="",
        help="one-letter amino-acid codes that must not be sampled",
    )
    parser.add_argument("--output-fasta", required=True, type=Path)
    args = parser.parse_args()

    if args.num_sequences < 1:
        parser.error("--num-sequences must be >= 1")

    base_sequence = re.sub(r"[^A-Za-z]", "", args.base_sequence).upper()
    positions = parse_positions(args.positions)
    rows = load_chain_rows(args.logits_csv, args.chain)
    omitted_amino_acids = set(re.sub(r"[^A-Za-z]", "", args.omit_aa).upper())
    invalid_omissions = omitted_amino_acids.difference(AMINO_ACIDS)
    if invalid_omissions:
        parser.error(
            "--omit-aa contains unsupported codes: "
            + ",".join(sorted(invalid_omissions))
        )
    rng = random.Random(args.seed)

    samples = [
        sample_sequence(
            base_sequence,
            rows,
            positions,
            args.temperature,
            rng,
            args.limit_variation,
            omitted_amino_acids,
        )[0]
        for _ in range(args.num_sequences)
    ]
    write_fasta(
        args.output_fasta,
        base_sequence,
        samples,
        positions,
        args.temperature,
        args.seed,
        omitted_amino_acids,
    )
    print(samples[0])


if __name__ == "__main__":
    main()
