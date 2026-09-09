#!/usr/bin/env python3
"""Deterministic sequence priors for iterative-design secondary structure.

This module deliberately controls *sequence sampling*, not the folded result.
The generated plan is saved with each trajectory and reused for every
ProteinMPNN-family redesign cycle.  Whether a requested prior produced helix,
sheet, or coil must still be measured from predicted coordinates.
"""

from __future__ import annotations

import argparse
import copy
import functools
import json
import math
import random
from pathlib import Path
from typing import Any


AA_POOL = list("ADEFGHIKLMNPQRSTVWY")
HELIX_PRONE = set("AEKLMQ")
BETA_PRONE = set("VITFYW")
HYDROPHOBIC_FACE = set("VIFYW")
POLAR_FACE = set("STNQDEK")
TURN_FAVOURED = set("GDNS")
MODES = {"none", "antihelix", "beta", "mixed"}
APPLICATION_SCOPES = {"seed-only", "seed-and-cycles"}
PLAN_SCHEMA = 1


def bounded(value: float, name: str) -> float:
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return value


def build_plan(
    length: int,
    seed: int | None,
    mode: str,
    anti_helix_strength: float,
    beta_strength: float,
    beta_pattern_strength: float,
    turn_strength: float,
    application_scope: str = "seed-and-cycles",
) -> dict[str, Any]:
    if length < 1:
        raise ValueError("length must be positive")
    if mode not in MODES:
        raise ValueError(f"secondary bias must be one of {sorted(MODES)}")
    if application_scope not in APPLICATION_SCOPES:
        raise ValueError(f"secondary-bias scope must be one of {sorted(APPLICATION_SCOPES)}")
    controls = {
        "anti_helix_strength": bounded(anti_helix_strength, "anti-helix strength"),
        "beta_strength": bounded(beta_strength, "beta strength"),
        "beta_pattern_strength": bounded(beta_pattern_strength, "beta-pattern strength"),
        "turn_strength": bounded(turn_strength, "turn strength"),
    }
    positions: list[dict[str, Any]] = [
        {"index": index, "region": "unconstrained", "face": None, "turn_core": False, "edge": False}
        for index in range(1, length + 1)
    ]
    blocks: list[dict[str, Any]] = []

    if mode in {"beta", "mixed"}:
        if length < 5:
            raise ValueError("beta-oriented priors require a binder length of at least 5 residues")
        # Architecture draws use an independent stream, so choosing a bias does
        # not perturb the historical length/X-position stream.
        plan_rng = random.Random(None if seed is None else seed ^ 0x5EC0DA7A)
        spans = {"strand": range(5, 9), "turn": range(2, 6)}

        @functools.lru_cache(maxsize=None)
        def can_partition(remaining: int, kind: str) -> bool:
            if remaining == 0:
                return True
            next_kind = "turn" if kind == "strand" else "strand"
            return any(
                size <= remaining and can_partition(remaining - size, next_kind)
                for size in spans[kind]
            )

        if not can_partition(length, "strand"):
            raise ValueError(f"cannot construct 5-8-residue strands and 2-5-residue turns for length {length}")

        cursor = 0
        kind = "strand"
        while cursor < length:
            remaining = length - cursor
            next_kind = "turn" if kind == "strand" else "strand"
            choices = [
                size for size in spans[kind]
                if size <= remaining and can_partition(remaining - size, next_kind)
            ]
            block_length = plan_rng.choice(choices)
            start = cursor
            if kind == "strand":
                face_offset = plan_rng.randrange(2)
                for offset in range(block_length):
                    edge = offset == 0 or offset == block_length - 1
                    positions[cursor] = {
                        "index": cursor + 1,
                        "region": "strand",
                        "face": "edge" if edge else (
                            "hydrophobic" if (offset + face_offset) % 2 == 0 else "polar"
                        ),
                        "turn_core": False,
                        "edge": edge,
                    }
                    cursor += 1
                blocks.append({
                    "kind": "strand", "start": start + 1, "end": cursor,
                    "face_offset": face_offset,
                })
            else:
                core_offset = (block_length - 1) // 2
                for offset in range(block_length):
                    positions[cursor] = {
                        "index": cursor + 1,
                        "region": "turn",
                        "face": None,
                        "turn_core": offset == core_offset,
                        "edge": False,
                    }
                    cursor += 1
                blocks.append({"kind": "turn", "start": start + 1, "end": cursor})
            kind = next_kind

    return {
        "schema": PLAN_SCHEMA,
        "kind": "iproteinstudio-secondary-structure-sequence-prior",
        "scientific_status": "experimental-sequence-prior-not-fold-guarantee",
        "mode": mode,
        "application_scope": application_scope,
        "length": length,
        "seed": seed,
        "controls": controls,
        "blocks": blocks,
        "positions": positions,
    }


