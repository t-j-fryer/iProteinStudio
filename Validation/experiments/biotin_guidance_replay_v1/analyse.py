"""Independently audit replay outputs and compare time and geometry diagnostics."""
import argparse
import csv
import json
import re
import pickle
from pathlib import Path
import statistics
import sys


def read(path):
    return json.loads(path.read_text())


def geometry(path, settings, manifest, reference_molecule=None):
    import gemmi
    import numpy as np
    from rdkit import Chem
    from rdkit.Chem import rdDistGeom
    from atom_geometry import measure
    from validate_prediction_geometry import inspect_geometry
    model = gemmi.read_structure(str(path))[0]
    atoms = [(c.name, j, a.name.strip(), a.element.atomic_number,
              np.array([a.pos.x, a.pos.y, a.pos.z]), float(a.b_iso))
             for c in model for j, r in enumerate(c) for a in r
             if a.element.name not in ("H", "D")]
    protein = [a for a in atoms if a[0] == "A"]
    ligand = [a for a in atoms if a[0] == "B"]
    radii = Chem.GetPeriodicTable()
    pxyz, lxyz = np.array([a[4] for a in protein]), np.array([a[4] for a in ligand])
    pr = np.array([radii.GetRvdw(a[3]) for a in protein])
    lr = np.array([radii.GetRvdw(a[3]) for a in ligand])
    pd = np.linalg.norm(pxyz[:, None] - pxyz[None, :], axis=-1)
    pl = np.linalg.norm(pxyz[:, None] - lxyz[None, :], axis=-1)
    indices = np.array([a[1] for a in protein])
    nonlocal_pairs = np.triu(abs(indices[:, None] - indices[None, :]) > 1, 1)
    # Deliberately conservative severe-overlap diagnostics, not a calibrated clashscore.
    pp_overlap = pr[:, None] + pr[None, :] - pd
    pl_overlap = pr[:, None] + lr[None, :] - pl
    atom_checks = measure(path, settings, manifest)
    continuity = inspect_geometry(path)
    if continuity["errors"]:
        raise ValueError(continuity["errors"])
    mol = Chem.MolFromSmiles(manifest["smiles_used"])
    by_name = {a[2]: a[4] for a in ligand}
    coords = np.array([by_name[a["name"]] for a in manifest["atoms"]])
    if len(coords) != mol.GetNumAtoms():
        raise ValueError("Ligand graph does not match the atom manifest")
    bounds = rdDistGeom.GetMoleculeBoundsMatrix(mol)
    bonds = []
    for bond in mol.GetBonds():
        i, j = sorted((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()))
        d = float(np.linalg.norm(coords[i] - coords[j]))
        bonds.append(dict(atoms=[manifest["atoms"][k]["name"] for k in (i, j)],
                          distance=d, lower=float(bounds[j, i]), upper=float(bounds[i, j]),
                          violation=bool(d < bounds[j, i] - .15 or d > bounds[i, j] + .15)))
    Chem.AssignStereochemistry(mol, force=True, cleanIt=True)
    expected = {a.GetIdx(): a.GetProp("_CIPCode") for a in mol.GetAtoms() if a.HasProp("_CIPCode")}
    probe = Chem.Mol(mol)
    conformer = Chem.Conformer(len(coords))
    for i, xyz in enumerate(coords):
        conformer.SetAtomPosition(i, xyz)
    probe.RemoveAllConformers(); probe.AddConformer(conformer)
    Chem.RemoveStereochemistry(probe)
    Chem.AssignStereochemistryFrom3D(probe, replaceExistingTags=True)
    observed = {a.GetIdx(): a.GetProp("_CIPCode") for a in probe.GetAtoms() if a.HasProp("_CIPCode")}
    chiral_errors = [manifest["atoms"][i]["name"] for i, tag in expected.items() if observed.get(i) != tag]
    volume_checks = []
    if reference_molecule is not None:
        # Independent of CIP assignment: compare signed tetrahedral volumes to
        # the actual, correctly chiral frozen input conformer using named atoms.
        reference_by_name = {a.GetProp("name"): np.array(reference_molecule.GetConformer().GetAtomPosition(a.GetIdx()))
                             for a in reference_molecule.GetAtoms() if a.GetAtomicNum() > 1}
        for index in expected:
            center = manifest["atoms"][index]["name"]
            neighbors = sorted(a.GetIdx() for a in mol.GetAtomWithIdx(index).GetNeighbors())
            if len(neighbors) != 3:
                raise ValueError("Independent volume check currently supports tetrahedral CH stereocentres")
            names = [manifest["atoms"][j]["name"] for j in neighbors]
            ref = float(np.linalg.det([reference_by_name[n] - reference_by_name[center] for n in names]))
            pred = float(np.linalg.det([by_name[n] - by_name[center] for n in names]))
            if abs(ref) < .1:
                raise ValueError("Frozen chiral reference is nearly planar")
            volume_checks.append(dict(atom=center, reference_determinant_a3=ref, predicted_determinant_a3=pred,
                                      opposite_sign=bool(ref * pred < 0), near_planar=abs(pred) < .1))
        reversed_names = {v["atom"] for v in volume_checks if v["opposite_sign"]}
        if reversed_names != set(chiral_errors):
            raise ValueError("Independent volume and CIP chirality checks disagree")
    residues = list(model.find_chain("A"))
    return dict(
        atom_checks=atom_checks, continuity=continuity, ligand_bonds=bonds,
        chiral_errors=chiral_errors, independent_chiral_volume_checks=volume_checks,
        metrics=dict(
            atom_checks_passed=atom_checks["passed"],
            hotspots_passed=all(d <= settings["hotspot_distance"] for d in atom_checks["hotspot_distance_a"].values()),
            exposed_passed=all(r["retained_fraction"] >= settings["exposure_min_fraction"] for r in atom_checks["exposure"].values()),
            min_terminal_exposure=min(r["retained_fraction"] for r in atom_checks["exposure"].values()),
            max_hotspot_distance=max(atom_checks["hotspot_distance_a"].values()),
            continuity_violations=len(continuity["violations"]),
            severe_protein_ligand_overlaps=int((pl_overlap > 1).sum()),
            severe_nonlocal_protein_overlaps=int(((pp_overlap > 1) & nonlocal_pairs).sum()),
            minimum_protein_ligand_distance=float(pl.min()),
            ligand_bond_violations=sum(b["violation"] for b in bonds),
            ligand_chiral_errors=len(chiral_errors),
            ligand_plddt=statistics.mean(a[5] for a in ligand),
            protein_residues=len(residues), unknown_residues=sum(r.name == "UNK" for r in residues)))


