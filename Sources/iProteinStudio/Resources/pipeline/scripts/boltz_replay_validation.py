"""Bounded resident Boltz replay experiment, launched only by the job broker.

Capture singleton RNG states without changing them; replay them per input in a
single directory request. Hash actual model features to reject a false pairing.
This is an explicit validation route, not a change to normal Boltz sampling.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid


def checksum(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate(output, config):
    output = Path(output).resolve()
    version = config.get("schema")
    if (version not in (1, 2) or Path(config.get("output", "")).resolve() != output
            or config.get("potentials") is not (version == 2) or config.get("phase") != "structure"
            or config.get("seed") != 0):
        raise ValueError("Replay requires seed 0, structure-only and the versioned guidance policy")
    if version == 2:
        steps = config.get("trace_steps")
        if (config.get("fk_steering") is not False or not isinstance(steps, list) or not steps
                or any(type(x) is not int or not 1 <= x <= 200 for x in steps)
                or steps != sorted(set(steps)) or steps[-1] != 200):
            raise ValueError("Single-particle replay requires FK off and unique ordered trace steps ending at 200")
    ids = config.get("ids")
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 100 or ids != sorted(set(ids))
            or any(not re.fullmatch(r"L\d{3,5}", x) for x in ids)):
        raise ValueError("Replay requires 1–100 unique ordered initial-backbone IDs")
    paths = []
    for name, digest in config["files"].items():
        path = (output / name).resolve()
        if (output / "inputs") not in path.parents or not path.is_file() or checksum(path) != digest:
            raise ValueError("Frozen replay input changed: " + name)
        paths.append(path)
    required = {"inputs/ligand_atom_map.json", "inputs/nise_config.json"}
    required |= {f"inputs/{name}/{name}.yaml" for name in ids}
    required |= {f"inputs/{name}/completed.json" for name in ids}
    required |= {f"inputs/{name}/processed/{folder}/{name}.{extension}"
                 for name in ids for folder, extension in
                 (("records", "json"), ("structures", "npz"), ("constraints", "npz"), ("mols", "pkl"))}
    if version == 2:
        required |= {f"inputs/rng/{name}_{suffix}" for name in ids
                     for suffix in ("features.pt", "prediction.pt", "features.sha256")}
    if not required <= config["files"].keys():
        raise ValueError("Replay lacks required frozen inputs")
    for name in ids:
        old = json.loads((output / "inputs" / name / "completed.json").read_text())
        spec = old["input"]
        if (spec.get("phase") != "structure" or spec.get("seed") != 0
                or spec.get("potentials") is not True or not spec.get("pocket", {}).get("force")
                or old["result"]["timing"].get("completed_jobs") != 1):
            raise ValueError("Expected completed guided structure-only baseline")
    return paths


def replay_arms(config):
    return ("physical", "physical_trace") if config["schema"] == 2 else ("singleton", "batch")


def install_rng_replay(session, mode, directory):
    """Preserve Python, NumPy, CPU and MPS streams at both stochastic boundaries."""
    import random
    import numpy as np
    import torch
    from boltz.data.module.inferencev2 import PredictionDataset
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    def boundary(name, stage):
        if not re.fullmatch(r"L\d{3,5}", name):
            raise ValueError("Unexpected replay input identity")
        path = directory / f"{name}_{stage}.pt"
        if mode == "capture":
            state = dict(python=random.getstate(), numpy=np.random.get_state(),
                         cpu=torch.get_rng_state(), mps=torch.mps.get_rng_state())
            torch.save(state, path)
        else:
            # These are local experiment-generated states, covered by receipts.
            state = torch.load(path, map_location="cpu", weights_only=False)
            random.setstate(state["python"]); np.random.set_state(state["numpy"])
            torch.set_rng_state(state["cpu"]); torch.mps.set_rng_state(state["mps"])

    original_item = PredictionDataset.__getitem__
    def getitem(dataset, index):
        boundary(dataset.manifest.records[index].id, "features")
        return original_item(dataset, index)
    PredictionDataset.__getitem__ = getitem
    original_step = session.model.predict_step
    def step(batch, batch_idx, dataloader_idx=0):
        if len(batch["record"]) != 1:
            raise ValueError("Replay expects upstream batch size 1")
        name = batch["record"][0].id
        # Do not hash path-bearing record metadata; hash every model tensor.
        h = hashlib.sha256()
        for key, value in sorted(batch.items()):
            if torch.is_tensor(value):
                value = value.detach().cpu().contiguous()
                h.update(f"{key}|{value.dtype}|{tuple(value.shape)}".encode())
                h.update(value.numpy().tobytes())
        path = directory / f"{name}_features.sha256"
        if mode == "capture":
            path.write_text(h.hexdigest())
        elif path.read_text() != h.hexdigest():
            raise ValueError(f"Batch features differ from singleton for {name}")
        boundary(name, "prediction")
        started = time.time()
        result = original_step(batch, batch_idx, dataloader_idx)
        torch.mps.synchronize()
        session._replay_item_times.append(dict(id=name, seconds=time.time() - started))
        print(f"REPLAY|{mode}|{name}|{session._replay_item_times[-1]['seconds']:.3f}", flush=True)
        return result
    session._replay_item_times = []
    session.model.predict_step = step


def worker(config_path):
    import resident_predictor as resident
    original = resident.make_session
    def create(config):
        session = original(config)
        if config.get("physical_single_particle"):
            session.model.steering_args.update(fk_steering=False,
                physical_guidance_update=True, contact_guidance_update=True)
            # Lightning's executed-parameter record must describe the override.
            # Lightning logs hparams_initial (a frozen copy), not hparams.
            session.model.save_hyperparameters({"steering_args": dict(session.model.steering_args)})
            resident.atomic_json(Path(config["queue"]) / "actual_steering.json",
                dict(session.model.steering_args, effective_diffusion_particles=1))
        install_rng_replay(session, config["replay_mode"], config["rng_directory"])
        if config.get("trace_steps"):
            from boltz_diffusion_observer import install
            install(session, config["trace_steps"], Path(config["trace_directory"]))
        return session
    resident.make_session = create
    resident.serve(config_path)


def run(config_path):
    scripts = Path(__file__).resolve().parent
    sys.path.insert(0, str(scripts / "nise"))
    from runtime import ResidentClient, Journal, atomic, input_digest, Backend
    from ligand_atoms import audit_atoms
    config = json.loads(config_path.read_text())
    output = Path(config["output"])
    validate(output, config)
    import yaml
    for name in config["ids"]:
        old = json.loads((output / "inputs" / name / "completed.json").read_text())["input"]
        parsed = yaml.safe_load((output / "inputs" / name / f"{name}.yaml").read_text())
        proteins = [x["protein"] for x in parsed["sequences"] if "protein" in x]
        ligands = [x["ligand"] for x in parsed["sequences"] if "ligand" in x]
        if (proteins != [dict(id="A", sequence=old["sequence"], msa="empty")]
                or ligands != [dict(id="B", smiles=old["smiles"])]
                or parsed.get("constraints") != [dict(pocket=old["pocket"])]) :
            raise ValueError("YAML changed the saved sequence, chemical state, MSA or pocket restraint")
    root = Path(os.environ["NANOHUNTER_ROOT"])
    journal = Journal(output)
    manifest = json.loads((output / "inputs/ligand_atom_map.json").read_text())
    if config["schema"] == 2:
        (output / "rng").mkdir(exist_ok=True)
        for path in (output / "inputs/rng").iterdir():
            destination = output / "rng" / path.name
            if destination.exists():
                if checksum(destination) != checksum(path):
                    raise ValueError("Imported replay random state changed")
            else:
                shutil.copy2(path, destination)

    class Client(ResidentClient):
        def __init__(self, arm):
            self.queue = output / arm / "sessions" / uuid.uuid4().hex
            self.queue.mkdir(parents=True)
            self.log = self.queue / "worker.log"
            self.config = self.queue / "config.json"
            cfg = dict(root=str(root), engine="boltz", model="boltz2", queue=str(self.queue),
                owner_pid=os.getpid(), use_potentials=config["potentials"], allow_affinity=False,
                physical_single_particle=config["schema"] == 2,
                trace_steps=config["trace_steps"] if arm == "physical_trace" else [],
                trace_directory=str(output / arm / "traces"),
                replay_mode="capture" if arm == "singleton" else "replay",
                rng_directory=str(output / "rng"),
                engine_args=["--accelerator", "gpu", "--devices", "1", "--num_workers", "0",
                    "--output_format", "pdb", "--cache", str(root / "models/boltz2"), "--seed", "0",
                    "--recycling_steps", "3", "--sampling_steps", "200", "--diffusion_samples", "1"])
            atomic(self.config, cfg)
            self.stream = self.log.open("w")
            self.process = subprocess.Popen([str(root / "venvs/NanoHunter_boltz/bin/python"),
                str(Path(__file__).resolve()), "--worker", str(self.config)],
                stdout=self.stream, stderr=subprocess.STDOUT,
                env=dict(os.environ, PYTORCH_ENABLE_MPS_FALLBACK="0", BOLTZ_CACHE=str(root / "models/boltz2")))
            try:
                self.ready = self.wait(self.queue / "ready.json")
                if (self.ready.get("device") != "mps" or self.ready.get("fallback") != 0
                        or self.ready.get("model_load_count") != 1 or self.ready.get("pid") != self.process.pid
                        or self.ready.get("config_sha256") != checksum(self.config)):
                    raise ValueError("Invalid resident replay worker")
            except BaseException:
                self.close(); raise

        def submit(self, source, destination, count):
            identifier = uuid.uuid4().hex
            filename = f"request_{identifier}.json"
            sha = input_digest(source)
            atomic(self.queue / "requests" / filename, dict(request_id=identifier,
                input_dir=str(source), output_dir=str(destination), expected_jobs=count,
                input_sha256=sha, phase="structure", prediction_seed=0))
            receipt = self.wait(self.queue / "responses" / filename)
            if (not receipt.get("ok") or receipt.get("completed_jobs") != count
                    or receipt.get("input_sha256") != sha or receipt.get("request_id") != identifier
                    or receipt.get("phase") != "structure" or receipt.get("model_load_count") != 1
                    or receipt.get("prediction_seed") != 0):
                raise ValueError(f"Replay failed: {receipt}; see {self.log}")
            return dict(receipt, startup_seconds=self.ready["startup_seconds"], session=str(self.queue))

    for arm in replay_arms(config):
        groups = [[x] for x in config["ids"]] if arm == "singleton" else [config["ids"]]
        client = None
        try:
            for names in groups:
                unit = output / arm / (names[0] if arm == "singleton" else "all")
                spec = dict(arm=arm, ids=names, files=config["files"], seed=0, potentials=config["potentials"])
                if journal.load(unit / "completed.json", spec) is not None:
                    continue
                unit.mkdir(parents=True, exist_ok=True)
                if (unit / "out").exists():
                    (unit / "out").rename(unit / ("interrupted-" + uuid.uuid4().hex))
                source = unit / "yaml"
                source.mkdir(exist_ok=True)
                for name in names:
                    shutil.copy2(output / "inputs" / name / f"{name}.yaml", source / f"{name}.yaml")
                    processed = output / "inputs" / name / "processed"
                    for artifact in processed.rglob("*"):
                        if artifact.is_file() and artifact.name != "manifest.json":
                            destination = unit / "out/boltz_results_yaml/processed" / artifact.relative_to(processed)
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(artifact, destination)
                if client is None:
                    client = Client(arm)
                receipt = client.submit(source, unit / "out", len(names))
                for name in names:
                    leaf = unit / "out/boltz_results_yaml/predictions" / name
                    pdbs = list(leaf.glob("*.pdb"))
                    confidences = list(leaf.glob("confidence_*.json"))
                    if len(pdbs) != 1 or len(confidences) != 1:
                        raise ValueError("Wrong output cardinality")
                    sequence = json.loads((output / "inputs" / name / "completed.json").read_text())["input"]["sequence"]
                    Backend.audit_structure(pdbs[0], sequence, True)
                    audit_atoms(pdbs[0], manifest)
                    if list(leaf.glob("affinity_*.json")):
                        raise ValueError("Unexpected affinity inference")
                files = [p for p in (unit / "out").rglob("*") if p.is_file()]
                files += list(source.glob("*.yaml"))
                for name in names:
                    files += sorted((output / "rng").glob(name + "_*"))
                if arm == "physical_trace":
                    files += [output / arm / "traces" / name for name in
                              ("observer_provenance.json", "instrumented_sample.py")]
                    for name in names:
                        trace = output / arm / "traces" / name
                        if not (trace / "metadata.json").is_file() or not (trace / "coordinates.npz").is_file():
                            raise ValueError("Missing diffusion trace for " + name)
                        files += [trace / "metadata.json", trace / "coordinates.npz"]
                journal.save(unit / "completed.json", spec, receipt, files)
                atomic(output / "progress.json", dict(arm=arm, completed=names, status="running"))
                print(f"REPLAY|completed|{arm}|{','.join(names)}", flush=True)
        finally:
            if client is not None:
                client.close()
    atomic(output / "progress.json", dict(status="completed", count_per_arm=len(config["ids"])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--config", type=Path)
    group.add_argument("--worker", type=Path)
    args = parser.parse_args()
    worker(args.worker) if args.worker else run(args.config)
