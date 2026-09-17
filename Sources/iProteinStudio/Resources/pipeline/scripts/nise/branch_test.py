"""Bounded integration validation using an explicitly imported historical parent.

This is not a campaign resume or an alternative seed-selection policy. The
private desktop planner fingerprints every input and executes the ordinary
partial_noising.run_branch under the same broker and resident Backend.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import re


def validate(output, settings, descriptor):
    """Dependency-free preflight, also repeated immediately before inference."""
    output = Path(output).resolve()
    if not isinstance(descriptor, dict) or set(descriptor) != {"schema", "cycle", "files", "source_run", "source_candidate"}:
        raise ValueError("Incomplete branch-test descriptor")
    if descriptor["schema"] != 1 or type(descriptor["cycle"]) is not int or descriptor["cycle"] < 2:
        raise ValueError("Branch tests require schema 1 and an optimization cycle >= 2")
    if (not settings["partial_noising"] or settings["adaptive_proposals"]
            or settings["scheduler"] != "resident" or settings["trajectories"] != 1
            or settings["nesso_screen"] or settings["phase0_nesso_screen"] or settings["preorganisation"]
            or not settings["selective_affinity"]):
        raise ValueError("Branch validation requires one resident, fixed-sampling Boltz trajectory with selective affinity")
    if settings["noise_predictions"] + settings["noise_mpnn_seqs"] > 64:
        raise ValueError("A branch test is bounded to at most 64 structure predictions")
    files = descriptor["files"]
    expected = {"parent.json", "parent.pdb", "reference.pdb", "ligand_atom_map.json"}
    if not isinstance(files, dict) or set(files) != expected:
        raise ValueError("Branch tests require the parent record, structure, reference and ligand map")
    paths = []
    for name, checksum in files.items():
        path = (output / "branch_test_inputs" / name).resolve()
        if output not in path.parents or not path.is_file():
            raise ValueError("Branch-test inputs must be copied inside the new run")
        if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise ValueError("Branch-test input changed: " + name)
        paths.append(path)
    parent = json.loads((output / "branch_test_inputs/parent.json").read_text())
    if (parent.get("name") != descriptor["source_candidate"] or parent.get("passed") is not True
            or not re.fullmatch("[ACDEFGHIKLMNPQRSTVWY]+", parent.get("sequence", ""))):
        raise ValueError("Choose a complete, previously passing parent candidate")
    for key in ("ligand_plddt", "pbind", "score", "ca_rmsd", "ligand_rmsd"):
        if not isinstance(parent.get(key), (int, float)) or not math.isfinite(parent[key]):
            raise ValueError("Missing finite parent metric: " + key)
    if not (0 <= parent["pbind"] <= 1 and 0 <= parent["ligand_plddt"] <= 100
            and math.isclose(parent["score"], parent["pbind"] + parent["ligand_plddt"] / 100, abs_tol=1e-8)):
        raise ValueError("Parent score does not match the Boltz objective")
    return paths


def run(arguments, backend, descriptor):
    import nise_run as search
    from partial_noising import run_branch
    from runtime import atomic
    from types import SimpleNamespace
    validate(backend.output, backend.settings, descriptor)
    args = search.parse_arguments(arguments, backend)
    out = backend.output
    inputs = out / "branch_test_inputs"
    old = json.loads((inputs / "parent.json").read_text())
    old_map = json.loads((inputs / "ligand_atom_map.json").read_text())
    current_map = backend.atom_manifest()
    if any(old_map.get(key) != current_map.get(key) for key in ("signature", "smiles_used")):
        raise ValueError("Imported parent's ligand chemical state or atom map does not match")
    pdb, reference = inputs / "parent.pdb", inputs / "reference.pdb"
    backend.audit_structure(pdb, old["sequence"], True)
    # Recompute strict parent checks, independent of historical selection flags.
    sc = search.L.self_consistency(str(pdb), str(reference), ca_thresh=args.nise_sc_ca, lig_thresh=args.nise_sc_lig)
    atom_pass = backend.check_atom_requirements(SimpleNamespace(name="imported_parent", pdb=str(pdb)))
    atomic(out / "parent_audit.json", dict(source=descriptor, ca_rmsd=sc.ca_rmsd,
        ligand_rmsd=sc.ligand_rmsd, self_consistency_passed=sc.ok,
        atom_checks=backend.atom_checks.get("imported_parent"), atom_checks_passed=atom_pass))
    if not sc.ok or not atom_pass:
        raise ValueError("Imported parent fails recomputed geometry checks")
    parent = search.Node(name=old["name"], sequence=old["sequence"], pdb=str(pdb), ref_pdb=str(reference),
        ca_rmsd=sc.ca_rmsd, ligand_rmsd=sc.ligand_rmsd, ligand_plddt=old["ligand_plddt"],
        pbind=old["pbind"], score=old["score"], cycle=old["cycle"], traj=0, origin=descriptor["source_candidate"])
    backend.freeze_config({**{k: v for k, v in vars(args).items() if k != "backend"}, "branch_test": descriptor})
    cycle = descriptor["cycle"]
    ligand_threshold = args.nise_sc_lig if cycle >= args.nise_ligand_sc_from_cycle else float("inf")
    atomic(out / "progress.json", dict(message="Testing partial noising from imported parent", mode="branch_test"))
    with (out / "trajectory.csv.part").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["phase", "cycle", "trajectory", "origin", "name", "ca_rmsd", "ligand_rmsd",
                         "ligand_plddt", "pbind", "score", "passed", "sequence"])
        result = run_branch([dict(tid=0, current=[parent])], out, current_map["smiles_used"], args,
                            cycle, ligand_threshold, writer)
    (out / "trajectory.csv.part").replace(out / "trajectory.csv")
    selection = json.loads((out / f"cycle{cycle:02d}/partial_noising/selection.json").read_text())
    summary = dict(status="completed", mode="branch_test", source_candidate=parent.name,
        branch_status=selection["trajectories"]["0"]["status"],
        selected=[n.name for n in result.get(0, [])[:args.noise_advance]],
        acceptance_passed=bool(selection["trajectories"]["0"]["advanced"]),
        maximum_structure_predictions=args.noise_predictions + args.noise_mpnn_seqs,
        interpretation="Integration test only; no ordinary beam, initial generation or binding-efficacy comparison")
    atomic(out / "summary.json", summary)
    atomic(out / "progress.json", dict(message="Branch test completed: " + summary["branch_status"], status="completed"))
