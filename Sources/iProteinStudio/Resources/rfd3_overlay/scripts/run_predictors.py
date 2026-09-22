#!/usr/bin/env python3
"""Run RFdiffusion verification predictors with measured model-load policies.

Boltz, IntelliFold and Protenix Mini keep one native-MPS model resident for all
pending designs in this invocation. Full Protenix v2 deliberately uses one
directory wave: the governed iterative-design benchmark found that faster than
keeping its model resident. OpenFold retains its validated per-input adapter
until it has an equivalent resident implementation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rfd3_resume import bind_inputs, save_receipt, verify_receipt, sha256


SUPPORTED = {"boltz", "intellifold", "protenix-v2", "protenix-mini", "openfold-3-mlx"}
RETIRED = {"alphafold3", "intellifold-jax"}
RESIDENT_PREDICTORS = {"boltz", "intellifold", "protenix-mini"}
CYCLE_WAVE_PREDICTORS = {"protenix-v2"}


def shared_registry(root=None):
    candidates = [Path(__file__).resolve().parents[2] / 'pipeline/scripts', Path(__file__).resolve().parents[1] / 'scripts']
    if root is not None: candidates.insert(0, Path(root) / 'scripts')
    registry = next((p for p in candidates if (p / 'engine_registry.json').is_file()), None)
    if registry is None: registry = default_root() / 'scripts'
    if not (registry / 'engine_registry.json').is_file(): raise RuntimeError('The shared engine registry is missing; update Studio.')
    sys.path.insert(0, str(registry))
    import engine_registry
    return engine_registry


def scheduling_policy(predictor: str) -> str:
    return shared_registry().scheduling_policy(predictor)


def input_digest(directory: Path) -> tuple[str, list[Path]]:
    paths = sorted(directory.glob("*.yaml"))
    if not paths:
        raise RuntimeError(f"no YAML inputs found in {directory}")
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.resolve().read_bytes())
        digest.update(b"\0")
    return digest.hexdigest(), paths


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def terminate_process(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def yaml_uses_real_msa(path: Path) -> bool:
    """Read Studio's explicit MSA policy without a server or silent default."""
    values = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("msa:"):
            continue
        value = stripped.split(":", 1)[1].strip().strip("'\"")
        if not value:
            raise RuntimeError(f"empty msa field in {path}")
        values.append(value)
    if not values:
        raise RuntimeError(f"no explicit msa field in {path}")
    return any(value.lower() != "empty" for value in values)


def command_for(predictor: str, yaml_path: Path, output: Path, root: Path,
                intellifold_model: str):
    shared_registry(root)
    from engine_adapters import command_for as adapter
    return adapter(predictor, yaml_path, output, root, intellifold_model, Path(__file__).resolve().parent)


def resident_spec(predictor: str, root: Path, intellifold_model: str,
                  use_msa: bool) -> tuple[Path, dict, dict]:
    shared_registry(root)
    from engine_adapters import resident_spec as adapter
    return adapter(predictor, root, intellifold_model, use_msa)


