#!/usr/bin/env python3
"""Fold a batch of sequences — no design, just prediction.

The design tabs drive a whole campaign; this drives a list of folds. What makes
it worth having as its own thing is everything around the folding:

**MSA reuse.** Generating an MSA is a network round trip that often costs more
than the fold itself, and the same target gets folded over and over across a
project. Every MSA this pipeline has ever produced is indexed by the sequence it
describes, so a target that was aligned once during a design campaign is never
aligned again. New ones are generated once and land in the same shared cache.

**Per-chain MSA policy.** A de-novo binder has no homologues, so aligning it is
pure cost and mild harm; its partner usually needs a deep MSA. Policy is per
chain, not per job.

**Scheduling.** Predictors differ enormously in how they want to be run. Jobs
are grouped by token bucket so a compiled shape is reused, and each accelerator
path gets the concurrency and batch size measured fastest for it.

Progress markers on stdout:
    PBSTAGE|<name>|<0-100>|<message>
    PBINFO|<message>
    PBDONE|ok
    PBFAIL|<message>
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Measured best schedules on the reference workload (96-aa SUMO, cached MSA,
# M4 Max). `batch` is how many inputs one loaded process is given — for these
# backends that is sequential model reuse, not a tensor batch, and it is what
# amortises model load and shape compilation.
SCHEDULE = {
    "boltz":            {"processes": 1, "batch": 8},
    "boltz_potentials": {"processes": 2, "batch": 4},
    "intellifold":      {"processes": 4, "batch": 16},
    # One loaded MPS process handles a directory of inputs. These are the only
    # schedules validated for the patched native-MPS implementation.
    "protenix-v2":      {"processes": 1, "batch": 8},
    "protenix-mini":    {"processes": 1, "batch": 8},
    "openfold-3-mlx":   {"processes": 2, "batch": 1},   # per-job adapter, no directory mode
}
# Backends that accept a directory of inputs and load the model once.
DIRECTORY_CAPABLE = {"boltz", "boltz_potentials", "intellifold",
                     "protenix-v2", "protenix-mini"}
BUCKETS = (128, 256, 384, 512, 768, 1024, 1536, 2048, 3072, 4096)


def stage(name: str, pct: int, message: str) -> None:
    print(f"PBSTAGE|{name}|{pct}|{message}", flush=True)


def info(message: str) -> None:
    print(f"PBINFO|{message}", flush=True)


def die(message: str) -> None:
    print(f"PBFAIL|{message}", flush=True)
    sys.exit(1)


def validate_config(cfg: dict, jobs: list) -> list[str]:
    supported = set(SCHEDULE)
    predictors = cfg.get("predictors") or ["boltz"]
    retired = [p for p in predictors if p in {"alphafold3", "intellifold-jax"}]
    if retired:
        die("Retired predictor(s) cannot run: " + ", ".join(retired))
    unknown = [p for p in predictors if p not in supported or p == "boltz_potentials"]
    if unknown:
        die("Unsupported predictor(s): " + ", ".join(unknown))
    if len(set(predictors)) != len(predictors):
        die("Each predictor may be selected only once.")
    if "intellifold" in predictors:
        if cfg.get("intellifold_model") not in {"v2-flash", "v2"}:
            die("IntelliFold requires intellifold_model v2-flash or v2.")
    for key in ("max_parallel", "batch_size", "diffusion_samples"):
        if int(cfg.get(key, 0)) < 0:
            die(f"{key} cannot be negative.")
    if not 1 <= int(cfg.get("num_seeds", 1)) <= 20:
        die("num_seeds must be between 1 and 20.")
    if int(cfg.get("diffusion_samples", 0)) > 20:
        die("diffusion_samples must be 0–20; 0 preserves each engine's existing default.")
    names = [str(job.get("name", "")).strip() for job in jobs]
    if any(not name for name in names) or len(set(names)) != len(names):
        die("Every fold needs a unique, non-empty name.")
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", name)
           for name in names):
        die("Fold names must be 1–80 safe filename characters and start with a letter or number.")
    for job in jobs:
        chains = job.get("chains") or []
        if not chains:
            die(f"{job['name']} has no chains.")
        chain_ids = [str(chain.get("id", "")).strip() for chain in chains]
        if any(not chain_id for chain_id in chain_ids) or len(set(chain_ids)) != len(chain_ids):
            die(f"{job['name']} needs unique, non-empty chain IDs.")
        for chain in chains:
            kind = chain.get("kind")
            if kind == "protein" and len(canonical(chain.get("sequence", ""))) < 5:
                die(f"{job['name']} has an empty or too-short protein chain.")
            if kind == "ligand" and not str(chain.get("smiles", "")).strip():
                die(f"{job['name']} has an empty ligand SMILES.")
            if kind not in {"protein", "ligand"}:
                die(f"{job['name']} has unsupported chain kind {kind!r}.")
    return predictors


def structure_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()
            and path.suffix.lower() in {".cif", ".pdb"}]


def has_structure_for_job(root: Path, name: str) -> bool:
    for path in structure_files(root):
        if name in path.parts or path.stem == name:
            return True
        if path.stem.startswith((f"{name}_", f"{name}-")):
            return True
    return False


def completed_chunk(marker: Path, names: list[str], output: Path) -> bool:
    try:
        payload = json.loads(marker.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return payload.get("jobs") == names and all(has_structure_for_job(output, name) for name in names)


# ------------------------------------------------------------------ MSA cache --

def canonical(sequence: str) -> str:
    return "".join(c for c in (sequence or "").upper() if c.isalpha())


def sequence_key(sequence: str) -> str:
    return hashlib.sha256(canonical(sequence).encode()).hexdigest()[:32]


def a3m_query(path: Path) -> str:
    """The sequence an A3M describes, with insertions and gaps removed.

    Every consumer checks that the first record matches the chain it is attached
    to; a mismatch is the classic way a reused MSA silently corrupts a run. So
    the index is keyed on this, not on a filename.
    """
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return ""
    records = [r for r in text.split(">") if r.strip()]
    if not records:
        return ""
    body = "".join(records[0].splitlines()[1:])
    return "".join(c for c in body if not c.islower() and c not in "-.").upper()


def valid_a3m(path: Path, sequence: str) -> bool:
    try:
        depth = path.read_text(errors="replace").count(">")
    except OSError:
        return False
    return depth >= 2 and a3m_query(path) == canonical(sequence)


def build_index(cache_dir: Path, roots: list[Path], limit: int = 40000) -> dict:
    """Index every A3M this machine already has, by the sequence it describes.

    Cheap enough to redo on every run (reading one record per file), and doing so
    means an MSA generated by a design campaign five minutes ago is immediately
    available here without anyone wiring the two together.
    """
    index_path = cache_dir / "index.json"
    index = {}
    seen_files = {}
    if index_path.exists():
        try:
            stored = json.loads(index_path.read_text())
            index = stored.get("by_sequence", {})
            seen_files = stored.get("files", {})
        except Exception:
            index, seen_files = {}, {}

    scanned = 0
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.a3m"):
            if scanned >= limit:
                break
            key = str(path)
            try:
                stamp = f"{path.stat().st_mtime_ns}:{path.stat().st_size}"
            except OSError:
                continue
            if seen_files.get(key) == stamp:
                continue
            scanned += 1
            query = a3m_query(path)
            depth = path.read_text(errors="replace").count(">")
            if len(query) < 12 or depth < 2:
                seen_files[key] = stamp
                continue
            digest = sequence_key(query)
            # Prefer the deepest alignment when the same sequence appears twice.
            existing = index.get(digest)
            if not existing or depth > existing.get("depth", 0):
                index[digest] = {"path": str(path), "depth": depth, "length": len(query)}
            seen_files[key] = stamp

    cache_dir.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps({"by_sequence": index, "files": seen_files}, indent=0))
    return index


def generate_msa(sequence: str, cache_dir: Path, root: Path, env: dict,
                 provider: str) -> Path | None:
    """Generate and retain one verified MSA using an installed server client.

    Protenix has its own upstream MSA command, so it must never bring Boltz as
    a hidden dependency. If installed, use it. Do not silently switch providers
    after a Protenix service failure: that would make identical saved settings
    produce different scientific inputs on different machines.
    """
    digest = sequence_key(sequence)
    target = cache_dir / f"{digest}.a3m"
    if target.exists() and valid_a3m(target, sequence):
        return target
    if target.exists():
        target.unlink()

    work = cache_dir / f"_gen_{digest}"
    work.mkdir(parents=True, exist_ok=True)
    protenix = root / "venvs" / "NanoHunter_protenix" / "bin" / "protenix"
    if provider == "protenix":
        if not protenix.exists():
            return None
        adapter = root / "scripts" / "protenix_msa.py"
        if not adapter.is_file():
            return None
        info("Generating the missing alignment with Protenix's MSA server client")
        log = work / "msa.log"
        with log.open("w") as handle:
            result = subprocess.run(
                [str(protenix.parent / "python"), str(adapter),
                 "--sequence", canonical(sequence), "--output", str(target),
                 "--nanohunter-root", str(root),
                 "--work-dir", str(work / "protenix_msa")],
                env=env, stdout=handle, stderr=subprocess.STDOUT)
        if result.returncode == 0 and valid_a3m(target, sequence):
            shutil.rmtree(work, ignore_errors=True)
            return target
        return None

    yaml_path = work / "query.yaml"
    yaml_path.write_text(
        "sequences:\n  - protein:\n      id: A\n"
        f"      sequence: {canonical(sequence)}\n"
        "version: 1\n"
    )
    boltz = root / "venvs" / "NanoHunter_boltz" / "bin" / "boltz"
    if not boltz.exists():
        return None
    info("Generating the missing alignment with Boltz's ColabFold client")
    log = work / "msa.log"
    with log.open("w") as handle:
        result = subprocess.run(
            [str(boltz), "predict", str(yaml_path), "--out_dir", str(work),
             "--use_msa_server", "--msa_server_url", "https://api.colabfold.com",
             "--msa_pairing_strategy", "greedy", "--override"],
            env=env, stdout=handle, stderr=subprocess.STDOUT)
    raw = sorted(work.rglob("msa/*.csv"))
    if result.returncode and not raw:
        return None
    if not raw:
        return None

    rows = list(csv.DictReader(raw[0].open()))
    if not rows:
        return None
    key = "sequence" if "sequence" in rows[0] else list(rows[0])[0]
    lines = [">query", canonical(sequence)]
    for i, row in enumerate(rows):
        seq = (row.get(key) or "").strip()
        if not seq:
            continue
        bare = "".join(c for c in seq if not c.islower() and c not in "-.").upper()
        if i == 0 and bare == canonical(sequence):
            continue
        lines += [f">seq{i}", seq]
    if len(lines) < 4:
        return None
    partial = target.with_suffix(target.suffix + ".part")
    partial.write_text("\n".join(lines) + "\n")
    if not valid_a3m(partial, sequence):
        partial.unlink(missing_ok=True)
        return None
    partial.replace(target)
    shutil.rmtree(work, ignore_errors=True)
    return target


def resolve_msas(jobs: list, cfg: dict, root: Path, env: dict) -> dict:
    """Give every chain that asked for an MSA a real file, reusing what exists."""
    cache_dir = Path(cfg["msa"]["cache_dir"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    roots = [Path(p) for p in cfg["msa"].get("index_roots", [])] + [cache_dir]

    stage("msa", 10, "Looking for alignments we already have")
    index = build_index(cache_dir, roots)
    info(f"{len(index)} distinct sequences already aligned on this machine")

    wanted = {}
    for job in jobs:
        for chain in job["chains"]:
            if chain.get("kind") != "protein":
                continue
            if str(chain.get("msa", "auto")).lower() != "auto":
                continue
            wanted.setdefault(sequence_key(chain["sequence"]), chain["sequence"])

    resolved, hits, misses = {}, 0, 0
    for digest, sequence in wanted.items():
        entry = index.get(digest)
        if entry and valid_a3m(Path(entry["path"]), sequence):
            resolved[digest] = entry["path"]
            hits += 1
    info(f"{hits} of {len(wanted)} needed alignments came from the cache")

    todo = [(d, s) for d, s in wanted.items() if d not in resolved]
    if todo and not cfg["msa"].get("allow_server", True):
        die(f"{len(todo)} sequence(s) have no cached alignment and the MSA server is switched off. "
            f"Either allow it, or set those chains to single-sequence.")
    provider = "protenix" if any(
        value in {"protenix-v2", "protenix-mini"}
        for value in (cfg.get("predictors") or [])
    ) else "boltz"
    for n, (digest, sequence) in enumerate(todo, 1):
        stage("msa", 10 + int(20 * n / max(1, len(todo))),
              f"Generating alignment {n} of {len(todo)}")
        path = generate_msa(sequence, cache_dir, root, env, provider)
        if path is None:
            die("The MSA server could not be reached. A fold without a real alignment is much "
                "worse, so this stops rather than quietly continuing.")
        resolved[digest] = str(path)
        misses += 1
    if misses:
        info(f"{misses} new alignment(s) generated and cached for next time")
    return resolved


def materialize_msas(resolved: dict, input_dir: Path) -> dict:
    """Copy every selected alignment into the durable run inputs.

    The cache index may find an alignment anywhere on the machine, including an
    older checkout. Pointing the saved YAML at that external file makes a run
    impossible to reproduce after the source is moved or deleted. Each run owns
    an exact byte-for-byte copy instead.
    """
    msa_dir = input_dir / "msas"
    msa_dir.mkdir(parents=True, exist_ok=True)
    local = {}
    for digest, source_text in resolved.items():
        source = Path(source_text)
        target = msa_dir / f"{digest}.a3m"
        if not target.exists() or target.read_bytes() != source.read_bytes():
            shutil.copyfile(source, target)
        local[digest] = str(target.resolve())
    return local


# --------------------------------------------------------------------- inputs --

def job_yaml(job: dict, resolved: dict, affinity: bool) -> str:
    lines = ["sequences:"]
    ligand_id = None
    for chain in job["chains"]:
        cid = chain["id"]
        if chain.get("kind") == "ligand":
            ligand_id = cid
            smiles = str(chain.get("smiles", "")).replace("'", "''")
            lines += [f"  - ligand:", f"      id: {cid}", f"      smiles: '{smiles}'"]
            continue
        lines += ["  - protein:", f"      id: {cid}",
                  f"      sequence: {canonical(chain['sequence'])}"]
        policy = str(chain.get("msa", "auto")).lower()
        if policy == "empty":
            lines.append("      msa: empty")
        elif policy == "auto":
            path = resolved.get(sequence_key(chain["sequence"]))
            lines.append(f"      msa: {path}" if path else "      msa: empty")
        else:
            lines.append(f"      msa: {chain['msa']}")
    if affinity and ligand_id:
        lines += ["properties:", "  - affinity:", f"      binder: {ligand_id}"]
    lines.append("version: 1")
    return "\n".join(lines) + "\n"


def token_estimate(job: dict) -> int:
    total = 0
    for chain in job["chains"]:
        if chain.get("kind") == "ligand":
            total += 40
        else:
            total += len(canonical(chain.get("sequence", "")))
    return total


def bucket_for(tokens: int) -> int:
    for bucket in BUCKETS:
        if tokens <= bucket:
            return bucket
    return BUCKETS[-1]


# -------------------------------------------------------------------- running --

def run_directory_batch(predictor: str, yamls: list, out_dir: Path, root: Path,
                        env: dict, cfg: dict, log_path: Path) -> int:
    """One loaded process, several inputs. Amortises model load and compilation."""
    batch_dir = out_dir / "_inputs"
    batch_dir.mkdir(parents=True, exist_ok=True)
    for path in yamls:
        shutil.copyfile(path, batch_dir / path.name)

    if predictor.startswith("boltz"):
        venv = root / "venvs" / "NanoHunter_boltz"
        command = [str(venv / "bin" / "boltz"), "predict", str(batch_dir),
                   "--out_dir", str(out_dir), "--accelerator", "gpu", "--devices", "1",
                   "--num_workers", "0", "--output_format", "mmcif", "--override",
                   "--seed", str(cfg.get("seed", 42))]
        if int(cfg.get("diffusion_samples", 0)) > 0:
            command += ["--diffusion_samples", str(cfg["diffusion_samples"])]
        if predictor == "boltz_potentials":
            command.append("--use_potentials")
        if cfg.get("recycles"):
            command += ["--recycling_steps", str(cfg["recycles"])]
    elif predictor == "intellifold":
        venv = root / "venvs" / "NanoHunter_intellifold"
        env = {**env,
               # IntelliFold only: host BLAS/OpenMP contends with MPS submission.
               "OMP_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1", "KMP_USE_SHM": "0"}
        seed = int(cfg.get("seed", 42))
        num_seeds = int(cfg.get("num_seeds", 1))
        seeds = ",".join(str(seed + offset) for offset in range(num_seeds))
        samples = int(cfg.get("diffusion_samples", 0)) or 1
        command = [str(venv / "bin" / "python"),
                   str(root / "src" / "IntelliFold" / "run_intellifold.py"), str(batch_dir),
                   "--out_dir", str(out_dir), "--precision", "no", "--num_workers", "0",
                   "--seed", seeds, "--num_diffusion_samples", str(samples),
                   "--override", "--model", cfg.get("intellifold_model", "v2-flash"),
                   "--cache", str(root / "models" / "intellifold")]
    else:
        venv = root / "venvs" / "NanoHunter_protenix"
        model = "v2" if predictor == "protenix-v2" else "mini"
        seed = int(cfg.get("seed", 42))
        seeds = ",".join(str(seed + offset)
                         for offset in range(int(cfg.get("num_seeds", 1))))
        samples = int(cfg.get("diffusion_samples", 0)) or 5
        command = [str(venv / "bin" / "python"),
                   str(root / "scripts" / "protenix_predict.py"),
                   "--inputs", str(batch_dir), "--output", str(out_dir),
                   "--nanohunter-root", str(root), "--model", model,
                   "--seeds", seeds, "--samples", str(samples)]

    handle = log_path.open("w")
    return subprocess.Popen(command, env=env, stdout=handle, stderr=subprocess.STDOUT), handle


def run_single(predictor: str, yaml_path: Path, out_dir: Path, root: Path,
               env: dict, log_path: Path, cfg: dict) -> int:
    rfd3 = root / "rfd3"
    adapters = {
        "openfold-3-mlx": ("NanoHunter_openfold3_mlx", "openfold_predict_one.py"),
    }
    venv_name, script = adapters[predictor]
    command = [str(root / "venvs" / venv_name / "bin" / "python"),
               str(rfd3 / "scripts" / script),
               "--yaml", str(yaml_path), "--output", str(out_dir),
               "--nanohunter-root", str(root)]
    command += ["--seed", str(cfg.get("seed", 42)),
                "--num-seeds", str(cfg.get("num_seeds", 1))]
    samples = int(cfg.get("diffusion_samples", 0))
    if samples > 0:
        command += ["--diffusion-samples", str(samples)]
    handle = log_path.open("w")
    return subprocess.Popen(command, cwd=str(rfd3), env=env,
                            stdout=handle, stderr=subprocess.STDOUT), handle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        cfg = json.loads(args.config.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        die(f"Could not read {args.config}: {exc}")

    root = Path(cfg["root"]).resolve()
    output = Path(cfg["output"]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "logs").mkdir(exist_ok=True)
    jobs = cfg.get("jobs") or []
    if not jobs:
        die("No sequences to fold.")
    predictors = validate_config(cfg, jobs)

    if "boltz" in predictors and int(cfg.get("num_seeds", 1)) > 1:
        info("Boltz uses one model seed per fold; the requested seed count applies to the other "
             "engines. Use diffusion samples for additional Boltz structures.")

    env = dict(os.environ)
    env["BOLTZ_CACHE"] = str(root / "models" / "boltz2")
    env["NUMBA_CACHE_DIR"] = str(root / "numba_cache")
    Path(env["NUMBA_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)

    resolved = resolve_msas(jobs, cfg, root, env)

    stage("plan", 32, "Preparing inputs")
    yaml_dir = output / "inputs"
    yaml_dir.mkdir(exist_ok=True)
    resolved = materialize_msas(resolved, yaml_dir)
    prepared = []
    for job in jobs:
        path = yaml_dir / f"{job['name']}.yaml"
        path.write_text(job_yaml(job, resolved, cfg.get("affinity", False)))
        prepared.append({"name": job["name"], "yaml": path,
                         "tokens": token_estimate(job), "bucket": bucket_for(token_estimate(job))})

    if "protenix-v2" in predictors:
        oversized = [item["name"] for item in prepared if item["tokens"] > 2560]
        if oversized:
            die("Protenix v2 supports at most 2,560 tokens; too large: "
                + ", ".join(oversized[:5]))

    started = time.time()
    results = []
    total_units = len(prepared) * len(predictors)
    done_units = 0

    for predictor in predictors:
        key = "boltz_potentials" if (predictor == "boltz" and cfg.get("use_potentials")) else predictor
        plan = SCHEDULE.get(key, {"processes": 1, "batch": 1})
        processes = cfg.get("max_parallel") or plan["processes"]
        batch = cfg.get("batch_size") or plan["batch"]

        # Group by token bucket: a batch of one shape compiles once and reuses it.
        groups: dict = {}
        for item in prepared:
            groups.setdefault(item["bucket"], []).append(item)
        info(f"{predictor}: {len(prepared)} fold(s) in {len(groups)} shape group(s), "
             f"{processes} process(es) x {batch} input(s) each")

        for bucket, items in sorted(groups.items()):
            chunks = [items[i:i + batch] for i in range(0, len(items), batch)] \
                if key in DIRECTORY_CAPABLE else [[i] for i in items]

            # Real concurrency: launch up to `processes` at once and reap as they
            # finish. Running them one after another would make the measured
            # per-predictor process counts meaningless -- IntelliFold's optimum
            # of four is most of why it is affordable at all.
            queue = list(enumerate(chunks))
            running = []
            while queue or running:
                while queue and len(running) < processes:
                    index, chunk = queue.pop(0)
                    tag = f"{predictor}_b{bucket}_c{index}"
                    out_dir = output / predictor / f"bucket_{bucket}" / f"chunk_{index}"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    log_path = output / "logs" / f"{tag}.log"
                    marker = out_dir / "chunk_complete.json"
                    names = [member["name"] for member in chunk]
                    if completed_chunk(marker, names, out_dir):
                        for member in chunk:
                            results.append({"job": member["name"], "predictor": predictor,
                                            "bucket": bucket, "exit_code": 0,
                                            "output": str(out_dir)})
                        done_units += len(chunk)
                        info(f"{tag}: reused {len(chunk)} completed fold(s)")
                        stage("fold", 35 + int(60 * done_units / max(1, total_units)),
                              f"{done_units} of {total_units} folds done")
                        continue
                    if key in DIRECTORY_CAPABLE:
                        proc, handle = run_directory_batch(key, [c["yaml"] for c in chunk],
                                                           out_dir, root, env, cfg, log_path)
                    else:
                        proc, handle = run_single(predictor, chunk[0]["yaml"], out_dir,
                                                  root, env, log_path, cfg)
                    running.append((proc, handle, chunk, tag, out_dir, marker))

                time.sleep(1.0)
                still = []
                for proc, handle, chunk, tag, out_dir, marker in running:
                    if proc.poll() is None:
                        still.append((proc, handle, chunk, tag, out_dir, marker))
                        continue
                    handle.close()
                    code = proc.returncode
                    missing = [member["name"] for member in chunk
                               if not has_structure_for_job(out_dir, member["name"])]
                    if code == 0 and missing:
                        code = 1
                        info(f"{tag} returned success but produced no structure for: {', '.join(missing)}")
                    if code == 0:
                        marker.write_text(json.dumps({
                            "predictor": predictor,
                            "jobs": [member["name"] for member in chunk],
                        }, indent=2) + "\n")
                    for member in chunk:
                        results.append({"job": member["name"], "predictor": predictor,
                                        "bucket": bucket, "exit_code": code,
                                        "output": str(out_dir)})
                    done_units += len(chunk)
                    if code:
                        info(f"{tag} failed (exit {code}) — see logs/{tag}.log")
                    stage("fold", 35 + int(60 * done_units / max(1, total_units)),
                          f"{done_units} of {total_units} folds done")
                running = still

    stage("collect", 96, "Collecting results")
    with (output / "predictions.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["job", "predictor", "bucket", "exit_code", "output"])
        writer.writeheader()
        writer.writerows(results)

    failures = sum(1 for r in results if r["exit_code"])
    summary = {"jobs": len(prepared), "predictors": predictors, "results": len(results),
               "failures": failures, "wall_sec": round(time.time() - started, 1),
               "seed": int(cfg.get("seed", 42)),
               "num_seeds": int(cfg.get("num_seeds", 1)),
               "diffusion_samples": int(cfg.get("diffusion_samples", 0)),
               "msa_cache": cfg["msa"]["cache_dir"]}
    (output / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    info(json.dumps(summary))
    succeeded = len(results) - failures
    print(f"PBSTAGE|done|100|{succeeded} of {len(results)} folds succeeded", flush=True)
    if failures:
        die(f"{failures} of {len(results)} folds failed. See predictions.csv and logs/ for details.")
    print("PBDONE|ok", flush=True)


if __name__ == "__main__":
    main()
