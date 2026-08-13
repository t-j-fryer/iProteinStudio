#!/usr/bin/env python3
"""Benchmark concurrent, internally batched RFD3 jobs with different shapes."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PEAK_RE = re.compile(r"^\s*(\d+)\s+peak memory footprint\s*$", re.MULTILINE)


def memory_free_percent() -> float | None:
    result = subprocess.run(["memory_pressure", "-Q"], capture_output=True, text=True)
    match = re.search(r"System-wide memory free percentage:\s*([0-9.]+)%", result.stdout)
    return float(match.group(1)) if match else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    processes = []
    started = time.time()
    env = os.environ.copy()
    env.update({"DEBUG": "false", "TOKENIZERS_PARALLELISM": "false"})
    for job in config["jobs"]:
        job_output = output / job["name"]
        log_path = output / f"{job['name']}.log"
        command = [
            "/usr/bin/time", "-l", str(ROOT / ".venv/bin/python"),
            str(ROOT / "scripts/generate_backbones.py"),
            "--fixture", str((ROOT / job["fixture"]).resolve()),
            "--output", str(job_output),
            "--num-designs", str(job["num_designs"]),
            "--steps", str(job.get("steps", 200)),
            "--recycle", str(job.get("recycle", 2)),
            "--batch-size", str(job["batch_size"]),
            "--precision", job.get("precision", "bf16"),
            "--seed-start", str(job["seed_start"]),
        ]
        if job.get("ligand_code"):
            command += ["--ligand-code", job["ligand_code"]]
        handle = log_path.open("w")
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
        processes.append((job, process, handle, log_path))

    memory_samples = []
    while any(process.poll() is None for _, process, _, _ in processes):
        free = memory_free_percent()
        if free is not None:
            memory_samples.append(free)
        time.sleep(2)
    wall = time.time() - started
    rows = []
    failures = []
    for job, process, handle, log_path in processes:
        handle.close()
        log = log_path.read_text()
        peak = PEAK_RE.search(log)
        if process.returncode != 0:
            failures.append(job["name"])
        rows.append({
            "job": job["name"],
            "return_code": process.returncode,
            "binder_design_tokens": job["binder_design_tokens"],
            "batch_size": job["batch_size"],
            "num_designs": job["num_designs"],
            "peak_physical_footprint_gb": float(peak.group(1)) / 1e9 if peak else "",
            "log": str(log_path),
        })
    summary = {
        "wall_sec": wall,
        "total_designs": sum(job["num_designs"] for job, *_ in processes),
        "sec_per_design": wall / sum(job["num_designs"] for job, *_ in processes),
        "minimum_system_memory_free_percent": min(memory_samples) if memory_samples else None,
        "failures": failures,
        "jobs": rows,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (output / "jobs.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary, indent=2))
    if failures:
        raise SystemExit(f"Failed jobs: {', '.join(failures)}")


if __name__ == "__main__":
    main()