def analyse(output):
    scripts = output / ".studio_runtime/pipeline/scripts"
    sys.path[:0] = [str(scripts), str(scripts / "nise")]
    from runtime import Journal, Backend
    from nise_lib import self_consistency
    from boltz_replay_validation import validate, checksum
    import gemmi
    import numpy as np
    config = read(output / "replay_config.json")
    validate(output, config)
    ids = config["ids"]
    settings = read(output / "inputs/nise_config.json")["request"]
    manifest = read(output / "inputs/ligand_atom_map.json")
    journal = Journal(output)
    timings = {arm: [] for arm in ("original", "singleton", "batch")}
    raw_rows, rows, pairing = [], [], []
    for name in ids:
        old = read(output / "inputs" / name / "completed.json")
        timings["original"].append(old["result"]["timing"])
        receipt_path = output / "singleton" / name / "completed.json"
        receipt = read(receipt_path)
        timings["singleton"].append(journal.load(receipt_path, receipt["input"]))
        structures = {}
        # Locally generated, fingerprinted Boltz preprocessing cache; not an
        # arbitrary uploaded pickle. Exactly one small-molecule component.
        molecules = pickle.loads((output / "inputs" / name / "processed/mols" / f"{name}.pkl").read_bytes())
        if len(molecules) != 1:
            raise ValueError("Expected one frozen ligand molecule")
        reference_molecule = next(iter(molecules.values()))
        for arm in timings:
            if arm == "original":
                path = output / "inputs" / name / f"{name}_model_0.pdb"
            else:
                unit = name if arm == "singleton" else "all"
                path = output / arm / unit / "out/boltz_results_yaml/predictions" / name / f"{name}_model_0.pdb"
            Backend.audit_structure(path, old["input"]["sequence"], True)
            measures = geometry(path, settings, manifest, reference_molecule)
            rows.append(dict(arm=arm, id=name, **measures["metrics"]))
            raw_rows.append(dict(arm=arm, id=name, path=str(path), sha256=checksum(path), **measures))
            structures[arm] = path
        def coords(path):
            return {(c.name, str(r.seqid), a.name): [a.pos.x, a.pos.y, a.pos.z]
                    for c in gemmi.read_structure(str(path))[0] for r in c for a in r}
        a, b = coords(structures["singleton"]), coords(structures["batch"])
        if a.keys() != b.keys():
            raise ValueError("Unpaired output atoms")
        delta = np.array([a[k] for k in a]) - np.array([b[k] for k in a])
        conf = lambda path: read(path.parent / f"confidence_{name}_model_0.json")
        aligned = self_consistency(structures["batch"], structures["singleton"])
        changed = self_consistency(structures["singleton"], structures["original"])
        pairing.append(dict(id=name, pdb_bytes_identical=checksum(structures["singleton"]) == checksum(structures["batch"]),
                            max_coordinate_difference_a=float(np.abs(delta).max()),
                            coordinate_rms_difference_a=float(np.sqrt((delta**2).sum(axis=1).mean())),
                            confidence_identical=conf(structures["singleton"]) == conf(structures["batch"]),
                            batch_vs_singleton_ca_rmsd=aligned.ca_rmsd,
                            batch_vs_singleton_ligand_rmsd=aligned.ligand_rmsd,
                            off_vs_on_ca_rmsd=changed.ca_rmsd,
                            off_vs_on_ligand_rmsd=changed.ligand_rmsd))
    receipt_path = output / "batch/all/completed.json"
    receipt = read(receipt_path)
    timings["batch"].append(journal.load(receipt_path, receipt["input"]))
    if timings["batch"][0]["completed_jobs"] != len(ids):
        raise ValueError("Batch did not include every input in one request")
    worker_audit = {}
    for arm in ("singleton", "batch"):
        import yaml
        readies = [read(p) for p in (output / arm / "sessions").glob("*/ready.json")]
        responses = [read(p) for p in (output / arm / "sessions").glob("*/responses/*.json")]
        if (len(readies) != 1 or readies[0]["device"] != "mps" or readies[0]["fallback"] != 0
                or any(not r.get("ok") or r["model_load_count"] != 1 for r in responses)):
            raise ValueError("Resident worker audit failed; resumed runs require separate timing treatment")
        logs = "\n".join(p.read_text() for p in (output / arm / "sessions").glob("*/worker.log"))
        fallbacks = [x for x in logs.splitlines() if "will fall back to run on the CPU" in x]
        if any("aten::linalg_svd" not in x for x in fallbacks):
            raise ValueError("Unexpected CPU fallback")
        resets = logs.count("IPROTEINSTUDIO_MPS_ALLOCATOR_RESET|boltz|")
        if resets != len(ids):
            raise ValueError("Wrong number of actual model input batches")
        parameters = [yaml.safe_load(p.read_text()) for p in (output / arm).rglob("hparams.yaml")]
        for hp in parameters:
            steering = hp["steering_args"]
            if (steering["fk_steering"] or steering["physical_guidance_update"]
                    or not steering["contact_guidance_update"]
                    or hp["predict_args"]["recycling_steps"] != 3
                    or hp["predict_args"]["sampling_steps"] != 200
                    or hp["predict_args"]["diffusion_samples"] != 1):
                raise ValueError("Executed predictor settings differ from the comparison")
        if len(parameters) != len(responses):
            raise ValueError("Missing executed-model parameter record")
        step_times = [(name, float(seconds)) for name, seconds in
                      re.findall(r"REPLAY\|(?:capture|replay)\|(L\d+)\|([0-9.]+)", logs)]
        if len(step_times) != len(ids) or sorted(name for name, _ in step_times) != ids:
            raise ValueError("Missing or duplicate per-input model-step timings")
        worker_audit[arm] = dict(pid=readies[0]["pid"], model_load_count=1,
            requests=len(responses), model_input_batches=resets,
            startup_seconds=readies[0]["startup_seconds"], documented_svd_warnings=len(fallbacks),
            fallback_warnings=fallbacks, model_step_seconds=dict(step_times))
    summary = {}
    for arm, receipts in timings.items():
        selected = [r for r in rows if r["arm"] == arm]
        duration = sum(r["wall_seconds"] for r in receipts)
        startup = receipts[0]["startup_seconds"]
        summary[arm] = dict(count=len(ids), request_seconds=duration, seconds_per_initialization=duration / len(ids),
            startup_seconds=startup, amortized_seconds_including_startup=(duration + startup) / len(ids),
            atom_pass_count=sum(r["atom_checks_passed"] for r in selected),
            hotspot_pass_count=sum(r["hotspots_passed"] for r in selected),
            exposure_pass_count=sum(r["exposed_passed"] for r in selected),
            clean_continuity_count=sum(r["continuity_violations"] == 0 for r in selected),
            no_severe_protein_ligand_overlap_count=sum(r["severe_protein_ligand_overlaps"] == 0 for r in selected),
            no_severe_nonlocal_protein_overlap_count=sum(r["severe_nonlocal_protein_overlaps"] == 0 for r in selected),
            valid_ligand_bonds_count=sum(r["ligand_bond_violations"] == 0 for r in selected),
            correct_ligand_chirality_count=sum(r["ligand_chiral_errors"] == 0 for r in selected),
            mean_ligand_plddt=statistics.mean(r["ligand_plddt"] for r in selected),
            median_pl_overlaps=statistics.median(r["severe_protein_ligand_overlaps"] for r in selected),
            median_pp_overlaps=statistics.median(r["severe_nonlocal_protein_overlaps"] for r in selected))
        if arm in worker_audit:
            forward = sum(worker_audit[arm]["model_step_seconds"].values())
            summary[arm].update(mean_model_step_seconds=forward / len(ids),
                                mean_other_request_seconds=(duration - forward) / len(ids))
    indexed = {(r["arm"], r["id"]): r for r in rows}
    transitions = {}
    for before, after in (("original", "singleton"), ("singleton", "batch")):
        transitions[f"{before}_to_{after}"] = dict(
            atom_pass_gains=[i for i in ids if not indexed[before, i]["atom_checks_passed"] and indexed[after, i]["atom_checks_passed"]],
            atom_pass_losses=[i for i in ids if indexed[before, i]["atom_checks_passed"] and not indexed[after, i]["atom_checks_passed"]],
            mean_ligand_plddt_change=statistics.mean(indexed[after, i]["ligand_plddt"] - indexed[before, i]["ligand_plddt"] for i in ids),
            max_absolute_ligand_plddt_change=max(abs(indexed[after, i]["ligand_plddt"] - indexed[before, i]["ligand_plddt"]) for i in ids))
    return dict(summary=summary, workers=worker_audit, pairing=pairing, transitions=transitions, rows=rows, raw_metrics=raw_rows,
                timing_receipts=timings, audit_passed=True,
                limits="Initializations with X residues; all-atom completeness and biological binding untested. Severe overlaps >1 Å vdW overlap are descriptive, not a calibrated clashscore. Bond bounds use RDKit distance geometry plus 0.15 Å tolerance. No default promotion.")