class ResidentWorker:
    """One checksummed file-queue worker and one pinned model."""

    def __init__(self, predictor: str, root: Path, output: Path,
                 intellifold_model: str, use_msa: bool) -> None:
        stamp = f"{int(time.time())}_{os.getpid()}_{uuid.uuid4().hex[:8]}"
        self.predictor = predictor
        self.queue = output / "_scheduler" / f"resident_{predictor}_{stamp}"
        self.queue.mkdir(parents=True, exist_ok=False)
        self.log = self.queue / "worker.log"
        python, config, env = resident_spec(predictor, root, intellifold_model, use_msa)
        config["queue"] = str(self.queue)
        self.config = self.queue / "config.json"
        atomic_json(self.config, config)
        self._log_handle = self.log.open("w")
        self.process = None
        try:
            self.process = subprocess.Popen(
                [str(python), str(root / "scripts" / "resident_predictor.py"),
                 "--config", str(self.config)],
                cwd=root, env=env, stdout=self._log_handle, stderr=subprocess.STDOUT,
            )
            self._wait_ready()
        except BaseException:
            if self.process is not None:
                terminate_process(self.process)
            self._log_handle.close()
            raise

    def _wait_ready(self) -> None:
        ready_path = self.queue / "ready.json"
        deadline = time.time() + 1800
        while not ready_path.is_file():
            if self.process.poll() is not None:
                self._log_handle.flush()
                raise RuntimeError(
                    f"resident {self.predictor} exited while loading; see {self.log}")
            if time.time() >= deadline:
                self.process.terminate()
                raise RuntimeError(
                    f"resident {self.predictor} did not become ready within 30 minutes")
            time.sleep(0.1)
        self.ready = json.loads(ready_path.read_text())
        if (self.ready.get("pid") != self.process.pid or self.ready.get("device") != "mps"
                or self.ready.get("fallback") != 0 or self.ready.get("model_load_count") != 1):
            self.process.terminate()
            raise RuntimeError(f"resident {self.predictor} returned an invalid readiness receipt")

    def submit(self, yaml_path: Path, output: Path, index: int) -> tuple[dict, Path]:
        request_id = f"job_{index:05d}_{yaml_path.stem}"
        source = self.queue / "job_inputs" / request_id
        source.mkdir(parents=True, exist_ok=False)
        shutil.copy2(yaml_path, source / yaml_path.name)
        digest, paths = input_digest(source)
        request_path = self.queue / "requests" / f"request_{request_id}.json"
        response_path = self.queue / "responses" / request_path.name
        atomic_json(request_path, {
            "schema": 1, "request_id": request_id, "input_dir": str(source.resolve()),
            "output_dir": str(output.resolve()), "expected_jobs": len(paths),
            "input_sha256": digest, "submitted_epoch": time.time(),
        })
        while not response_path.is_file():
            if self.process.poll() is not None:
                self._log_handle.flush()
                raise RuntimeError(
                    f"resident {self.predictor} died during {request_id}; see {self.log}")
            time.sleep(0.1)
        receipt = json.loads(response_path.read_text())
        if (not receipt.get("ok") or receipt.get("request_id") != request_id
                or receipt.get("completed_jobs") != 1
                or receipt.get("model_load_count") != 1):
            raise RuntimeError(
                f"resident {self.predictor} request failed: "
                f"{receipt.get('error', 'invalid receipt')}")
        return receipt, response_path

    def stop(self) -> None:
        if self.process.poll() is None:
            atomic_json(self.queue / "stop.json", {
                "requested_epoch": time.time(), "requester_pid": os.getpid(),
            })
            deadline = time.time() + 120
            while self.process.poll() is None and time.time() < deadline:
                time.sleep(0.1)
            if self.process.poll() is None:
                terminate_process(self.process)
        self._log_handle.close()
        stopped = self.queue / "stopped.json"
        if self.process.returncode == 0 and not stopped.is_file():
            raise RuntimeError(f"resident {self.predictor} stopped without a receipt")



def protenix_wave_command(inputs: Path, output: Path, root: Path) -> tuple[list[str], dict]:
    venv = root / "venvs" / "NanoHunter_protenix"
    env = os.environ.copy()
    env.update({
        "PATH": f"{venv / 'bin'}:{env.get('PATH', '')}",
        "VIRTUAL_ENV": str(venv),
        "PROTENIX_ROOT_DIR": str(root / "models" / "protenix"),
    })
    env.pop("PYTORCH_ENABLE_MPS_FALLBACK", None)
    return [
        str(venv / "bin" / "python"), str(root / "scripts" / "protenix_predict.py"),
        "--inputs", str(inputs), "--output", str(output),
        "--nanohunter-root", str(root), "--model", "v2",
    ], env


def parse_metrics(output: Path) -> dict:
    # Boltz prefixes confidence_ while IntelliFold suffixes
    # _summary_confidences. Prefer summary files over per-atom confidence data.
    confidence_files = sorted(output.rglob("*summary_confidences.json"))
    if not confidence_files:
        confidence_files = sorted(output.rglob("confidence*.json"))
    cifs = sorted(output.rglob("*.cif"))
    metrics: dict = {}
    confidence_path = confidence_files[0] if confidence_files else None
    if confidence_path:
        data = json.loads(confidence_path.read_text())
        for key in (
            "iptm", "ptm", "plddt", "complex_plddt", "confidence_score", "ranking_score",
            "ligand_iptm", "protein_iptm", "has_clash", "complex_iplddt", "complex_ipde",
            "ipsae_min",
        ):
            value = data.get(key)
            if isinstance(value, (int, float)):
                metrics[key] = value
    metrics["confidence_json"] = str(confidence_path) if confidence_path else ""
    metrics["structure"] = str(cifs[0]) if cifs else ""
    return metrics