def per_residue_bias(
    plan: dict[str, Any], chain: str = "A", phase: str = "redesign"
) -> dict[str, dict[str, float]]:
    if phase not in {"seed", "redesign"}:
        raise ValueError("secondary-structure phase must be seed or redesign")
    application_scope = str(plan.get("application_scope", "seed-and-cycles"))
    if application_scope not in APPLICATION_SCOPES:
        raise ValueError(f"secondary-bias scope must be one of {sorted(APPLICATION_SCOPES)}")
    if phase == "redesign" and application_scope == "seed-only":
        return {}
    mode = str(plan["mode"])
    controls = plan["controls"]
    anti = float(controls["anti_helix_strength"]) if mode in {"antihelix", "mixed"} else 0.0
    beta = float(controls["beta_strength"]) if mode in {"beta", "mixed"} else 0.0
    pattern = float(controls["beta_pattern_strength"]) if mode in {"beta", "mixed"} else 0.0
    turn = float(controls["turn_strength"]) if mode in {"beta", "mixed"} else 0.0
    result: dict[str, dict[str, float]] = {}

    for position in plan["positions"]:
        bias: dict[str, float] = {}
        if anti > 0:
            for aa in HELIX_PRONE:
                bias[aa] = bias.get(aa, 0.0) - 1.20 * anti
            bias["S"] = bias.get("S", 0.0) + 0.25 * anti

        if position["region"] == "strand" and beta > 0:
            for aa in "VIT":
                bias[aa] = bias.get(aa, 0.0) + 0.40 * beta
            for aa in "FYW":
                bias[aa] = bias.get(aa, 0.0) + 0.15 * beta
            for aa in "GP":
                bias[aa] = bias.get(aa, 0.0) - 1.20 * beta

            if position["face"] == "edge":
                # Solvent-facing strand edges reduce the chance that a simple
                # alternating prior degenerates into an aggregation-prone strip.
                for aa in POLAR_FACE:
                    bias[aa] = bias.get(aa, 0.0) + 0.70 * pattern
                for aa in HYDROPHOBIC_FACE:
                    bias[aa] = bias.get(aa, 0.0) - 0.50 * pattern
            elif position["face"] == "hydrophobic":
                for aa in HYDROPHOBIC_FACE:
                    bias[aa] = bias.get(aa, 0.0) + 0.65 * pattern
                for aa in POLAR_FACE:
                    bias[aa] = bias.get(aa, 0.0) - 0.10 * pattern
            else:
                for aa in POLAR_FACE:
                    bias[aa] = bias.get(aa, 0.0) + 0.60 * pattern
                for aa in HYDROPHOBIC_FACE:
                    bias[aa] = bias.get(aa, 0.0) - 0.15 * pattern

        if position["region"] == "turn" and turn > 0:
            for aa in TURN_FAVOURED:
                bias[aa] = bias.get(aa, 0.0) + 1.10 * turn
            # Proline is localized to one turn-core position instead of being
            # boosted globally. It remains discouraged at strand positions.
            bias["P"] = bias.get("P", 0.0) + (0.90 if position["turn_core"] else 0.15) * turn
            for aa in HYDROPHOBIC_FACE:
                bias[aa] = bias.get(aa, 0.0) - 0.40 * turn

        if bias:
            result[f"{chain}{position['index']}"] = {
                aa: round(value, 6) for aa, value in sorted(bias.items()) if abs(value) > 1e-12
            }
    return result


