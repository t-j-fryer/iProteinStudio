"""Shared runtime primitives for iProteinStudio's RFdiffusion3 campaign.

These functions are the generic, validated pieces formerly imported from
NanoHunter's experimental ``nise_lib``: process launching, Boltz input/output,
the published ranking expression, and Kabsch/PDB helpers. Keeping them here
makes the shipped RFdiffusion3 workflow self-contained without bringing NISE's
selection/expansion campaign into iProteinStudio.
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np


_configured_root: Path | None = None


def configure(root: Path | str) -> None:
    global _configured_root
    _configured_root = Path(root).resolve()
    os.environ.setdefault("BOLTZ_CACHE", str(_configured_root / "models" / "boltz2"))
    os.environ.setdefault("NUMBA_CACHE_DIR", str(_configured_root / "numba_cache"))
    Path(os.environ["NUMBA_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)


def pipeline_root() -> Path:
    if _configured_root is not None:
        return _configured_root
    configured = os.environ.get("NANOHUNTER_ROOT") or os.environ.get("IPROTEIN_ROOT")
    if configured:
        return Path(configured).resolve()
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "venvs").is_dir():
        return candidate
    raise RuntimeError("Cannot locate the pipeline root; pass --nanohunter-root.")


def run(cmd, cwd=None, env=None, log_path=None, check=True):
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    proc = subprocess.run(
        [str(item) for item in cmd], cwd=str(cwd) if cwd else None,
        env=merged_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if log_path is not None:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("$ " + " ".join(str(item) for item in cmd) + "\n" + (proc.stdout or ""))
    if check and proc.returncode:
        tail = "\n".join((proc.stdout or "").splitlines()[-40:])
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(map(str, cmd))}\n{tail}")
    return proc


def _run_parallel(cmds_and_logs):
    """Launch (command, log) pairs concurrently; fail if any child fails."""
    processes = []
    for command, log_path in cmds_and_logs:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("w")
        handle.write("$ " + " ".join(str(item) for item in command) + "\n")
        handle.flush()
        process = subprocess.Popen(
            [str(item) for item in command], stdout=handle, stderr=subprocess.STDOUT,
            env=dict(os.environ))
        processes.append((process, handle, command, path))
    failures = []
    for process, handle, command, path in processes:
        returncode = process.wait()
        handle.close()
        if returncode:
            tail = "\n".join(path.read_text(errors="replace").splitlines()[-30:])
            failures.append(f"rc={returncode}: {' '.join(map(str, command))}\n{tail}")
    if failures:
        raise RuntimeError("Boltz shard(s) failed:\n" + "\n---\n".join(failures))


def _iter_pdb_atoms(pdb_path):
    for line in Path(pdb_path).read_text().splitlines():
        if line.startswith(("ATOM", "HETATM")):
            yield line


def ca_coords_chain(pdb_path, chain):
    coords = []
    for line in _iter_pdb_atoms(pdb_path):
        if line[21] == chain and line[12:16].strip() == "CA":
            coords.append([float(line[30:38]), float(line[38:46]), float(line[46:54])])
    return np.array(coords, dtype=float)


def _kabsch(points, reference):
    """Return RMSD and the rotation/centres mapping points to reference."""
    points_centered = points - points.mean(0)
    reference_centered = reference - reference.mean(0)
    covariance = points_centered.T @ reference_centered
    left, _, right_transpose = np.linalg.svd(covariance)
    handedness = np.sign(np.linalg.det(right_transpose.T @ left.T))
    correction = np.diag([1.0, 1.0, handedness])
    rotation = right_transpose.T @ correction @ left.T
    aligned = (rotation @ points_centered.T).T
    rmsd = float(np.sqrt(((aligned - reference_centered) ** 2).sum(1).mean()))
    return rmsd, rotation, points.mean(0), reference.mean(0)


def _ligand_bfactors(pdb_path, chain):
    values = []
    for line in _iter_pdb_atoms(pdb_path):
        if line[21] == chain:
            try:
                values.append(float(line[60:66]))
            except ValueError:
                pass
    return np.array(values, dtype=float)


def write_boltz_yaml(path, sequence, smiles, affinity=True, binder_chain="B", pocket=None):
    """Write the exact protein-A/ligand-B YAML shape used by NanoHunter."""
    lines = [
        "sequences:", "  - protein:", "      id: A",
        f"      sequence: {sequence}", "      msa: empty",
        "  - ligand:", "      id: B", f"      smiles: '{smiles}'",
    ]
    if pocket:
        contacts = pocket.get("contacts")
        if contacts is None and pocket.get("n_center_contacts"):
            length = len(sequence)
            count = max(1, int(pocket["n_center_contacts"]))
            low, high = max(1, length // 4), max(1, (3 * length) // 4)
            indices = ([max(1, length // 2)] if count == 1 else sorted({
                int(round(low + (high - low) * index / (count - 1)))
                for index in range(count)}))
            contacts = [["A", residue] for residue in indices]
        contacts_text = ", ".join(f"[{item[0]}, {item[1]}]" for item in contacts)
        lines += [
            "constraints:", "  - pocket:", f"      binder: {pocket.get('binder', 'B')}",
            f"      contacts: [{contacts_text}]",
            f"      max_distance: {pocket.get('max_distance', 6.0)}",
            f"      force: {str(pocket.get('force', True)).lower()}",
        ]
    if affinity:
        lines += ["properties:", "  - affinity:", f"      binder: {binder_chain}"]
    lines += ["version: 1", ""]
    Path(path).write_text("\n".join(lines))
    return path


@dataclass
class Prediction:
    name: str
    pdb: str
    complex_plddt: float = float("nan")
    iptm: float = float("nan")
    ligand_iptm: float = float("nan")
    ligand_plddt: float = float("nan")
    pbind: Optional[float] = None


def parse_prediction(out_dir, stem):
    matches = glob.glob(os.path.join(out_dir, "**", "predictions", stem), recursive=True)
    if not matches:
        return None
    pdbs = glob.glob(os.path.join(matches[0], f"{stem}_model_0.pdb"))
    if not pdbs:
        return None
    prediction = Prediction(name=stem, pdb=pdbs[0])
    confidence = os.path.join(matches[0], f"confidence_{stem}_model_0.json")
    if os.path.exists(confidence):
        with open(confidence) as handle:
            data = json.load(handle)
        prediction.complex_plddt = float(data.get("complex_plddt", float("nan")))
        prediction.iptm = float(data.get("iptm", float("nan")))
        prediction.ligand_iptm = float(data.get("ligand_iptm", float("nan")))
    affinity = os.path.join(matches[0], f"affinity_{stem}.json")
    if os.path.exists(affinity):
        with open(affinity) as handle:
            data = json.load(handle)
        if "affinity_probability_binary" in data:
            prediction.pbind = float(data["affinity_probability_binary"])
    b_factors = _ligand_bfactors(prediction.pdb, "B")
    if len(b_factors):
        prediction.ligand_plddt = float(b_factors.mean())
    return prediction


def _boltz_cmd(yaml_dir, out_dir, recycling, sampling_steps, extra, use_potentials=False):
    command = [
        pipeline_root() / "venvs" / "NanoHunter_boltz" / "bin" / "boltz",
        "predict", yaml_dir, "--out_dir", out_dir, "--output_format", "pdb",
        "--num_workers", "0", "--override",
    ]
    if use_potentials:
        command += ["--use_potentials"]
    if recycling is not None:
        command += ["--recycling_steps", str(recycling)]
    if sampling_steps is not None:
        command += ["--sampling_steps", str(sampling_steps)]
    if extra:
        command += list(extra)
    return command


def rank_score(prediction: Prediction, mode="auto"):
    ligand = (prediction.ligand_plddt / 100.0
              if prediction.ligand_plddt == prediction.ligand_plddt else 0.0)
    if mode == "ligand_plddt":
        return ligand
    if mode in ("ligand_plddt+pbind", "auto"):
        return ligand + prediction.pbind if prediction.pbind is not None else ligand
    raise ValueError(f"Unknown rank metric mode: {mode}")
