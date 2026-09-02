#!/usr/bin/env python3
"""Keep one pinned predictor model alive across iterative-design cycles.

The shell runner remains authoritative for trajectory state, inverse folding,
resume, and normalized campaign outputs.  This process owns only one model and
accepts immutable, checksummed directory requests through a file-backed queue.
It is deliberately engine-environment local: launch it with the Python from the
requested predictor's managed virtual environment.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from argparse import Namespace
from pathlib import Path
from typing import Any


def die(message: str) -> None:
    raise RuntimeError(f"resident predictor: {message}")


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def input_digest(directory: Path) -> tuple[str, list[Path]]:
    paths = sorted(directory.glob("*.yaml"))
    if not paths:
        die(f"no YAML inputs found in {directory}")
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.resolve().read_bytes())
        digest.update(b"\0")
    return digest.hexdigest(), paths


def option(arguments: list[str], name: str, default: str) -> str:
    for index, value in enumerate(arguments):
        if value == name:
            if index + 1 >= len(arguments):
                die(f"{name} requires a value")
            return arguments[index + 1]
        if value.startswith(name + "="):
            return value.split("=", 1)[1]
    return default


def flag(arguments: list[str], name: str) -> bool:
    return name in arguments


def require_mps() -> Any:
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") == "1":
        die("PYTORCH_ENABLE_MPS_FALLBACK=1 is forbidden")
    os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"
    import torch
    if not torch.backends.mps.is_built() or not torch.backends.mps.is_available():
        die("Apple MPS is unavailable; CPU execution is forbidden")
    return torch


def load_path(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        die(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def validate_geometry(root: Path, output: Path) -> None:
    validator = Path(__file__).resolve().with_name("validate_prediction_geometry.py")
    if not validator.is_file():
        die("managed prediction-geometry validator is missing")
    completed = subprocess.run([sys.executable, str(validator), str(output)])
    if completed.returncode:
        die("predictor returned invalid protein geometry")


class BoltzSession:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.root = Path(config["root"])
        self.arguments = list(config["engine_args"])
        self.torch = require_mps()
        import boltz.main as boltz_main
        from dataclasses import asdict

        compatibility = load_path(
            "iproteinstudio_boltz_mps",
            Path(__file__).resolve().with_name("boltz_mps.py"),
        )
        compatibility.configure_runtime(boltz_main, self.torch)

        self.boltz_main = boltz_main
        cache = Path(option(self.arguments, "--cache", str(self.root / "models" / "boltz2"))).expanduser()
        checkpoint = Path(option(self.arguments, "--checkpoint", str(cache / "boltz2_conf.ckpt")))
        if not checkpoint.is_file():
            die(f"Boltz checkpoint is missing: {checkpoint}")

        diffusion = boltz_main.Boltz2DiffusionParams()
        diffusion.step_scale = float(option(self.arguments, "--step_scale", "1.5"))
        msa = boltz_main.MSAModuleArgs(
            subsample_msa=not flag(self.arguments, "--no_subsample_msa"),
            num_subsampled_msa=int(option(self.arguments, "--num_subsampled_msa", "1024")),
            use_paired_feature=True,
        )
        steering = boltz_main.BoltzSteeringParams()
        steering.fk_steering = bool(config.get("use_potentials", False))
        steering.physical_guidance_update = bool(config.get("use_potentials", False))
        predict_args = {
            "recycling_steps": int(option(self.arguments, "--recycling_steps", "3")),
            "sampling_steps": int(option(self.arguments, "--sampling_steps", "200")),
            "diffusion_samples": int(option(self.arguments, "--diffusion_samples", "1")),
            "max_parallel_samples": None,
            "write_confidence_summary": True,
            "write_full_pae": flag(self.arguments, "--write_full_pae"),
            "write_full_pde": flag(self.arguments, "--write_full_pde"),
        }
        self.model = boltz_main.Boltz2.load_from_checkpoint(
            checkpoint,
            strict=True,
            predict_args=predict_args,
            map_location="cpu",
            diffusion_process_args=asdict(diffusion),
            ema=False,
            use_kernels=not flag(self.arguments, "--no_kernels"),
            pairformer_args=asdict(boltz_main.PairformerArgsV2()),
            msa_args=asdict(msa),
            steering_args=asdict(steering),
        )
        self.model.eval()
        self._original_loader = boltz_main.Boltz2.load_from_checkpoint

        model = self.model

        def resident_loader(_class, *_args, **_kwargs):
            return model

        boltz_main.Boltz2.load_from_checkpoint = classmethod(resident_loader)
        self.model_load_count = 1

    def predict(self, source: Path, output: Path, expected: int) -> None:
        arguments = [str(source), "--out_dir", str(output), *self.arguments]
        if self.config.get("use_potentials") and "--use_potentials" not in arguments:
            arguments.append("--use_potentials")
        if "--override" not in arguments:
            arguments.append("--override")
        self.boltz_main.predict.main(args=arguments, standalone_mode=False)
        root = output / f"boltz_results_{source.stem}" / "predictions"
        names = {path.stem for path in source.glob("*.yaml")}
        found = set()
        for name in names:
            leaf = root / name
            structures = list(leaf.glob("*.cif")) + list(leaf.glob("*.pdb"))
            confidences = list(leaf.glob("confidence_*_model_0.json"))
            if not structures or not confidences:
                die(f"Boltz output is incomplete for {name}")
            found.add(name)
        if len(found) != expected:
            die(f"Boltz expected {expected} completed jobs, found {len(found)}")
        validate_geometry(self.root, output)


class IntelliFoldSession:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.root = Path(config["root"])
        self.arguments = list(config["engine_args"])
        self.torch = require_mps()
        if importlib.metadata.version("accelerate") != "1.1.1":
            die("resident IntelliFold requires pinned Accelerate 1.1.1")
        if importlib.metadata.version("torch") != "2.6.0":
            die("resident IntelliFold requires pinned PyTorch 2.6.0")

        compatibility = load_path(
            "iproteinstudio_intellifold_mps",
            Path(__file__).resolve().with_name("intellifold_mps_compat.py"),
        )
        try:
            compatibility.patch_source(self.root)
        except RuntimeError as exc:
            die(str(exc))

        from accelerate import Accelerator
        from accelerate.state import AcceleratorState, PartialState
        strict_device = property(lambda _state: self.torch.device("mps"))
        PartialState.default_device = strict_device
        AcceleratorState.default_device = strict_device

        runner_path = self.root / "src" / "IntelliFold" / "run_intellifold.py"
        if not runner_path.is_file():
            die(f"IntelliFold runner is missing: {runner_path}")
        self.upstream = load_path("iproteinstudio_resident_intellifold", runner_path)
        self.args = Namespace(
            data="",
            out_dir="",
            cache=option(self.arguments, "--cache", str(self.root / "models" / "intellifold")),
            num_workers=int(option(self.arguments, "--num_workers", "0")),
            precision=option(self.arguments, "--precision", "no"),
            seed=option(self.arguments, "--seed", "42"),
            recycling_iters=int(option(self.arguments, "--recycling_iters", "10")),
            num_diffusion_samples=int(option(self.arguments, "--num_diffusion_samples", "1")),
            sampling_steps=int(option(self.arguments, "--sampling_steps", "200")),
            buckets=self.upstream.parse_buckets(option(self.arguments, "--buckets", "256,512,768,1024,1280,1536,2048,2560,3072,3584,4096,4608,5120")),
            output_format=option(self.arguments, "--output_format", "mmcif"),
            override=True,
            use_msa_server=flag(self.arguments, "--use_msa_server"),
            msa_server_url=option(self.arguments, "--msa_server_url", "https://api.colabfold.com"),
            msa_pairing_strategy=option(self.arguments, "--msa_pairing_strategy", "greedy"),
            no_pairing=flag(self.arguments, "--no_pairing"),
            use_template=flag(self.arguments, "--use_template"),
            only_run_data_process=False,
            return_similar_seq=False,
            model=option(self.arguments, "--model", config.get("model", "v2-flash")),
        )
        from accelerate import DistributedDataParallelKwargs, InitProcessGroupKwargs
        from datetime import timedelta
        from accelerate.utils import set_seed
        seeds = [int(value) for value in self.args.seed.split(",")]
        set_seed(seeds[0])
        self.seeds = seeds
        self.accelerator = Accelerator(
            kwargs_handlers=[
                DistributedDataParallelKwargs(find_unused_parameters=False),
                InitProcessGroupKwargs(timeout=timedelta(seconds=1800000)),
            ],
            log_with="wandb",
            mixed_precision=self.args.precision,
            step_scheduler_with_optimizer=False,
        )
        if self.accelerator.device.type != "mps":
            die(f"Accelerate selected forbidden device {self.accelerator.device}")
        cache = Path(self.args.cache).expanduser()
        cache.mkdir(parents=True, exist_ok=True)
        os.environ["INTELLIFOLD_CACHE"] = str(cache)
        self.upstream.download(cache, self.args.model, use_template=self.args.use_template)
        if self.args.model == "v2-flash":
            model_config = self.upstream.get_v2_flash_config(self.args)
            checkpoint = cache / "intellifold_v2_flash.pt"
        elif self.args.model == "v2":
            model_config = self.upstream.get_v2_model_config(self.args)
            checkpoint = cache / "intellifold_v2.pt"
        else:
            die(f"unsupported resident IntelliFold model {self.args.model}")
        if not checkpoint.is_file():
            die(f"IntelliFold checkpoint is missing: {checkpoint}")
        generator = self.torch.Generator(device=self.accelerator.device)
        generator.manual_seed(seeds[0])
        model = self.upstream.IntelliFold(model_config, generator=generator)
        state = self.torch.load(checkpoint, map_location=self.accelerator.device)
        model.load_state_dict(state)
        del state
        self.model = self.accelerator.prepare(model)
        self.model.eval()
        self.model_load_count = 1

    def predict(self, source: Path, output: Path, expected: int) -> None:
        import torch.nn.functional as functional
        from accelerate.utils import set_seed

        args = self.args
        args.data = str(source)
        args.out_dir = str(output)
        out_dir = output / source.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        data = self.upstream.check_inputs(source)
        if len(data) != expected:
            die(f"IntelliFold expected {expected} validated inputs, found {len(data)}")
        ccd = Path(args.cache) / "ccd_v2.pkl"
        self.upstream.process_inputs(
            args,
            data=data,
            out_dir=out_dir,
            ccd_path=ccd,
            use_msa_server=args.use_msa_server,
            msa_server_url=args.msa_server_url,
            msa_pairing_strategy=args.msa_pairing_strategy,
            max_msa_seqs=16384,
            use_pairing=not args.no_pairing,
            use_template=args.use_template,
        )
        processed_dir = out_dir / "processed"
        processed = self.upstream.BoltzProcessedInput(
            manifest=self.upstream.Manifest.load(processed_dir / "manifest.json"),
            targets_dir=processed_dir / "structures",
            msa_dir=processed_dir / "msa",
            template_dir=(processed_dir / "templates") if args.use_template else None,
            constraints_dir=(processed_dir / "constraints") if (processed_dir / "constraints").exists() else None,
        )
        loader = self.upstream.get_inference_dataloader(
            args=args,
            manifest=processed.manifest,
            target_dir=processed.targets_dir,
            msa_dir=processed.msa_dir,
            template_dir=processed.template_dir if args.use_template else None,
            constraints_dir=processed.constraints_dir,
        )
        loader = self.accelerator.prepare(loader)
        completed = 0
        for input_features in loader:
            record = input_features.pop("record")[0]
            structure = input_features.pop("structure")
            input_features["msa"] = functional.one_hot(input_features["msa"].long(), num_classes=32).float()
            ref_keys = [key for key in input_features if "ref_" in key]
            original_refs = [input_features[key] for key in ref_keys]
            if args.use_template:
                input_features["template_aatype"] = functional.one_hot(
                    input_features["template_aatype"].long(), num_classes=31
                ).float()
            else:
                input_features.update(self.upstream.construct_empty_template_features(
                    input_features, device=self.accelerator.device
                ))
            for seed in self.seeds:
                input_features.update(dict(zip(ref_keys, original_refs)))
                set_seed(seed)
                resident_model = self.model.module if hasattr(self.model, "module") else self.model
                resident_model.generator.manual_seed(seed)
                self.upstream.predict_and_save(
                    args, self.model, input_features, record, structure, out_dir, seed
                )
            completed += 1
            del input_features, original_refs
            gc.collect()
        self.accelerator.wait_for_everyone()
        if completed != expected:
            die(f"IntelliFold expected {expected} completed jobs, found {completed}")
        adapter = load_path(
            "iproteinstudio_intellifold_adapter",
            self.root / "scripts" / "intellifold_predict.py",
        )
        adapter.verify_outputs([
            str(source), "--out_dir", str(output), *self.arguments,
        ])
        validate_geometry(self.root, output)


class ProtenixSession:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.root = Path(config["root"])
        self.torch = require_mps()
        scripts = self.root / "scripts"
        sys.path.insert(0, str(scripts))
        self.adapter = load_path("iproteinstudio_protenix_adapter", scripts / "protenix_predict.py")
        model_alias = config.get("model", "v2")
        self.model_name = self.adapter.MODEL_NAMES[model_alias]
        self.constraint = self.model_name == self.adapter.CONSTRAINT_MODEL
        profile = "protenix_constraint" if self.constraint else "protenix"
        self.model_root = self.root / "models" / profile
        os.environ["PROTENIX_ROOT_DIR"] = str(self.model_root)
        os.environ["MPLCONFIGDIR"] = str(self.root / "matplotlib_cache")
        checkpoint = self.model_root / "checkpoint" / f"{self.model_name}.pt"
        if not checkpoint.is_file():
            die(f"Protenix checkpoint is missing: {checkpoint}")
        if self.constraint:
            executable = self.root / "venvs" / "NanoHunter_protenix_constraint" / "bin" / "protenix"
            self.adapter.audit_constraint_runtime(
                executable, checkpoint, self.model_root / "install_receipt.json"
            )
        from runner.batch_inference import get_default_runner
        cycles, steps = (4, 5) if self.model_name == "protenix_mini_default_v0.5.0" else (10, 200)
        self.seeds = [int(value) for value in str(config.get("seed", 42)).split(",")]
        self.samples = int(config.get("samples", 1))
        self.runner = get_default_runner(
            seeds=self.seeds,
            n_cycle=cycles,
            n_step=steps,
            n_sample=self.samples,
            dtype="fp32",
            model_name=self.model_name,
            use_msa=bool(config.get("use_msa", True)),
            trimul_kernel="torch",
            triatt_kernel="torch",
            enable_cache=False,
            enable_fusion=False,
            enable_tf32=False,
            use_template=False,
            use_rna_msa=False,
            use_seeds_in_json=False,
            need_atom_confidence=True,
            use_tfg_guidance=False,
        )
        self.model_load_count = 1

    def predict(self, source: Path, output: Path, expected: int) -> None:
        from runner.inference import infer_predict
        yaml_paths = sorted(source.glob("*.yaml"))
        converted = [self.adapter.convert_yaml(path.resolve(), self.constraint) for path in yaml_paths]
        jobs = [item[0] for item in converted]
        if len(jobs) != expected:
            die(f"Protenix expected {expected} inputs, found {len(jobs)}")
        names = [job["name"] for job in jobs]
        if len(names) != len(set(names)):
            die("Protenix input names are not unique")
        output.mkdir(parents=True, exist_ok=True)
        self.adapter.materialize_single_sequence_msas(converted, output / "single_sequence_msas")
        has_real = {item[2] for item in converted}
        configured = bool(self.config.get("use_msa", True))
        if has_real != {configured}:
            die(f"Protenix resident MSA policy mismatch: inputs={sorted(has_real)}, configured={configured}")
        input_json = output / "protenix_input.json"
        input_json.write_text(json.dumps(jobs, indent=2) + "\n")
        configs = self.runner.configs
        configs.input_json_path = str(input_json)
        configs.dump_dir = str(output)
        self.runner.configs = configs
        self.runner.init_basics()
        self.runner.init_dumper(need_atom_confidence=True, sorted_by_ranking_score=True)
        infer_predict(self.runner, configs)
        self.adapter.annotate_protenix(output, jobs)
        self.adapter.normalize(output, names, len(self.seeds) * self.samples)
        if self.constraint:
            self.adapter.annotate_constraint_geometry(output, jobs)


def make_session(config: dict[str, Any]) -> Any:
    engine = config["engine"]
    if engine == "boltz":
        return BoltzSession(config)
    if engine == "intellifold":
        return IntelliFoldSession(config)
    if engine in {"protenix-v2", "protenix-mini", "protenix-constraint-v0.5"}:
        return ProtenixSession(config)
    die(f"unsupported resident engine {engine}")


def allocated_mps_bytes(torch_module: Any) -> int | None:
    if hasattr(torch_module.mps, "driver_allocated_memory"):
        return int(torch_module.mps.driver_allocated_memory())
    return None


def serve(config_path: Path) -> None:
    config_path = config_path.expanduser().resolve()
    config = json.loads(config_path.read_text())
    queue = Path(config["queue"]).expanduser().resolve()
    requests = queue / "requests"
    responses = queue / "responses"
    requests.mkdir(parents=True, exist_ok=True)
    responses.mkdir(parents=True, exist_ok=True)
    started = time.time()
    session = make_session(config)
    atomic_json(queue / "ready.json", {
        "schema": 1,
        "pid": os.getpid(),
        "engine": config["engine"],
        "model": config.get("model"),
        "device": "mps",
        "fallback": 0,
        "model_load_count": session.model_load_count,
        "config_sha256": sha256(config_path),
        "ready_epoch": time.time(),
        "startup_seconds": time.time() - started,
        "mps_driver_allocated_bytes": allocated_mps_bytes(session.torch),
    })
    while True:
        owner_pid = int(config.get("owner_pid", 0))
        if owner_pid:
            try:
                os.kill(owner_pid, 0)
            except ProcessLookupError:
                atomic_json(queue / "stopped.json", {
                    "pid": os.getpid(), "stopped_epoch": time.time(),
                    "model_load_count": session.model_load_count,
                    "reason": "owner process exited",
                })
                return
        if (queue / "stop.json").is_file():
            atomic_json(queue / "stopped.json", {
                "pid": os.getpid(), "stopped_epoch": time.time(),
                "model_load_count": session.model_load_count,
            })
            return
        pending = [path for path in sorted(requests.glob("request_*.json"))
                   if not (responses / path.name).is_file()]
        if not pending:
            atomic_json(queue / "heartbeat.json", {"pid": os.getpid(), "epoch": time.time()})
            time.sleep(0.1)
            continue
        request_path = pending[0]
        request = json.loads(request_path.read_text())
        response_path = responses / request_path.name
        request_started = time.time()
        try:
            source = Path(request["input_dir"]).resolve()
            output = Path(request["output_dir"]).resolve()
            expected = int(request["expected_jobs"])
            actual_digest, paths = input_digest(source)
            if actual_digest != request["input_sha256"]:
                die("request input checksum changed before execution")
            if len(paths) != expected:
                die(f"request expected {expected} YAML files, found {len(paths)}")
            output.mkdir(parents=True, exist_ok=True)
            before = allocated_mps_bytes(session.torch)
            session.predict(source, output, expected)
            after_digest, after_paths = input_digest(source)
            if after_digest != actual_digest or len(after_paths) != expected:
                die("request inputs changed during execution")
            atomic_json(response_path, {
                "schema": 1,
                "ok": True,
                "request_id": request["request_id"],
                "input_sha256": actual_digest,
                "completed_jobs": expected,
                "start_epoch": request_started,
                "end_epoch": time.time(),
                "wall_seconds": time.time() - request_started,
                "model_load_count": session.model_load_count,
                "mps_driver_allocated_before_bytes": before,
                "mps_driver_allocated_after_bytes": allocated_mps_bytes(session.torch),
            })
        except Exception as exc:
            atomic_json(response_path, {
                "schema": 1,
                "ok": False,
                "request_id": request.get("request_id"),
                "start_epoch": request_started,
                "end_epoch": time.time(),
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "model_load_count": getattr(session, "model_load_count", None),
            })
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--daemonize", action="store_true")
    args = parser.parse_args()
    if args.daemonize:
        first = os.fork()
        if first:
            os._exit(0)
        os.setsid()
        second = os.fork()
        if second:
            os._exit(0)
        sys.stdin.close()
    serve(args.config)


if __name__ == "__main__":
    main()
