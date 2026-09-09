#!/usr/bin/env python3
"""Audit sample-then-mask seed-only experiments using the shared structural audit.

Smoke gates test operational integrity, independently of scientific success.
Full results retain the prospectively declared trajectory-mean decision rule.
All writes are derived analysis; raw outputs are never modified.
"""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import itertools
import json
import math
from pathlib import Path
import random
import sys
import tempfile

SHARED_PATH = Path(__file__).resolve().parents[1] / "secondary_structure_search_v1" / "audit.py"
spec = importlib.util.spec_from_file_location("shared_secondary_structure_audit", SHARED_PATH)
assert spec and spec.loader
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
require = shared.require
AA = frozenset("ACDEFGHIKLMNPQRSTVWY")
COMPOSITION_METRICS = ("sequence_entropy_bits", "max_residue_fraction", "max_identical_residue_run")


def composition(sequence: str) -> dict:
    """Composition of concrete residues; X is missing information, not an amino acid."""
    concrete = sequence.replace("X", "")
    require(bool(concrete) and set(concrete) <= AA, "composition needs concrete amino acids")
    counts = Counter(concrete)
    # Do not join residues across an X when counting contiguous runs.
    runs = [len(list(group)) for aa, group in itertools.groupby(sequence) if aa != "X"]
    return {
        "sequence_entropy_bits": -sum((n / len(concrete)) * math.log2(n / len(concrete)) for n in counts.values()),
        "max_residue_fraction": max(counts.values()) / len(concrete),
        "max_identical_residue_run": max(runs),
        "concrete_residues_for_composition": len(concrete),
        "amino_acid_counts": dict(sorted(counts.items())),
    }


