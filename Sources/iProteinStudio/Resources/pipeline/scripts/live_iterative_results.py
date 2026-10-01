"""Publish display-only checkpoints after the predictor's writer has returned.

These receipts do not satisfy scientific resume checks or advance a trajectory.
The shell's completed-cycle metrics remain authoritative when they arrive.
"""
from contextlib import contextmanager
import csv
import hashlib
import json
import math
from pathlib import Path
import re

import yaml

from validate_prediction_geometry import inspect_geometry


class LiveIterativeResults:
    def __init__(self, source: Path, binder_chain: str = "A"):
        self.inputs = {}
        for path in sorted(source.glob("*.yaml")):
            match = re.fullmatch(r"run_(\d+)_cycle_(\d+)", path.stem)
            if not match:
                raise ValueError(f"Unexpected iterative input name: {path.name}")
            resolved = path.resolve()
            run, cycle = match.groups()
            if (resolved.parent.name != f"cycle_{cycle}" or
                    resolved.parent.parent.name != f"run_{run}"):
                raise ValueError("Live results require a saved run/cycle input")
            raw = resolved.read_bytes()
            data = yaml.safe_load(raw)
            proteins = [entry["protein"] for entry in data["sequences"] if "protein" in entry]
            sequences = [p["sequence"] for p in proteins
                         if binder_chain in ([p["id"]] if isinstance(p["id"], str) else p["id"])]
            if len(sequences) != 1:
                raise ValueError("Cannot identify the saved binder sequence")
            self.inputs[path.stem] = (resolved, hashlib.sha256(raw).hexdigest(), sequences[0], int(cycle))
            # A rerun must not expose the previous attempt while files are replaced.
            (resolved.parent / "live_prediction.csv").unlink(missing_ok=True)

    def publish(self, name: str, leaf: Path):
        path, expected, sequence, cycle = self.inputs[name]
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Iterative input changed during prediction")
        structures = [leaf / f"{name}_model_0{suffix}" for suffix in (".cif", ".pdb")]
        structures = [p for p in structures if p.is_file()]
        confidence = leaf / f"confidence_{name}_model_0.json"
        if len(structures) != 1 or not confidence.is_file():
            raise ValueError(f"Incomplete Boltz prediction for {name}")
        self.publish_structure(name, structures[0], confidence, 'boltz')

    def publish_structure(self, name, structure, confidence, engine):
        path, expected, sequence, cycle = self.inputs[name]
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Iterative input changed during prediction')
        if inspect_geometry(structure)["errors"]:
            raise ValueError(f"Unusable prediction coordinates for {name}")
        scores = json.loads(confidence.read_text())
        def metric(key):
            value = scores.get(key)
            return value if isinstance(value, (int, float)) and math.isfinite(value) else ""
        root = path.parent.parent.parent
        row = dict(cycle=cycle, predictor=engine, iptm=metric("iptm"), complex_plddt=metric("complex_plddt"),
                   confidence_json=str(confidence.resolve().relative_to(root)),
                   structure_path=str(structure.resolve().relative_to(root)), binder_sequence=sequence)
        target = path.parent / "live_prediction.csv"
        temporary = target.with_suffix(".csv.part")
        with temporary.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)
        temporary.replace(target)


@contextmanager
def boltz_live_writer(boltz_main, publisher, report_progress, total):
    """Wrap only the disk writer, preserving its tensors, order, RNG and model."""
    original = boltz_main.BoltzWriter
    completed = set()

    class LiveWriter(original):
        def write_on_batch_end(self, trainer, pl_module, prediction, batch_indices,
                               batch, batch_idx, dataloader_idx):
            super().write_on_batch_end(trainer, pl_module, prediction, batch_indices,
                                       batch, batch_idx, dataloader_idx)
            if prediction["exception"]:
                return
            for record in batch["record"]:
                publisher.publish(record.id, Path(self.output_dir) / record.id)
                completed.add(record.id)
            if report_progress:
                report_progress(len(completed), total, 0)

    boltz_main.BoltzWriter = LiveWriter
    try:
        yield
    finally:
        boltz_main.BoltzWriter = original
