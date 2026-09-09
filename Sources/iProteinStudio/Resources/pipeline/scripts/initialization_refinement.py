#!/usr/bin/env python3
"""Durable monomer initialization stages, driven by the existing job scheduler.

The assessor determines eligibility; the sequence sampler proposes candidates;
this journal records stage inputs, outputs and the scheduler's explicit handoff.
No prediction or inverse-folding process is launched by this module.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from initialization_assessment import assess, assess_structure, validate_policy
from secondary_structure_control import generate_sequence


def canonical(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def publish(destination, payloads):
    """Publish a complete immutable stage, including its receipt, atomically."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError(f"Stage already exists: {destination}")
    stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=destination.parent))
    try:
        receipt = {"schema": 1, "sha256": {name: digest(data) for name, data in payloads.items()}}
        for name, data in {**payloads, "receipt.json": canonical(receipt)}.items():
            with (stage / name).open("wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        os.rename(stage, destination)
        fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def verify(path):
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"Invalid stage directory: {path}")
    receipt_path = path / "receipt.json"
    if receipt_path.is_symlink():
        raise ValueError("Stage receipt must not be a symlink")
    receipt = json.loads(receipt_path.read_bytes())
    for name, expected in receipt["sha256"].items():
        if Path(name).name != name or (path / name).is_symlink():
            raise ValueError("Invalid preserved artifact path")
        if digest((path / name).read_bytes()) != expected:
            raise ValueError(f"Preserved initialization artifact changed: {path / name}")
    return receipt


def read_json(path):
    return json.loads(path.read_bytes())


def validate_monomer_template(path):
    import yaml
    document = yaml.safe_load(path.read_text())
    if not isinstance(document, dict) or set(document) - {"version", "sequences"}:
        raise ValueError("Refinement requires an unconditioned monomer template")
    sequences = document.get("sequences")
    if not isinstance(sequences, list) or len(sequences) != 1 or set(sequences[0]) != {"protein"}:
        raise ValueError("Refinement requires exactly one protein chain and no target or ligand")
    protein = sequences[0]["protein"]
    if (not isinstance(protein, dict) or protein.get("id") != "A"
            or set(protein) - {"id", "sequence", "msa"}
            or protein.get("msa", "empty") != "empty"):
        raise ValueError("Refinement requires an unconditioned, single-sequence monomer on chain A")