def validate_seed_plan(plan: dict, expected_sequence: str, arm: dict, controls: dict, length: int) -> dict:
    require(plan.get("sampling_order") == "sample-then-mask", "seed plan does not declare sample-then-mask")
    require(plan.get("sampling_algorithm") == "complete-sequence-independent-mask-v1", "unexpected seed sampling algorithm")
    require(plan.get("application_scope") == "seed-only" and arm.get("scope") == "seed-only", "secondary controls were not restricted to seed-only")
    require(plan.get("mode") == arm.get("mode"), "seed plan mode differs from declaration")
    require(plan.get("length") == length and plan.get("percent_x") == 50, "seed plan length or mask percentage differs from declaration")
    complete = plan.get("unmasked_sequence")
    require(isinstance(complete, str) and len(complete) == length and set(complete) <= AA, "invalid full sequence in seed plan")
    positions = plan.get("x_positions")
    require(isinstance(positions, list) and all(type(value) is int for value in positions), "mask positions must be integer list")
    require(len(positions) * 2 == length and len(set(positions)) == len(positions), "mask must contain exactly 50% unique positions")
    require(all(1 <= value <= length for value in positions), "mask positions outside sequence")
    seed = plan.get("seed")
    require(type(seed) is int, "seed plan lacks an integer random seed")
    expected_positions = list(range(length))
    random.Random(seed ^ 0x584D4153).shuffle(expected_positions)
    require(set(positions) == {index + 1 for index in expected_positions[:length // 2]}, "mask does not replay from independent RNG seed")
    masked = "".join("X" if index in set(positions) else aa for index, aa in enumerate(complete, 1))
    require(plan.get("masked_sequence") == masked, "stored masked sequence cannot be reconstructed from full sequence and mask")
    require(expected_sequence == masked, "actual cycle00 requested sequence differs from saved seed plan")
    for field in ("anti_helix_strength", "beta_strength", "beta_pattern_strength", "turn_strength"):
        expected = arm.get(field, controls.get(field))
        require(expected is not None and plan.get("controls", {}).get(field) == expected, f"seed plan {field} differs from declaration")
    return {
        "sampling_order": plan["sampling_order"],
        "sampling_algorithm": plan["sampling_algorithm"],
        "seed": seed,
        "x_positions": sorted(positions),
        "masked_sequence": masked,
        "unmasked_sequence": complete,
        "unmasked_composition": composition(complete),
        "visible_seed_composition": composition(masked),
        "positions": plan.get("positions"),
        "blocks": plan.get("blocks"),
        "actual_cycle00_equals_reconstructed_mask": True,
    }


def option_value(arguments: list, option: str, default=None):
    matches = [index for index, value in enumerate(arguments) if value == option]
    require(len(matches) <= 1, f"repeated command option {option}")
    if not matches:
        return default
    require(matches[0] + 1 < len(arguments), f"missing command option value {option}")
    return arguments[matches[0] + 1]


def validate_seed_only_runtime(campaign: Path, arguments: list, design_cycles: int) -> dict:
    require(option_value(arguments, "--secondary-bias-scope") == "seed-only", "immutable request is not seed-only")
    require(option_value(arguments, "--seed-sampling-order") == "sample-then-mask", "immutable request does not select sample-then-mask")
    require(option_value(arguments, "--predictor") == "boltz", "immutable request does not select Boltz")
    require(option_value(arguments, "--sequence-designer") == "solublempnn", "immutable request does not select SolubleMPNN")
    for option in ("--mpnn-bias-aa-cycle1", "--mpnn-bias-aa-other"):
        require(option_value(arguments, option, "") == "", f"unexpected global redesign bias: {option}")
    require(float(option_value(arguments, "--loopkill", "0")) == 0, "unexpected loopkill bias")
    forbidden = list(campaign.glob("run_*/cycle_*/ligandmpnn/secondary_structure_bias.json"))
    require(not forbidden, f"unexpected per-residue MPNN secondary bias files: {forbidden}")
    evidence = []
    for run_root in sorted(campaign.glob("run_*")):
        if not run_root.is_dir():
            continue
        for cycle in range(design_cycles):
            log = run_root / f"cycle_{cycle:02d}" / "ligandmpnn" / "ligandmpnn.log"
            require(log.is_file(), f"missing redesign log: {log}")
            content = log.read_text(errors="replace")
            require("secondary_structure_bias.json" not in content and "--bias_AA_per_residue" not in content, f"redesign log contains secondary bias: {log}")
            evidence.append(str(log.relative_to(campaign)))
    return {"scope": "seed-only", "secondary_bias_files": 0, "redesign_log_files_checked": len(evidence), "source_cycles_checked": list(range(design_cycles)), "design_cycles_produced": list(range(1, design_cycles + 1))}


ORIGINAL_AUDIT_ARM = shared.audit_arm


def audit_arm(arm, campaign, trajectories, design_cycles, binder_length, binder_chain, root, phase, manifest, job, state):
    rows, checksums, details = ORIGINAL_AUDIT_ARM(arm, campaign, trajectories, design_cycles, binder_length, binder_chain, root, phase, manifest, job, state)
    config = manifest.get("config", manifest)
    arguments = shared.load_json(root / "plans" / phase / f"{arm}.json")["normalized_request"]["arguments"]
    details["seed_only_runtime"] = validate_seed_only_runtime(campaign, arguments, design_cycles)
    helper_path = campaign / ".studio_runtime" / "pipeline" / "scripts" / "secondary_structure_control.py"
    helper_spec = importlib.util.spec_from_file_location("audited_seed_sampler", helper_path)
    require(helper_spec is not None and helper_spec.loader is not None, "cannot load audited sampling helper")
    helper = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helper)
    plans = {}
    for row in rows:
        row.update({key: value for key, value in composition(row["sequence"]).items() if key != "amino_acid_counts"})
        if row["cycle"] != 0:
            continue
        plan_path = campaign / row["run"] / "secondary_structure_plan.json"
        plan = shared.load_json(plan_path)
        plans[row["run"]] = validate_seed_plan(plan, row["sequence"], config["arms"][arm], config.get("controls", {}), binder_length)
        expected_seed = int(config["campaign"]["binder_seed"]) + int(row["run"].split("_")[-1])
        require(plan["seed"] == expected_seed, f"trajectory binder seed differs from manifest: {arm}/{row['run']}")
        weights = plan["controls"]
        regenerated, regenerated_plan = helper.generate_sequence(
            binder_length, binder_length, 50, "boltz", expected_seed, plan["mode"],
            weights["anti_helix_strength"], weights["beta_strength"], weights["beta_pattern_strength"], weights["turn_strength"],
            0, "seed-only", "sample-then-mask",
        )
        require(regenerated == row["sequence"] and regenerated_plan == plan, f"full seed plan does not replay from verified snapshot and declared seed: {arm}/{row['run']}")
        plans[row["run"]]["full_plan_replays_from_verified_snapshot"] = True
        shared.hash_file(plan_path, root, checksums)
        for cycle in range(design_cycles):
            shared.hash_file(campaign / row["run"] / f"cycle_{cycle:02d}" / "ligandmpnn" / "ligandmpnn.log", root, checksums)
    details["seed_plans"] = plans
    return rows, checksums, details


def enrich_report(report: dict, gate: dict, phase: str) -> None:
    paired = {}
    audited = {arm: details for arm, details in report["arm_audits"].items() if details["audit_status"] == "audited_complete"}
    for first, second in itertools.combinations(audited, 2):
        first_plans, second_plans = audited[first]["seed_plans"], audited[second]["seed_plans"]
        runs = sorted(set(first_plans) & set(second_plans))
        paired[f"{first}__vs__{second}"] = {
            run: {"same_mask": first_plans[run]["x_positions"] == second_plans[run]["x_positions"], "same_positional_plan": first_plans[run]["positions"] == second_plans[run]["positions"] and first_plans[run]["blocks"] == second_plans[run]["blocks"]}
            for run in runs
        }
    paired_passed = bool(paired) and all(item["same_mask"] and item["same_positional_plan"] for pairs in paired.values() for item in pairs.values())
    checks = dict(gate["checks"])
    scientific = {key: checks.pop(key) for key in list(checks) if key in ("structural_target_candidate_present", "declared_balanced_trajectory_mean_rule_met")}
    checks["sample_then_mask_seed_plans_match_actual_sequences"] = gate["all_complete"]
    checks["secondary_bias_absent_from_mpnn_redesign"] = gate["all_complete"]
    checks["paired_masks_and_positional_plans_equal"] = paired_passed
    operational_passed = all(checks.values())
    # Completing the requested campaign and evaluating a hypothesis must remain
    # possible when the hypothesis is false. Scientific success is separate.
    gate.update(checks=checks, passed=operational_passed, operational_passed=operational_passed, scientific_checks=scientific, paired_seed_masks=paired)
    report.update(gate_checks=checks, passed=operational_passed, operational_passed=operational_passed, scientific_checks=scientific, paired_seed_masks=paired)
    report["method"].update(
        primary_statistical_unit="trajectory mean of cycles01–05; then equal-weight mean across trajectories; cycle00 excluded",
        smoke_gate="operational integrity only; independent of scientific endpoint",
        composition="Shannon entropy in bits and maximum residue fraction exclude X; identical-residue runs never bridge X",
        secondary_control_audit="saved mask replay + sequence reconstruction + immutable seed-only request + no MPNN secondary bias artifacts/log evidence",
        phase=phase,
    )


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--phase", default="smoke")
    parser.add_argument("--output-dir", type=Path)
    if "--help" in sys.argv:
        shared.main()
        return
    args, rest = parser.parse_known_args()
    output = args.output_dir.resolve() if args.output_dir else args.root.resolve() / "analysis" / args.phase
    output.mkdir(parents=True, exist_ok=True)
    shared.audit_arm = audit_arm
    shared.METRICS += COMPOSITION_METRICS
    with tempfile.TemporaryDirectory(prefix=".seed-mask-audit-", dir=output) as temporary:
        original_argv = sys.argv
        sys.argv = [str(SHARED_PATH), "--root", str(args.root), "--phase", args.phase, "--output-dir", temporary, *rest]
        try:
            # Suppress shared intermediate gate output; it is not the final gate.
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                shared.main()
        finally:
            sys.argv = original_argv
        temporary = Path(temporary)
        report = shared.load_json(temporary / "audit.json")
        gate = shared.load_json(temporary / "smoke_passed.json")
        enrich_report(report, gate, args.phase)
        (temporary / "audit.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        (temporary / "smoke_passed.json").write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n")
        # Gate is published last, only after every derived result is available.
        for name in ("audited_per_structure.csv", "audited_per_trajectory.csv", "audit.json", "smoke_passed.json"):
            (temporary / name).replace(output / name)
    print(json.dumps({"report": str(output / "audit.json"), "gate": str(output / "smoke_passed.json"), "passed": gate["passed"], "audited_structures": gate["audited_structures"], "scientific_checks": gate["scientific_checks"], "arm_audits": {arm: {key: value for key, value in details.items() if key in ("audit_status", "error")} for arm, details in report["arm_audits"].items()}}, indent=2))


if __name__ == "__main__":
    main()
