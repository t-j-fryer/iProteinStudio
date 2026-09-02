#!/usr/bin/env python3
"""Isolated one-sample GPU smoke test for Studio's two structure-guided RFD3 modes.

The disposable adapter root copies app-owned scripts but symlinks the installed
MLX port, checkpoint and weights read-only. It never edits ~/.iproteinstudio.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OVERLAY = ROOT / "Sources/iProteinStudio/Resources/rfd3_overlay"
PREPARE = ROOT / "Sources/iProteinStudio/Resources/rfd3/prepare_campaign.py"
STRUCTURE = ROOT / "Sources/iProteinStudio/Resources/examples/p53_mdm2/1YCR.pdb"
MDM2 = "ETLVRPKPLLLKLLKSVGAQKDTYTMKEVLFYLGQYIMTKRLYDEKQQHIVYCSNDLLGDLFGVPSFSVKEHRKIYTMIYRNLVV"


def run(command: list[str], log: Path, cwd: Path | None = None) -> float:
    started = time.monotonic()
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    elapsed = time.monotonic() - started
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(result.stdout + result.stderr)
    if result.returncode:
        raise SystemExit(f"command failed ({result.returncode}); see {log}")
    return elapsed


def stage_runtime(destination: Path, installed: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(OVERLAY / "scripts", destination / "scripts", dirs_exist_ok=True)
    mlx_destination = destination / "mlx_port"
    if mlx_destination.is_symlink():
        mlx_destination.unlink()
    shutil.copytree(installed / "mlx_port", mlx_destination, dirs_exist_ok=True)
    shutil.copytree(OVERLAY / "mlx_port", mlx_destination, dirs_exist_ok=True)
    shutil.copy2(installed / "milestone0_oracle.py", destination / "milestone0_oracle.py")
    for name in ("weights", "checkpoints", "assets"):
        link = destination / name
        if not link.exists():
            link.symlink_to(installed / name, target_is_directory=True)
    (destination / "oracle").mkdir(exist_ok=True)


def request(mode: str, campaign: Path, runtime: Path, steps: int, recycles: int) -> dict:
    value = {
        "campaign_dir": str(campaign), "rfd3_root": str(runtime),
        "nanohunter_root": str(ROOT), "design_name": f"p53_mdm2_{mode}",
        "design_mode": mode, "target_kind": "protein",
        "target_structure": str(STRUCTURE), "target_chain": "A", "target_chains": ["A"],
        "target_sequence": MDM2, "source_binder_chain": "B", "lengths": [70],
        "num_backbones": 1, "batch_size": 1, "queues_per_bin": 1,
        "timesteps": steps, "recycles": recycles, "precision": "bf16", "seed_base": 17,
        "sequences_per_backbone": 1, "top_n": 1, "sequence_model": "solublempnn",
        "extra_predictors": ["boltz"], "run_apo": True, "hit_filters": {},
    }
    if mode == "partialDiffusion":
        value.update(partial_t=1.0, preserve_partial_sequence=True, motif_sites={})
    else:
        value["motif_sites"] = {"B19": "CG,CE1,CZ", "B23": "CG,NE1,CH2", "B26": "CG,CD1,CD2"}
    return value


def load_validation_scorer():
    path = ROOT / "Sources/iProteinStudio/Resources/rfd3_overlay/scripts/score_binder_validation.py"
    spec = importlib.util.spec_from_file_location("rfd3_smoke_scorer", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installed-rfd3", type=Path,
                        default=Path.home() / ".iproteinstudio/rfd3")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--recycles", type=int, default=2)
    parser.add_argument("--mode", choices=["all", "partial", "motif"], default="all")
    args = parser.parse_args()
    output, installed = args.output.resolve(), args.installed_rfd3.resolve()
    runtime = output / "disposable_runtime"
    stage_runtime(runtime, installed)

    summaries = []
    modes = {"all": ("partialDiffusion", "motifScaffolding"),
             "partial": ("partialDiffusion",), "motif": ("motifScaffolding",)}[args.mode]
    scorer = load_validation_scorer()
    for mode in modes:
        campaign = output / mode
        payload = output / f"{mode}.json"
        payload.parent.mkdir(parents=True, exist_ok=True)
        payload.write_text(json.dumps(request(mode, campaign, runtime, args.steps, args.recycles), indent=2) + "\n")
        prepare_seconds = run([sys.executable, str(PREPARE), str(payload)],
                              output / "logs" / f"{mode}_prepare.log")
        config = json.loads((campaign / "config/campaign.json").read_text())
        command = [sys.executable, str(runtime / "scripts/design_from_yaml.py"), config["design_yaml"],
                   "--name", config["design_name"], "--output", str(campaign), "--num-designs", "1",
                   "--lengths", "70", "--batch-size", "1", "--queues-per-bin", "1",
                   "--precision", "bf16", "--timesteps", str(args.steps), "--n-recycle", str(args.recycles),
                   "--seed-base", "17", "--stage", "all"]
        gpu_seconds = run(command, output / "logs" / f"{mode}_gpu.log", runtime)
        results = sorted((campaign / "rfd3").glob("**/results/design_*.json"))
        backbones = sorted((campaign / "rfd3/backbones").glob("design_*.pdb"))
        if len(results) != 1 or len(backbones) != 1:
            raise SystemExit(f"{mode}: expected exactly one checkpoint and backbone")
        metrics = json.loads(results[0].read_text())
        analysis = {}
        if mode == "partialDiffusion":
            normalized = campaign / "assets/target/normalized_target.pdb"
            analysis["input_output_binder_ca_rmsd"] = scorer.rmsd(
                str(backbones[0]), str(normalized), chain="A")
        if mode == "motifScaffolding":
            if set(metrics.get("diffused_index_map", {})) != {"A19", "A23", "A26"}:
                raise SystemExit("motif residue correspondence is incomplete")
            if not metrics.get("motif_fixed_atoms"):
                raise SystemExit("motif atom provenance is missing")
            analysis["mapped_source_residues"] = metrics["diffused_index_map"]
            analysis["requested_fixed_atoms"] = metrics["motif_fixed_atoms"]
            normalized = campaign / "assets/target/normalized_target.pdb"
            moving, reference, owners = [], [], []
            for source_residue, designed_residue in metrics["diffused_index_map"].items():
                names = metrics["motif_fixed_atoms"][source_residue]
                source_atoms = scorer.selected_atom_map(str(normalized), source_residue, names)
                designed_atoms = scorer.selected_atom_map(str(backbones[0]), designed_residue, names)
                common = sorted(set(source_atoms) & set(designed_atoms))
                if set(common) != set(names):
                    raise SystemExit(f"{source_residue}: requested motif atoms are absent from output")
                for name in common:
                    moving.append(designed_atoms[name]); reference.append(source_atoms[name])
                    owners.append(source_residue)
            import numpy as np
            moving_array, reference_array = np.asarray(moving), np.asarray(reference)
            rotation, translation = scorer.kabsch_transform(moving_array, reference_array)
            aligned = (rotation @ moving_array.T).T + translation
            squared = ((aligned - reference_array) ** 2).sum(1)
            fixed_atom_rmsds = {
                residue: float(np.sqrt(np.mean([value for value, owner in zip(squared, owners)
                                                if owner == residue])))
                for residue in sorted(set(owners))
            }
            aligned_rmsd = float(np.sqrt(np.mean(squared)))
            if aligned_rmsd > 0.01:
                raise SystemExit("aligned fixed motif atoms drifted from their source geometry")
            analysis["source_to_design_aligned_fixed_atom_rmsd"] = aligned_rmsd
            analysis["source_to_design_aligned_rmsd_by_residue"] = fixed_atom_rmsds
        summaries.append({"mode": mode, "steps": args.steps, "recycles": args.recycles,
                          "prepare_seconds": prepare_seconds,
                          "gpu_stage_seconds": gpu_seconds, "backbone": str(backbones[0]),
                          "metrics": metrics, "analysis": analysis})

    (output / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