class Refinement:
    """Stage API. Mutating callers must hold locked(); the CLI does so for every action."""
    def __init__(self, root):
        self.root = Path(root)

    @contextmanager
    def locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / ".lock").open("a+b") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield

    def configure(self, config):
        validate_policy(config["policy"])
        plan = config["plan"]
        sequence = config["sequence"]
        if (not sequence or len(sequence) != plan["length"]
                or any(aa not in "ACDEFGHIKLMNPQRSTVWYX" for aa in sequence)
                or sequence != plan["masked_sequence"] or type(plan["sampling_seed"]) is not int):
            raise ValueError("Refinement requires an exact, deterministically sampled original sequence and plan")
        if config["policy"]["min_uncertain_coil_length"] > len(sequence):
            raise ValueError("Uncertain-coil length exceeds the monomer length")
        if config["predictor"] not in {"boltz", "intellifold", "protenix-v2", "protenix-mini"}:
            raise ValueError("Unsupported initialization confidence adapter")
        if (config["predictor"] == "openfold-3-mlx"
                or plan["application_scope"] not in {"seed-only", "seed-and-cycles"}):
            raise ValueError("Unsupported initialization sampling contract")
        if (self.root / "configuration").exists():
            verify(self.root / "configuration")
            if read_json(self.root / "configuration/config.json") != config:
                raise ValueError("Initialization configuration cannot change on resume")
        else:
            publish(self.root / "configuration", {"config.json": canonical(config)})
        if not list(self.root.glob("attempt_*")):
            self._input(0, {"sequence": sequence, "plan": plan, "changes": [],
                            "reconsider_positions": [], "generator": "original", "parent": None})
        return self.status()

    def _input(self, index, candidate):
        candidate = {**candidate, "index": index,
                     "configuration_sha256": digest((self.root / "configuration/config.json").read_bytes())}
        publish(self.root / f"attempt_{index:06d}", {"input.json": canonical(candidate)})

    def status(self):
        verify(self.root / "configuration")
        config = read_json(self.root / "configuration/config.json")
        validate_policy(config["policy"])
        config_hash = digest(canonical(config))
        attempts = sorted(self.root.glob("attempt_*"))
        if not attempts or len(attempts) > config["policy"]["max_attempts"]:
            raise ValueError("Missing initialization or exceeded attempt budget")
        state, parent = None, None
        for index, path in enumerate(attempts):
            if path.name != f"attempt_{index:06d}":
                raise ValueError("Initialization attempt history has a gap")
            if index and state != "needs_refinement":
                raise ValueError("Attempt recorded before assessment or after a terminal decision")
            verify(path)
            candidate = read_json(path / "input.json")
            if (candidate["index"] != index or candidate["configuration_sha256"] != config_hash
                    or candidate["parent"] != parent):
                raise ValueError("Initialization attempt provenance differs from its history")
            state = "awaiting_prediction"
            structure = ""
            if (path / "prediction").exists():
                receipt = verify(path / "prediction")
                names = [name for name in receipt["sha256"] if name.startswith("model_0.")]
                if len(names) != 1 or not {"confidence.json", "input.yaml"} <= receipt["sha256"].keys():
                    raise ValueError("Prediction requires exactly one structure, confidence JSON and input YAML")
                structure = str(path / "prediction" / names[0])
                state = "awaiting_assessment"
            if (path / "assessment").exists():
                if state != "awaiting_assessment":
                    raise ValueError("Assessment has no preserved prediction")
                verify(path / "assessment")
                assessment = read_json(path / "assessment/assessment.json")
                expected = assess(assessment["psea"], assessment["confidence"], config["policy"])
                if any(assessment.get(key) != value for key, value in expected.items()):
                    raise ValueError("Assessment differs from the recorded criteria")
                state = ("acceptable" if assessment["eligible"] else "budget_exhausted"
                         if index + 1 == config["policy"]["max_attempts"] else "needs_refinement")
                if read_json(path / "assessment/decision.json") != self._decision(state, index, config):
                    raise ValueError("Recorded progression decision differs from the assessment and budget")
                parent = digest((path / "assessment/assessment.json").read_bytes())
        selected = None
        if (self.root / "selection").exists():
            verify(self.root / "selection")
            selection = read_json(self.root / "selection/selection.json")
            if state != "acceptable" or selection != self._selection(index, parent):
                raise ValueError("Selection does not identify the eligible assessed initialization")
            selected, state = index, "accepted"
        return {"state": state, "index": index, "sequence": candidate["sequence"],
                "structure": structure, "recorded_attempts": len(attempts),
                "remaining_attempts": config["policy"]["max_attempts"] - len(attempts),
                "selected_attempt": selected, "eligible_for_normal_cycling": state == "accepted"}

    @staticmethod
    def _decision(state, index, config):
        return {"state": state, "recorded_attempts": index + 1,
                "remaining_attempts": config["policy"]["max_attempts"] - index - 1,
                "selected_attempt": None, "executes_normal_cycling": False}

    @staticmethod
    def _selection(index, assessment_hash):
        return {"schema": 1, "attempt": index, "assessment_sha256": assessment_hash,
                "scheduler_decision": "enter_normal_cycling", "cycle_00_counts_as_design": False}

    def preserve_prediction(self, structure, confidence, input_yaml):
        status = self.status()
        if status["state"] != "awaiting_prediction":
            raise ValueError("The current attempt is not awaiting prediction")
        if structure.suffix.lower() not in {".cif", ".mmcif", ".pdb"}:
            raise ValueError("Prediction must be PDB or mmCIF")
        suffix = ".cif" if structure.suffix.lower() == ".mmcif" else structure.suffix.lower()
        payloads = {"model_0" + suffix: structure.read_bytes(),
                    "confidence.json": confidence.read_bytes(), "input.yaml": input_yaml.read_bytes()}
        if any(not data for data in payloads.values()):
            raise ValueError("Prediction artifacts must not be empty")
        json.loads(payloads["confidence.json"])
        publish(self.root / f"attempt_{status['index']:06d}/prediction", payloads)
        return self.status()

    def assess(self):
        status = self.status()
        if status["state"] != "awaiting_assessment":
            raise ValueError("The current attempt is not awaiting assessment")
        config = read_json(self.root / "configuration/config.json")
        assessment = assess_structure(Path(status["structure"]), status["sequence"], config["policy"])
        state = ("acceptable" if assessment["eligible"] else "budget_exhausted"
                 if status["remaining_attempts"] == 0 else "needs_refinement")
        publish(self.root / f"attempt_{status['index']:06d}/assessment",
                {"assessment.json": canonical(assessment),
                 "decision.json": canonical(self._decision(state, status["index"], config))})
        return self.status()

    def propose(self):
        status = self.status()
        if status["state"] != "needs_refinement":
            raise ValueError("Candidate generation requires a nonterminal failed assessment")
        config = read_json(self.root / "configuration/config.json")
        path = self.root / f"attempt_{status['index']:06d}"
        previous = read_json(path / "input.json")
        assessment = read_json(path / "assessment/assessment.json")
        positions = [p for region in assessment["reconsider_regions"]
                     for p in range(region["start"], region["end"] + 1)]
        plan, controls = previous["plan"], previous["plan"]["controls"]
        seed = config["plan"]["sampling_seed"] + status["index"] + 1
        sequence, plan = generate_sequence(
            plan["length"], plan["length"], plan["percent_x"], config["predictor"], seed,
            plan["mode"], controls["anti_helix_strength"], controls["beta_strength"],
            controls["beta_pattern_strength"], controls["turn_strength"], plan["loop_kill"],
            plan["application_scope"], plan["sampling_order"], position_plan=plan,
            previous_sequence=previous["sequence"], reconsider_positions=positions)
        changes = [{"position": p, "before": before, "after": after}
                   for p, (before, after) in enumerate(zip(previous["sequence"], sequence), 1)
                   if before != after]
        self._input(status["index"] + 1,
                    {"sequence": sequence, "plan": plan, "changes": changes,
                     "reconsider_positions": positions, "generator": "existing-seed-sampler-regional-v1",
                     "parent": digest((path / "assessment/assessment.json").read_bytes())})
        return self.status()

    def select(self):
        status = self.status()
        if status["state"] != "acceptable":
            raise ValueError("Normal cycling requires an acceptable initialization")
        assessment = self.root / f"attempt_{status['index']:06d}/assessment/assessment.json"
        publish(self.root / "selection",
                {"selection.json": canonical(self._selection(status["index"], digest(assessment.read_bytes())))})
        return self.status()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check-template", "status"])
    parser.add_argument("--root", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--structure", type=Path)
    parser.add_argument("--confidence", type=Path)
    parser.add_argument("--input-yaml", type=Path)
    parser.add_argument("--max-attempts", type=int)
    parser.add_argument("--min-uncertain-coil-length", type=int)
    parser.add_argument("--confidence-threshold", type=float)
    parser.add_argument("--minimum-length", type=int)
    parser.add_argument("--field", choices=["state", "index", "sequence", "structure"])
    args = parser.parse_args()
    try:
        if args.command == "check-template":
            validate_monomer_template(args.input_yaml)
            print("Unconditioned monomer template preflight passed")
            return
        if args.command == "check":
            import biotite  # Fail at preflight if the selected runtime cannot assess outputs.
            validate_policy({"max_attempts": args.max_attempts,
                             "min_uncertain_coil_length": args.min_uncertain_coil_length,
                             "confidence_threshold": args.confidence_threshold})
            if args.minimum_length is not None and args.min_uncertain_coil_length > args.minimum_length:
                raise ValueError("Uncertain-coil length exceeds the minimum requested monomer length")
            validate_monomer_template(args.input_yaml)
            print("Monomer refinement preflight passed")
            return
        journal = Refinement(args.root)
        with journal.locked():
            if args.command == "configure":
                result = journal.configure(read_json(args.config))
            elif args.command == "prediction":
                result = journal.preserve_prediction(args.structure, args.confidence, args.input_yaml)
            else:
                result = getattr(journal, args.command)()
        print(result[args.field] if args.field else json.dumps(result, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ImportError) as error:
        raise SystemExit(f"ERROR: Initialization refinement: {error}") from error


if __name__ == "__main__":
    main()
