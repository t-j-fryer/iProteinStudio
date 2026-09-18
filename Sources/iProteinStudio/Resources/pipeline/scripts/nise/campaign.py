#!/usr/bin/env python3
"""Studio's managed entry point for the pinned ligand-NISE search."""
import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

from contract import preflight, saved_request
from runtime import Backend, atomic, digest


def run(config_path, branch_test=False, stage_batches=False):
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text())
    if ("branch_test" in config) != branch_test:
        raise ValueError("A branch-test configuration requires the explicit branch-test entry point")
    root = Path(os.environ["NANOHUNTER_ROOT"]).resolve()
    output = config_path.parent
    if Path(config["output"]).resolve() != output:
        raise ValueError("NISE output does not match its saved configuration")
    settings = preflight(root, saved_request(config["request"]))
    from ligand_atoms import resolve, validate_selection
    manifest = resolve(settings["smiles"])
    validate_selection(settings, manifest)
    # Boltz affinity defines the chemical state. All later engines receive it
    # explicitly; no engine's atom indices are copied into NESSO input.
    smiles = manifest["smiles_used"]
    print("NISE ligand chemical state (Boltz affinity, RFdiffusion3, NESSO): " + smiles, flush=True)
    map_path = output / "ligand_atom_map.json"
    if map_path.exists() and json.loads(map_path.read_text()) != manifest:
        raise ValueError("The saved ligand atom map changed; start a new campaign.")
    if not map_path.exists():
        atomic(map_path, manifest)
    scripts = Path(__file__).resolve().parent.parent
    if stage_batches:
        from batch_runtime import BatchBackend
        backend = BatchBackend(root, output, settings, scripts)
    else:
        backend = Backend(root, output, settings, scripts)
    backend.ligand_manifest = manifest
    request_hash = digest(config_path)
    fingerprint = output / "request.sha256"
    if fingerprint.exists() and fingerprint.read_text().strip() != request_hash:
        raise ValueError("NISE request changed after the campaign was created")
    if not fingerprint.exists():
        fingerprint.write_text(request_hash + "\n")
    template = output / "ligand.yaml"
    import nise_lib
    import nise_run
    # Only the ligand block is consumed by the upstream search.
    content = "version: 1\nsequences:\n  - ligand:\n      id: B\n      smiles: " + json.dumps(smiles) + "\n"
    if template.exists() and template.read_text() != content:
        raise ValueError("Saved ligand template changed")
    if not template.exists():
        template.write_text(content)
    # Explicit protocol parameters protect campaigns from future CLI defaults.
    arguments = ["--template-yaml", str(template), "--out-dir", str(output),
                 "--backbone-method", settings["backbone_method"],
                 "--designer", "lasermpnn", "--device", "cpu", "--rank-metric", "ligand_plddt+pbind",
                 
                 "--phase0-temp", "0.5", "--phase0-sc-ca", str(settings["phase0_sc_ca"]), "--phase0-sc-lig", "2.0",
                 "--nise-sc-ca", str(settings["nise_sc_ca"]), "--nise-sc-lig", str(settings["nise_sc_lig"]),
                 "--nise-ligand-sc-from-cycle", str(settings["nise_ligand_sc_from_cycle"]), "--seq-temp", "0.5", "--bindingsite-temp", "0.7",
                 "--fs-distance", "10.0", "--ala-budget", "2", "--gly-budget", "0",
                 "--binder-percent-x", "50", "--min-improvement", str(settings["min_improvement"]), "--boltz-parallel", "1",
                 "--phase0-pocket-distance", str(settings["hotspot_distance"]), "--phase0-pocket-contacts", "5"]
    for key in ("num_starts", "trajectories", "nise_seqs", "first_cycle_seqs", "noise_radius", "noise_percent", "noise_predictions", "noise_mpnn_seqs", "noise_advance", "max_cycles", "patience",
                "binder_min_len", "binder_max_len", "seed", "phase0_refine_cycles", "phase0_seqs1", "phase0_seqs2", "phase0_gate_seqs", "beam", "early_score_gate", "initial_proposals", "affinity_batch_size"):
        arguments += ["--" + key.replace("_", "-"), str(settings[key])]
    for key in ("selective_affinity", "adaptive_proposals", "partial_noising"):
        if settings[key]:
            arguments.append("--" + key.replace("_", "-"))
    try:
        if branch_test:
            from branch_test import run as test_branch
            test_branch(arguments, backend, config["branch_test"])
            return
        atomic(output / "progress.json", dict(message="Searching for ligand-binding structures", scheduler=settings["scheduler"]))
        nise_run.main(arguments, backend=backend)
        if settings["preorganisation"]:
            atomic(output / "progress.json", dict(message="Measuring apo/holo pocket preorganisation"))
            backend.preorganisation(SimpleNamespace(seed=settings["seed"], use_potentials=False))
        summary = json.loads((output / "search_summary.json").read_text())
        atomic(output / "summary.json", {**summary, "status": "completed", "scheduler": settings["scheduler"],
               "preorganisation": settings["preorganisation"], "request_sha256": request_hash,
               "nesso_screen": settings["nesso_screen"], "nesso_top_k": settings["nesso_top_k"], "beam": settings["beam"],
               "backbone_method": settings["backbone_method"],
               "initial_screening": {key: settings[key] for key in
                    ("phase0_nesso_screen", "phase0_nesso_refine_top_k", "phase0_nesso_expand_top_k")},
               "sequence_replay": "Recorded LASErMPNN sequences; upstream sampler has no seed control"})
        atomic(output / "progress.json", dict(message="Completed", status="completed"))
    finally:
        try:
            backend.write_atom_report()
        finally:
            backend.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--resume", action="store_true", help="Audited operations are always resumed")
    parser.add_argument("--branch-test", action="store_true", help="Validate only the partial-noising branch from a recorded parent")
    parser.add_argument("--stage-batches", action="store_true", help="Submit stage inputs together with per-input durable checkpoints")
    args = parser.parse_args()
    run(args.config, branch_test=args.branch_test, stage_batches=args.stage_batches)