def generate_sequence(
    minimum: int,
    maximum: int,
    percent_x: float,
    predictor: str,
    seed: int | None,
    mode: str,
    anti_helix_strength: float,
    beta_strength: float,
    beta_pattern_strength: float,
    turn_strength: float,
    loop_kill: float,
    application_scope: str = "seed-and-cycles",
    sampling_order: str = "mask-first",
    *,
    position_plan: dict[str, Any] | None = None,
    previous_sequence: str | None = None,
    reconsider_positions: list[int] | None = None,
) -> tuple[str, dict[str, Any]]:
    if maximum < minimum or minimum < 1:
        raise ValueError("maximum length must be >= a positive minimum length")
    percent_x = max(0.0, min(100.0, float(percent_x)))
    loop_kill = bounded(loop_kill, "loop-kill strength")
    if sampling_order not in {"mask-first", "sample-then-mask"}:
        raise ValueError("seed sampling order must be mask-first or sample-then-mask")
    if sampling_order == "sample-then-mask" and (
        mode not in {"beta", "mixed"} or application_scope != "seed-only"
    ):
        raise ValueError("sample-then-mask requires beta or mixed seed-only control")
    rng = random.Random(seed)
    spike_rng = random.Random(None if seed is None else seed + 1_000_000_007)
    length = rng.randint(minimum, maximum)
    plan = build_plan(
        length, seed, mode, anti_helix_strength, beta_strength,
        beta_pattern_strength, turn_strength, application_scope,
    )
    mutable = set(range(1, length + 1))
    if position_plan is not None:
        if (minimum != maximum or position_plan["length"] != length
                or len(position_plan["positions"]) != length
                or position_plan["mode"] != mode
                or position_plan["controls"] != plan["controls"]
                or position_plan["application_scope"] != application_scope):
            raise ValueError("Refinement must preserve the original position plan and controls")
        if previous_sequence is None or len(previous_sequence) != length:
            raise ValueError("Refinement requires the complete previous sequence")
        if not reconsider_positions or any(type(p) is not int or not 1 <= p <= length
                                            for p in reconsider_positions):
            raise ValueError("Refinement positions must be one-based positions in the sequence")
        mutable = set(reconsider_positions)
        plan = copy.deepcopy(position_plan)
    elif previous_sequence is not None or reconsider_positions is not None:
        raise ValueError("Regional resampling requires the original position plan")
    # The released anti-helix seed rule is applied below in probability space.
    # Only the new beta/turn grammar contributes logit-style position bias here,
    # avoiding an accidental double anti-helix penalty in cycle 0. The complete
    # plan (including anti-helix) is still used by MPNN redesign cycles.
    if mode in {"beta", "mixed"}:
        seed_plan = dict(plan)
        seed_plan["mode"] = "beta"
        seed_plan["controls"] = dict(plan["controls"])
        seed_plan["controls"]["anti_helix_strength"] = 0.0
        position_bias = per_residue_bias(seed_plan, phase="seed")
    else:
        position_bias = {}

    n_x = max(0, min(length, int(round(length * percent_x / 100.0))))
    indices = list(range(length))
    if sampling_order == "mask-first":
        rng.shuffle(indices)
        x_positions = set(indices[:n_x])
    else:
        # Sample every residue, including those subsequently hidden from the
        # predictor. The local anti-helix rule therefore sees the complete chain.
        x_positions = set()
    if previous_sequence is not None and sampling_order == "mask-first":
        # Preserve the mask cardinality inside each selected union, and leave
        # every position outside it untouched. No additional X budget is added.
        old_mask = {i for i, aa in enumerate(previous_sequence) if aa == "X"}
        candidates = [i for i in indices if i + 1 in mutable]
        count = sum(i + 1 in mutable for i in old_mask)
        x_positions = {i for i in old_mask if i + 1 not in mutable} | set(candidates[:count])
    of3_spike_pool = list("ANGHFSY")

    # Preserve the released helix-kill weighting for seed generation. The new
    # plan additionally persists a gentler logit bias into redesign cycles.
    anti_active = mode in {"antihelix", "mixed"}
    anti = bounded(anti_helix_strength, "anti-helix strength") if anti_active else 0.0
    base_helix_penalty = max(0.10, 1.0 - 0.90 * anti)
    local_helix_penalty = max(0.02, 1.0 - 1.70 * anti)
    ser_boost = 1.0 + anti
    proline_scale = max(0.0, 1.0 - loop_kill)

    base_weights: list[float] = []
    for aa in AA_POOL:
        weight = 1.0
        if anti_active and aa in HELIX_PRONE:
            weight *= base_helix_penalty
        if anti_active and aa == "S":
            weight *= ser_boost
        if aa == "P":
            weight *= proline_scale
        base_weights.append(weight)

    sequence: list[str | None] = [None] * length
    for index in range(length):
        if previous_sequence is not None and index + 1 not in mutable:
            sequence[index] = (plan["unmasked_sequence"][index]
                               if sampling_order == "sample-then-mask"
                               else previous_sequence[index])
            continue
        if index in x_positions:
            sequence[index] = spike_rng.choice(of3_spike_pool) if predictor == "openfold-3-mlx" else "X"
            continue
        weights = base_weights[:]
        if anti_active and index >= 4 and sequence[index - 4] in HELIX_PRONE:
            for aa_index, aa in enumerate(AA_POOL):
                if aa in HELIX_PRONE:
                    weights[aa_index] *= local_helix_penalty
        for aa_index, aa in enumerate(AA_POOL):
            weights[aa_index] *= math.exp(position_bias.get(f"A{index + 1}", {}).get(aa, 0.0))
        sequence[index] = rng.choices(AA_POOL, weights=weights, k=1)[0]

    if sampling_order == "sample-then-mask":
        unmasked = "".join(str(aa) for aa in sequence)
        # Independent mask draws keep paired beta/mixed arms on the same mask
        # and make the underlying sequence invariant to the requested X fraction.
        mask_rng = random.Random(None if seed is None else seed ^ 0x584D4153)
        mask_rng.shuffle(indices)
        x_positions = set(indices[:n_x])
        if previous_sequence is not None:
            old_mask = {i for i, aa in enumerate(previous_sequence) if aa == "X"}
            candidates = [i for i in indices if i + 1 in mutable]
            count = sum(i + 1 in mutable for i in old_mask)
            x_positions = {i for i in old_mask if i + 1 not in mutable} | set(candidates[:count])
        for index in x_positions:
            sequence[index] = spike_rng.choice(of3_spike_pool) if predictor == "openfold-3-mlx" else "X"
        plan.update({
            "sampling_order": sampling_order,
            "sampling_algorithm": "complete-sequence-independent-mask-v1",
            "unmasked_sequence": unmasked,
            "x_positions": sorted(index + 1 for index in x_positions),
            "masked_sequence": "".join(str(aa) for aa in sequence),
            "percent_x": percent_x,
        })
    else:
        plan.update({"sampling_order": sampling_order,
                     "sampling_algorithm": "mask-first-v1",
                     "x_positions": sorted(i + 1 for i in x_positions),
                     "masked_sequence": "".join(str(aa) for aa in sequence),
                     "percent_x": percent_x})
    plan["sampling_seed"] = seed
    plan["loop_kill"] = loop_kill
    return "".join(str(aa) for aa in sequence), plan


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def read_plan(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if payload.get("schema") != PLAN_SCHEMA or payload.get("kind") != "iproteinstudio-secondary-structure-sequence-prior":
        raise ValueError(f"invalid secondary-structure plan: {path}")
    if len(payload.get("positions", [])) != int(payload.get("length", -1)):
        raise ValueError(f"secondary-structure plan length mismatch: {path}")
    return payload


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed", help="Generate one sequence and its durable position plan")
    seed.add_argument("--min-length", type=int, required=True)
    seed.add_argument("--max-length", type=int, required=True)
    seed.add_argument("--percent-x", type=float, default=0.0)
    seed.add_argument("--predictor", default="")
    seed.add_argument("--seed", type=int)
    seed.add_argument("--secondary-bias", choices=["none", "antihelix"], default="none")
    seed.add_argument(
        "--secondary-bias-scope", choices=["seed-only"],
        default="seed-only",
    )
    seed.add_argument("--anti-helix-strength", type=float, default=0.5)
    seed.add_argument("--seed-sampling-order", choices=["mask-first"], default="mask-first")
    seed.add_argument("--plan", type=Path)

    bias = sub.add_parser("mpnn-bias", help="Convert a saved plan to LigandMPNN per-residue biases")
    bias.add_argument("--plan", type=Path, required=True)
    bias.add_argument("--chain", default="A")
    bias.add_argument("--output", type=Path, required=True)
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        if args.command == "seed":
            sequence, plan = generate_sequence(
                args.min_length, args.max_length, args.percent_x, args.predictor,
                args.seed, args.secondary_bias, args.anti_helix_strength,
                0.5, 0.5,
                0.5, 0.0, args.secondary_bias_scope,
                args.seed_sampling_order,
            )
            if args.plan:
                write_json(args.plan, plan)
            print(sequence)
        else:
            plan = read_plan(args.plan)
            if plan.get("application_scope") != "seed-only":
                raise ValueError("Sustained secondary-structure bias is retired")
            write_json(args.output, {})
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise SystemExit(f"ERROR: {error}") from error


if __name__ == "__main__":
    main()