def report(result, destination):
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    with (destination / "metrics.csv").open("w") as f:
        w = csv.DictWriter(f, fieldnames=list(result["rows"][0])); w.writeheader(); w.writerows(result["rows"])
    rows = result["summary"]
    names = dict(original="Original: physical/FK on", singleton="Pocket only: separate requests", batch="Pocket only: one request")
    fields = [("Seconds / initial structure", "seconds_per_initialization"),
              ("Pocket + exposure pass", "atom_pass_count"), ("Pocket contacts pass", "hotspot_pass_count"),
              ("Terminal exposure pass", "exposure_pass_count"), ("No continuity warnings", "clean_continuity_count"),
              ("No severe protein–ligand overlaps", "no_severe_protein_ligand_overlap_count"),
              ("No severe nonlocal protein overlaps", "no_severe_nonlocal_protein_overlap_count"),
              ("Ligand bond lengths pass diagnostic", "valid_ligand_bonds_count"),
              ("Ligand chirality preserved", "correct_ligand_chirality_count"),
              ("Mean ligand pLDDT (0–100)", "mean_ligand_plddt")]
    wrong_after = [r["id"] for r in result["rows"] if r["arm"] == "singleton" and r["ligand_chiral_errors"]]
    escaped = [r["id"] for r in result["rows"] if r["arm"] == "singleton" and r["ligand_chiral_errors"] and r["atom_checks_passed"]]
    lines = ["# Biotin pocket-guidance replay", "", f"Paired initial backbones: n={rows['original']['count']}; Apple M4 Max, 64 GB.", "",
             f"**Pocket-only was faster, but introduced incorrect ligand stereochemistry in {len(wrong_after)} inputs.** The original set preserved biotin stereochemistry in all {rows['original']['count']}. Both RDKit CIP assignment and an independent signed-volume check against the actual frozen input conformer agree. Incorrect-chirality inputs that nevertheless passed the existing contact/exposure filters: {', '.join(escaped) or 'none'}.", "",
             "This comparison does not support switching off physical/FK guidance as a default. Pocket contacts and confidence alone do not catch these chemical errors. All numerical results below describe this bounded initial-backbone test; the main campaign stays paused.", "",
             "| Measure | " + " | ".join(names.values()) + " |", "|---|---:|---:|---:|"]
    for title, key in fields:
        lines.append("| " + title + " | " + " | ".join(f"{rows[a][key]:.2f}" if isinstance(rows[a][key], float) else str(rows[a][key]) for a in names) + " |")
    exact = sum(r["pdb_bytes_identical"] and r["confidence_identical"] for r in result["pairing"])
    lines += ["", f"Singleton/batch identical PDB bytes and confidence JSON: {exact}/{len(result['pairing'])}.",
        f"Singleton/batch aligned Cα RMSD: median {statistics.median(r['batch_vs_singleton_ca_rmsd'] for r in result['pairing']):.4f} Å; maximum {max(r['batch_vs_singleton_ca_rmsd'] for r in result['pairing']):.4f} Å. Ligand RMSD after the same protein alignment: median {statistics.median(r['batch_vs_singleton_ligand_rmsd'] for r in result['pairing']):.4f} Å; maximum {max(r['batch_vs_singleton_ligand_rmsd'] for r in result['pairing']):.4f} Å.",
        "", "Timing is measured worker request wall time divided by completed inputs; model startup is reported separately in audit.json. It includes loading inputs, RNG/feature instrumentation, prediction, confidence and output validation. Original timing includes YAML/RDKit preprocessing; both replay arms reuse the original processed inputs to hold ligand conformers fixed. Thus the original-to-replay speed ratio includes that preparation difference. Batching means one directory request with data-loader batch size1, not simultaneous folding of all proteins.",
        "", "Physical/FK-off retains contact-guidance updates and the identical force:true pocket YAML. Affinity is omitted in every arm, matching initial generation. The full campaign remains paused.",
        "", result["limits"], "", "Raw results, per-input metrics, fingerprints, random-state pairing and request receipts are retained. Geometry diagnostics are not experimental evidence of binding. Arm order was not randomized and there are no repeated timing trials."]
    transition = result["transitions"]["singleton_to_batch"]
    lines += ["", f"Batching changed the pocket/exposure verdict for {len(transition['atom_pass_gains']) + len(transition['atom_pass_losses'])} inputs: gains {transition['atom_pass_gains']}; losses {transition['atom_pass_losses']}.",
              "", "Request-time decomposition (measured model step, then remaining request overhead):"]
    for arm in ("singleton", "batch"):
        lines.append(f"- {names[arm]}: {rows[arm]['mean_model_step_seconds']:.2f} + {rows[arm]['mean_other_request_seconds']:.2f} seconds per input.")
    lines += ["", "[Overview figure](overview.svg) · [Per-input metrics](metrics.csv) · [Full audit and detailed atom checks](audit.json)"]
    (destination / "REPORT.md").write_text("\n".join(lines) + "\n")