def ensure_ipsae(predictor: str, yaml_path: Path, output: Path, root: Path,
                  log_path: Path) -> None:
    """Boltz needs a post-run adapter; other engines annotate in their launchers."""
    if predictor != "boltz":
        return
    command = [
        str(root / "venvs" / "NanoHunter_boltz" / "bin" / "python"),
        str(root / "scripts" / "ipsae_score.py"), "boltz",
        "--yaml", str(yaml_path), "--output", str(output),
    ]
    with log_path.open("a") as handle:
        completed = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT)
    if completed.returncode:
        raise SystemExit(
            f"{predictor} produced a structure but ipSAE scoring failed for {yaml_path}; "
            f"see {log_path}"
        )


def record_prediction(rows: list[dict], row: dict) -> None:
    if row.get("exit_code") == 0:
        required = [row.get("structure"), row.get("confidence_json")]
        if not all(p and Path(p).is_file() and Path(p).stat().st_size for p in required):
            raise RuntimeError(f"Predictor exited successfully without complete outputs: {row['design']}")
        receipt = Path(row["output_dir"]) / "studio_prediction_receipt.json"
        identity = json.loads((Path(row["output_dir"]) / "studio_prediction_request.json").read_text())
        if not verify_receipt(receipt, identity):
            save_receipt(receipt, identity, [Path(p) for p in required])
    rows.append(row)