def figure(result, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({"font.family": "Arial", "text.color": "black", "axes.labelcolor": "black",
        "xtick.direction": "in", "ytick.direction": "in", "svg.fonttype": "none", "axes.grid": False})
    fig, axes = plt.subplots(2, 2, figsize=(10.4, 7.5))
    arms = ["original", "singleton", "batch"]
    labels = ["Physical/FK on", "Pocket only\nSeparate requests", "Pocket only\nOne request"]
    colors = ["#737373", "#4B92C2", "#C99A3B"]
    summary = result["summary"]
    n = summary["original"]["count"]
    ax = axes[0, 0]
    values = [summary[a]["seconds_per_initialization"] for a in arms]
    ax.bar(range(3), values, color=colors, edgecolor="black")
    for i, value in enumerate(values):
        ax.text(i, value, f"{value:.1f}", ha="center", va="bottom")
    ax.set(xticks=range(3), xticklabels=labels, ylabel="Request seconds / initial structure", title="A  Measured wall time", ylim=(0, max(values) * 1.15))
    ax = axes[0, 1]
    metrics = [("Pocket +\nexposure", "atom_pass_count"), ("Backbone\ncontinuity", "clean_continuity_count"),
               ("No severe\nligand clash", "no_severe_protein_ligand_overlap_count"),
               ("Ligand\nchirality", "correct_ligand_chirality_count")]
    for j, arm in enumerate(arms):
        ax.bar(np.arange(len(metrics)) + (j - 1) * .25,
               [summary[arm][k] for _, k in metrics], width=.24, color=colors[j], edgecolor="black")
    ax.set(xticks=range(len(metrics)), xticklabels=[m[0] for m in metrics], ylabel=f"Initial structures passing / {n}",
           title="B  Geometry diagnostics", ylim=(0, n * 1.12))
    by_arm = {a: {r["id"]: r for r in result["rows"] if r["arm"] == a} for a in arms}
    for ax, metric, label, title in [(axes[1, 0], "ligand_plddt", "Ligand pLDDT (0–100)", "C  Confidence is not binding evidence"),
            (axes[1, 1], "min_terminal_exposure", "Minimum terminal SASA retention", "D  Linker-attachment exposure")]:
        for name in by_arm["original"]:
            ax.plot(range(3), [by_arm[a][name][metric] for a in arms], color="#B7B7B7", linewidth=.6, zorder=1)
        for j, arm in enumerate(arms):
            ax.scatter([j] * n, [r[metric] for r in by_arm[arm].values()], s=20, color=colors[j], edgecolor="black", linewidth=.4, zorder=2)
        ax.set(xticks=range(3), xticklabels=labels, ylabel=label, title=title)
        if metric == "min_terminal_exposure":
            ax.axhline(.5, color="black", linestyle="--", linewidth=.8); ax.set_ylim(-.04, 1.05)
    for ax in axes.flat:
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(f"Biotin: paired replay of {n} initial backbones · Apple M4 Max / 64 GB", fontsize=13)
    fig.text(.5, .01, "Unit: completed X-containing cycle00 input. Forced pocket retained. No affinity.\nOriginal includes preprocessing; replay uses its frozen conformers. One request still folds inputs sequentially.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .055, 1, .96))
    fig.savefig(destination / "overview.svg", transparent=True)
    fig.savefig(destination / "overview.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path)
    p.add_argument("--plot-audit", type=Path, help="Plot an existing audit using a plotting environment; no inference")
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    if args.plot_audit:
        figure(read(args.plot_audit), args.report)
    else:
        if args.output is None:
            p.error("--output or --plot-audit is required")
        result = analyse(args.output)
        report(result, args.report)
        print(json.dumps(dict(summary=result["summary"], pairing=result["pairing"], workers=result["workers"]), indent=2))