def write_csv(rows: list[dict], path: Path) -> None:
    fields = sorted({key for row in rows for key in row})
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def default_root() -> Path:
    """Where venvs/ and src/ live.

    From the environment the app sets, else this checkout's parent -- rfd3 is
    installed inside the pipeline root. Never a hard-coded home directory:
    that is one developer's machine, not the user's.
    """
    env = os.environ.get("NANOHUNTER_ROOT") or os.environ.get("IPROTEIN_ROOT")
    if env:
        return Path(env)
    # Installed layout is <root>/rfd3/scripts/, so the root is two levels up.
    # Verify rather than assume: a standalone checkout has no venvs/ above it,
    # and silently pointing at a home directory would be worse than saying so.
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "venvs").is_dir():
        return candidate
    raise SystemExit(
        "Cannot locate the pipeline root (no venvs/ found). "
        "Set NANOHUNTER_ROOT, or pass --nanohunter-root explicitly.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--predictors", default="boltz,intellifold")
    parser.add_argument("--max-parallel", type=int, default=4)
    parser.add_argument("--intellifold-model", choices=("v2-flash", "v2"), default="v2-flash")
    parser.add_argument("--nanohunter-root", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.max_parallel < 1:
        raise SystemExit("--max-parallel must be at least 1")
    args.nanohunter_root = args.nanohunter_root or default_root()
    predictors = [value.strip() for value in args.predictors.split(",") if value.strip()]
    retired = [value for value in predictors if value in RETIRED]
    if retired:
        raise SystemExit(f"retired predictors cannot run: {', '.join(retired)}")
    supported = shared_registry(args.nanohunter_root).predictors()
    unknown = [v for v in predictors if v not in supported]
    if not predictors or unknown:
        raise SystemExit(f"--predictors must be drawn from {sorted(supported)}; got {unknown}")
    predictors = list(dict.fromkeys(predictors))
    if any(value.startswith("protenix-") for value in predictors):
        args.max_parallel = 1
    yamls = sorted(args.inputs.resolve().glob("*.yaml"))
    if not yamls:
        raise SystemExit(f"No YAML inputs in {args.inputs}")

    root = args.nanohunter_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Hash exact YAML content and external alignment contents, not just names.
    inputs = {}
    for path in yamls:
        msas = {}
        entries = []
        if yaml_uses_real_msa(path):
            import yaml
            entries = yaml.safe_load(path.read_text()).get("sequences", [])
        for entry in entries:
            msa = entry.get("protein", {}).get("msa")
            if msa and msa != "empty":
                msa_path = Path(msa)
                if not msa_path.is_absolute():
                    msa_path = path.parent / msa_path
                msas[str(msa_path)] = sha256(msa_path)
        inputs[path.name] = {"yaml": sha256(path), "msas": msas}
    specification = {"inputs": inputs, "predictors": predictors,
                     "intellifold_model": args.intellifold_model, "root": str(root)}
    bind_inputs(output / "studio_prediction_request.json", specification)
    previous: dict[tuple[str, str], dict] = {}
    previous_csv = output / "prediction_metrics.csv"
    if previous_csv.exists():
        for row in csv.DictReader(previous_csv.open()):
            previous[(row.get("predictor", ""), row.get("design", ""))] = dict(row)
    rows: list[dict] = []
    pending: dict[str, list[tuple[Path, Path]]] = {predictor: [] for predictor in predictors}
    for predictor in predictors:
        for yaml_path in yamls:
            job_out = output / predictor / yaml_path.stem
            job_out.mkdir(parents=True, exist_ok=True)
            identity = {"input": inputs[yaml_path.name], "predictor": predictor,
                        "intellifold_model": args.intellifold_model}
            receipt = job_out / "studio_prediction_receipt.json"
            verified = verify_receipt(receipt, identity)
            cached = parse_metrics(job_out)
            if args.resume and verified:
                prior = previous.get((predictor, yaml_path.stem), {})
                record_prediction(rows, {
                    **prior, "design": yaml_path.stem, "predictor": predictor, "exit_code": 0,
                    "wall_sec": prior.get("wall_sec", 0.0), "reused": 1,
                    "scheduler": prior.get("scheduler", scheduling_policy(predictor)),
                    "input_yaml": str(yaml_path), "output_dir": str(job_out),
                    "log": str(job_out / "predict.log"), **cached,
                })
                continue
            # Preserve uncommitted/legacy output rather than mixing old and new
            # structures when a predictor is retried after partial failure.
            if any(job_out.iterdir()):
                archive = output / "_interrupted" / uuid.uuid4().hex / predictor
                archive.mkdir(parents=True)
                job_out.rename(archive / job_out.name)
                job_out.mkdir()
            bind_inputs(job_out / "studio_prediction_request.json", identity)
            pending[predictor].append((yaml_path, job_out))

    campaign_start = time.time()
    for predictor in predictors:
        jobs = pending[predictor]
        if not jobs:
            continue
        policy = scheduling_policy(predictor)
        print(f"{predictor}: scheduler={policy}, pending={len(jobs)}", flush=True)

        if policy == "resident":
            msa_policies = {yaml_uses_real_msa(yaml_path) for yaml_path, _ in jobs}
            if len(msa_policies) != 1:
                raise SystemExit(
                    f"{predictor} resident stage mixes real-MSA and single-sequence inputs")
            worker = None
            try:
                worker = ResidentWorker(
                    predictor, root, output, args.intellifold_model, msa_policies.pop())
                for index, (yaml_path, job_out) in enumerate(jobs, 1):
                    log_path = job_out / "predict.log"
                    started = time.time()
                    receipt, response_path = worker.submit(yaml_path, job_out, index)
                    wall = time.time() - started
                    log_path.write_text(
                        f"scheduler=resident\nworker_log={worker.log}\n"
                        f"request_receipt={response_path}\nmodel_load_count=1\n")
                    ensure_ipsae(predictor, yaml_path, job_out, root, log_path)
                    record_prediction(rows, {
                        "design": yaml_path.stem, "predictor": predictor, "exit_code": 0,
                        "wall_sec": wall, "reused": 0, "scheduler": policy,
                        "model_load_count": receipt["model_load_count"],
                        "worker_startup_sec": worker.ready.get("startup_seconds", ""),
                        "resident_session": str(worker.queue),
                        "request_wall_sec": receipt["wall_seconds"],
                        "input_yaml": str(yaml_path), "output_dir": str(job_out),
                        "log": str(log_path), "command": "resident file-queue request",
                        **parse_metrics(job_out),
                    })
                    write_csv(rows, output / "prediction_metrics.csv")
                    print(f"{predictor} {yaml_path.stem}: resident rc=0, {wall:.1f}s", flush=True)
            finally:
                if worker is not None:
                    worker.stop()
            continue

        if policy == "cycle-wave":
            wave = output / "_scheduler" / f"wave_{predictor}_{int(time.time())}_{os.getpid()}"
            inputs = wave / "inputs"
            inputs.mkdir(parents=True, exist_ok=False)
            for yaml_path, _ in jobs:
                shutil.copy2(yaml_path, inputs / yaml_path.name)
            command, env = protenix_wave_command(inputs, output / predictor, root)
            log_path = wave / "predict.log"
            started = time.time()
            with log_path.open("w") as handle:
                completed = subprocess.run(
                    command, cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT)
            wave_wall = time.time() - started
            for yaml_path, job_out in jobs:
                record_prediction(rows, {
                    "design": yaml_path.stem, "predictor": predictor,
                    "exit_code": completed.returncode, "wall_sec": wave_wall / len(jobs),
                    "wave_wall_sec": wave_wall, "wave_size": len(jobs), "reused": 0,
                    "scheduler": policy, "model_load_count": 1,
                    "input_yaml": str(yaml_path), "output_dir": str(job_out),
                    "log": str(log_path), "command": json.dumps(command),
                    **parse_metrics(job_out),
                })
                write_csv(rows, output / "prediction_metrics.csv")
            print(f"{predictor}: cycle-wave rc={completed.returncode}, {wave_wall:.1f}s", flush=True)
            continue

        queue = []
        for yaml_path, job_out in jobs:
            command, env = command_for(
                predictor, yaml_path, job_out, root, args.intellifold_model)
            queue.append((yaml_path, job_out, command, env))
        running = []
        try:
            while queue or running:
                while queue and len(running) < args.max_parallel:
                    yaml_path, job_out, command, env = queue.pop(0)
                    log_path = job_out / "predict.log"
                    handle = log_path.open("w")
                    started = time.time()
                    try:
                        proc = subprocess.Popen(
                            command, cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT)
                    except BaseException:
                        handle.close()
                        raise
                    running.append((proc, handle, started, yaml_path, job_out, log_path, command))
                time.sleep(0.25)
                for job in list(running):
                    proc, handle, started, yaml_path, job_out, log_path, command = job
                    if proc.poll() is None:
                        continue
                    handle.close()
                    wall = time.time() - started
                    record_prediction(rows, {
                        "design": yaml_path.stem, "predictor": predictor,
                        "exit_code": proc.returncode, "wall_sec": wall, "reused": 0,
                        "scheduler": policy, "model_load_count": 1,
                        "input_yaml": str(yaml_path), "output_dir": str(job_out),
                        "log": str(log_path), "command": json.dumps(command),
                        **parse_metrics(job_out),
                    })
                    write_csv(rows, output / "prediction_metrics.csv")
                    print(f"{predictor} {yaml_path.stem}: rc={proc.returncode}, {wall:.1f}s", flush=True)
                    running.remove(job)
        finally:
            for proc, handle, *_ in running:
                terminate_process(proc)
                handle.close()

    campaign_wall = time.time() - campaign_start
    write_csv(rows, output / "prediction_metrics.csv")
    failures = sum(row["exit_code"] != 0 for row in rows)
    manifest = {
        "num_designs": len(yamls), "predictors": predictors, "max_parallel": args.max_parallel,
        "scheduling": {predictor: scheduling_policy(predictor) for predictor in predictors},
        "num_jobs": len(rows), "num_failures": failures, "wall_sec": campaign_wall,
        "predictions_per_min": len(rows) / (campaign_wall / 60) if campaign_wall else None,
    }
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if failures:
        raise SystemExit(f"{failures} predictor jobs failed; see {output / 'prediction_metrics.csv'}")
    print(f"completed {len(rows)} predictions in {campaign_wall:.1f}s")


if __name__ == "__main__":
    main()
