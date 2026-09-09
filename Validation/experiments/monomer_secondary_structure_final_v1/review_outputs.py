"""Inspect completed monomer outputs and report all outcomes without new inference."""
from collections import Counter
from datetime import datetime, timezone
import csv
import importlib.util
import json
from pathlib import Path
import statistics as stats
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "monomer_secondary_structure_recovery_v1"))
import recover
c, a = recover.c, recover.a

LABELS = ["Baseline", "Helix kill", "Beta prior", "Mixed", "Beta + inspection",
          "Sustained helix kill", "Sustained beta", "Sustained mixed", "Helix kill strength 1.0",
          "Beta residue weight off", "Beta pattern weight off", "Turn weight off", "Beta, no X mask",
          "Beta, sample then mask", "Proline suppression (loopkill=1)", "First MPNN temperature 0.1",
          "Later MPNN temperature 0.3", "First MPNN P bias -0.5", "Later MPNN P bias -0.5",
          "Inspection, one attempt", "Inspection, coil length 8", "Inspection, confidence 70"]


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def main():
    latest = c.read(recover.RECOVERY / "latest_report.json")
    report_path = Path(latest["path"]) / "report.json"
    c.require(latest["complete"] and c.sha(report_path) == latest["report_sha256"], "Complete report identity differs")
    report = c.read(report_path)
    c.require(report["complete"] and report["audited_trajectories"] == 220, "Campaign incomplete")
    paths = sorted((c.OUTPUT / "audits").glob("*/*.json")) + [recover.RECOVERY / "geometry_failure_audit.json"]
    c.require(len(paths) == 44, "Expected 44 audited cohort phases")
    audits = [recover.verify_audit(c.read(p)) for p in paths]
    c.require({str(p.relative_to(c.OUTPUT)): c.sha(p) for p in paths} == report["input_audit_sha256"], "Report input audit identities differ")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = c.OUTPUT / "final_inspection" / stamp
    output.mkdir(parents=True)
    (output / "inspect_source.py").write_bytes(Path(__file__).read_bytes())
    snapshot = c.OUTPUT / "campaigns/pilot__baseline/.studio_runtime/pipeline/scripts"
    assessment = module_at("frozen_assessment", snapshot / "initialization_assessment.py")
    geometry = module_at("frozen_geometry", snapshot / "validate_prediction_geometry.py")
    stage = c.read(c.OUTPUT / "stage_receipt.json")
    for d in audits:
        root = c.OUTPUT / "campaigns" / f"{d['phase']}__{d['arm']}" / ".studio_runtime/pipeline"
        for name in ("nanohunter_run.sh", "scripts/initialization_assessment.py", "scripts/initialization_refinement.py", "scripts/secondary_structure_control.py"):
            c.require(c.sha(root / name) == stage["files"][name]["after_sha256"], "Snapshot differs from frozen stage")
        c.require(c.sha(root / "scripts/validate_prediction_geometry.py") == c.sha(snapshot / "validate_prediction_geometry.py"), "Geometry validator differs between cohorts")
    rows = [r for d in audits for r in d["trajectories"]]
    structures = [r for d in audits for r in d["structures"]]
    c.require(len({(r['arm'], r['trajectory']) for r in rows}) == 220, "Missing/duplicate trajectory identity")
    outcomes = Counter(r["outcome"] for r in rows)
    c.require(dict(outcomes) == report["outcomes"], "Outcome accounting differs")
    cache = {}
    def inspect_structure(path, sequence, expected=None):
        key = (c.sha(path), sequence)
        if key not in cache:
            c.require(not geometry.validate(path), f"Unexpected invalid accepted geometry: {path}")
            cache[key] = assessment.assess_structure(path, sequence, a.ASSESSMENT)
        actual = cache[key]
        if expected:
            c.require(actual["psea"] == expected["psea"], "P-SEA changed")
            c.require(actual["confidence"] == expected["per_residue_confidence"], "CA confidence changed")
            for metric in ("helix", "sheet", "coil"):
                c.require(abs(actual["fractions"][metric] - expected[metric]) < 1e-12, "Structural fraction changed")
        return actual
    for i, r in enumerate(structures, 1):
        inspect_structure(c.OUTPUT / r["structure"], r["sequence"], r)
        if i % 200 == 0:
            print(json.dumps({"checked_cycle_records": i, "total": len(structures)}), flush=True)
    inspections = {}
    for arm, config in c.CONFIG["arms"].items():
        if "inspection" not in config:
            continue
        group = [r for r in rows if r["arm"] == arm]
        attempts = []
        for t in group:
            local = t["trajectory"] if t["phase"] == "pilot" else t["trajectory"] - 1
            root = c.OUTPUT / "campaigns" / f"{t['phase']}__{arm}" / f"run_{local:03d}/initialization_refinement"
            status = a.Refinement(root).status()
            c.require(status["state"] == ("accepted" if t["outcome"] == "completed" else "budget_exhausted"), "Journal outcome differs")
            candidates = sorted(root.glob("attempt_*"))
            c.require(len(candidates) == t["attempts"], "Journal attempt count differs")
            for path in candidates:
                candidate = c.read(path / "input.json")
                models = list((path / "prediction").glob("model_0.*"))
                c.require(len(models) == 1, "Initialization prediction cardinality differs")
                actual = inspect_structure(models[0], candidate["sequence"])
                saved = c.read(path / "assessment/assessment.json")
                reassessed = assessment.assess(actual["psea"], actual["confidence"], config["inspection"])
                c.require(all(saved[k] == reassessed[k] for k in reassessed), "Recorded assessment decision does not reproduce")
                attempts.append({"trajectory": t["trajectory"], "attempt": candidate["index"], "eligible": reassessed["eligible"],
                                 "selected": candidate["index"] == t["selected_attempt"], "changes": len(candidate["changes"])})
        completed = {t["trajectory"]: t for t in group if t["outcome"] == "completed"}
        reference = {r["trajectory"]: r for r in rows if r["arm"] == "beta_inspection" and r["outcome"] == "completed"}
        decomposition = {}
        for metric in ("sheet", "helix", "coil", "plddt"):
            key = "mean_" + metric
            ref_all = stats.mean(r[key] for r in reference.values())
            ref_survivors = stats.mean(reference[i][key] for i in completed)
            observed = stats.mean(r[key] for r in completed.values())
            decomposition[metric] = {"observed_difference": observed - ref_all,
                                     "selection_of_trajectory_ids": ref_survivors - ref_all,
                                     "change_within_shared_trajectory_ids": observed - ref_survivors}
        inspections[arm] = {"policy": config["inspection"], "outcomes": dict(Counter(t["outcome"] for t in group)),
                            "attempt_histogram": dict(Counter(t["attempts"] for t in group)),
                            "attempt_predictions": len(attempts), "extra_initializations": len(attempts) - 10,
                            "refined_ids": [t["trajectory"] for t in group if t["attempts"] > 1],
                            "exhausted_ids": [t["trajectory"] for t in group if t["outcome"] != "completed"],
                            "attempts": attempts, "decomposition_vs_main_inspection": decomposition}
    invalid = audits[-1]["rejection"]
    invalid_issues = geometry.validate(c.OUTPUT / invalid["structure"])
    c.require(invalid_issues == invalid["diagnostic"], "Rejected-geometry diagnosis changed")
    identities = {arm: {r["trajectory"]: r for r in rows if r["arm"] == arm} for arm in c.CONFIG["arms"]}
    for arm in identities:
        c.require(sorted(identities[arm]) == list(range(1, 11)), "Declared trajectory cardinality differs")
        for t in identities[arm].values():
            if t["outcome"] != "completed":
                continue
            cycles = [r for r in structures if r["arm"] == arm and r["trajectory"] == t["trajectory"] and r["cycle"] > 0]
            c.require(sorted(r["cycle"] for r in cycles) == list(range(1, 6)), "Cycle count differs")
            for metric in a.METRICS:
                c.require(abs(stats.mean(r[metric] for r in cycles) - t["mean_" + metric]) < 1e-10, "Trajectory aggregate differs")
    loopkill = [r for r in structures if r["arm"] == "baseline_loopkill_1"]
    c.require(all("P" not in r["sequence"] for r in loopkill), "Full proline suppression not observed")
    coil_confidence = {}
    for arm in identities:
        cycle_rows = [r for r in structures if r["arm"] == arm and r["cycle"] > 0]
        # Every included trajectory has exactly five cycles, so this mean is
        # identical to equal weighting of trajectory means.
        coil_confidence[arm] = {
            "coil_plddt_at_least_70": stats.mean(sum(code == "c" and p >= 70 for code, p in zip(r["psea"], r["per_residue_confidence"])) / 90 for r in cycle_rows),
            "coil_plddt_below_50": stats.mean(sum(code == "c" and p < 50 for code, p in zip(r["psea"], r["per_residue_confidence"])) / 90 for r in cycle_rows),
            "long_uncertain_coil": stats.mean(r["uncertain_coil_fraction"] for r in cycle_rows)}
    svd = sum(len(d["svd_fallback_log_lines"]) for d in audits)
    result = {"time": c.now(), "complete": True, "manifest_sha256": c.sha(c.OUTPUT / "manifest.json"),
              "source_report": str(report_path), "source_report_sha256": c.sha(report_path),
              "input_audit_sha256": report["input_audit_sha256"], "outcomes": dict(outcomes),
              "optimized_structures": sum(r["cycle"] > 0 for r in structures),
              "checked_cycle_prediction_records": len(structures), "checked_journal_prediction_records": sum(d["attempt_predictions"] for d in inspections.values()),
              "unique_sequence_coordinate_checks": len(cache), "reproduced_geometry_rejections": len(invalid_issues),
              "recorded_svd_warning_lines": svd, "inspection": inspections,
              "coil_confidence": coil_confidence,
              "model_weights_read_or_changed": False, "new_model_inference": False,
              "assessment_code_sha256": c.sha(snapshot / "initialization_assessment.py"),
              "geometry_code_sha256": c.sha(snapshot / "validate_prediction_geometry.py"),
              "analysis_code_sha256": c.sha(Path(__file__)), "summaries": report["summaries"],
              "predeclared_contrasts": report["predeclared_contrasts"],
              "additional_exploratory_baseline_contrasts": report["additional_exploratory_baseline_contrasts"]}
    c.atomic(output / "inspection.json", result)
    fields = ["arm", "trajectory", "outcome", "attempts", "completed_cycles", "mean_helix", "mean_sheet", "mean_coil", "mean_plddt", "final_helix", "final_sheet", "final_coil", "final_plddt"]
    with (output / "trajectories.csv").open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
    write_report(output, result)
    plot(output, report, identities)
    c.atomic(c.OUTPUT / "final_inspection/latest.json", {"path": str(output), "complete": True, "inspection_sha256": c.sha(output / "inspection.json")})
    print(json.dumps({"output": str(output), "complete": True, "outcomes": dict(outcomes), "unique_coordinate_checks": len(cache)}), flush=True)


def write_report(output, result):
    names = list(c.CONFIG["arms"])
    lines = ["# Complete monomer secondary-structure benchmark", "", f"Inspection completed: {result['time']}", "",
             "All 220 declared trajectories are accounted for: 214 completed five optimization cycles (1,070 optimized structures), five exhausted initialization budgets, and one was rejected for invalid geometry. No failed seed was replaced.", "",
             "Boltz-2, 90 residues, ten declared trajectories per condition. Structural fractions use Biotite P-SEA on coordinates. Values average cycles 01–05 within each completed trajectory, then average trajectories equally. Cycle 00 is excluded. pLDDT is mean CA confidence on the 0–100 scale. Means are conditional on completion where n is below ten.", "",
             "| Condition | Completed / declared | Helix | Sheet | Coil | Mean pLDDT | Final pLDDT |", "|---|---:|---:|---:|---:|---:|---:|"]
    for name, label in zip(names, LABELS):
        s = result["summaries"][name]
        values = [f"{100*s['mean_'+m]:.1f}%" for m in ("helix", "sheet", "coil")]
        lines.append(f"| {label} | {s['completed_n']}/10 | {' | '.join(values)} | {s['mean_plddt']:.1f} | {s['final_plddt']:.1f} |")
    lines += ["", "## Interpretation", "",
              "Full proline suppression is the strongest tested way to favor helices and reduce coil: versus baseline, helix rises 27.7 percentage points, coil falls 17.1 points and sheet falls 10.6 points. Mean pLDDT rises 6.5. The control removes proline from initialization and all MPNN cycles; this is distinct from the weaker P:-0.5 MPNN-only biases. All saved sequences in this arm are proline-free.", "",
              "Sustained priors have clear incremental effects relative to initialization-only priors with the same starting sequences. Sheet rises 6.3 points for sustained helix kill, 3.9 for sustained beta, and 3.8 for sustained mixed. These are small absolute gains for sustained beta (10.3% sheet), and sustained mixed retains 57.5% coil with mean pLDDT 72.6. Its confidence falls 5.8 points relative to initialization-only mixed.", "",
              "Removing X masking changes sheet by +14.7 points relative to beta-only but also adds 12.3 points coil. Sample-then-mask gives 17.8% sheet among nine completed trajectories; its sheet-change interval includes zero. One original prediction failed the unchanged geometry gate and is retained as a failure.", "",
              "The beta-oriented prior itself does not establish beta enrichment over baseline. Its 6.4% mean sheet fraction falls to 4.4% at the final cycle, compared with baseline's 18.4% mean and 19.4% final. Disabling beta residue, pattern or turn weighting gives uncertain mean sheet increases over beta-only; this screen does not identify a beneficial component or optimal strength.", "",
              "MPNN temperature and weak global proline-bias changes have much smaller effects. Raising later temperature from 0.1 to 0.3 adds 1.8 points sheet (exploratory paired interval +0.2 to +3.5), but mean sheet remains only 8.1%. Lowering the first temperature and either P:-0.5 bias do not establish sheet gains.", "",
              "Main inspection repairs two initializations once each and retains all ten trajectories; its other eight reproduce beta-only metrics. A one-attempt budget discards those same two starts, and the eight survivors exactly match the main-inspection survivors. Raising the confidence threshold to 70 changes only one trajectory's structural endpoint appreciably and provides no robust additional benefit.", "",
              "Reducing the qualifying coil length from 16 to 8 is counterproductive for beta enrichment: three trajectories exhaust their budgets, the seven completed trajectories have only 0.1% mean sheet and zero sheet at cycle 05, and the condition requires 11 extra initialization predictions. Its apparent mean-confidence advantage is due to which trajectory IDs survive: matched to those same seven IDs, pLDDT is 0.7 points lower than main inspection. This criterion screens uncertain coil without protecting desired secondary structure.", "",
              "No condition establishes a sheet-enrichment advantage over baseline in the available paired intervals. Higher-sheet means in strong helix kill and sustained mixed come with considerable coil and lower confidence. These results support effects on predicted composition, not experimental fold validation or a new default.", "",
              "## Paired contrasts", "", "Ten-thousand paired bootstrap resamples; exploratory 95% intervals without multiplicity adjustment. Units are percentage points for fractions and pLDDT points for confidence. Failed trajectories are excluded from paired structural differences, with n shown.", "",
              "| Condition vs declared reference | n pairs | Δ helix [CI] | Δ sheet [CI] | Δ coil [CI] | Δ pLDDT [CI] |", "|---|---:|---:|---:|---:|---:|"]
    friendly = dict(zip(names, LABELS))
    for name in names:
        if name not in result["predeclared_contrasts"]:
            continue
        d = result["predeclared_contrasts"][name]; values = []
        for m in ("helix", "sheet", "coil", "plddt"):
            x = d["metrics"][m]; scale = 1 if m == "plddt" else 100; low, high = x["bootstrap_95_ci"]
            values.append(f"{scale*x['mean_difference']:+.1f} [{scale*low:+.1f}, {scale*high:+.1f}]")
        lines.append(f"| {friendly[name]} vs {friendly[d['reference']]} | {d['metrics']['sheet']['n_pairs']} | {' | '.join(values)} |")
    lines += ["", "## Initialization inspection", "", "| Policy | Completed / declared | Extra predictions | Exhausted trajectory IDs |", "|---|---:|---:|---|"]
    for name, d in result["inspection"].items():
        lines.append(f"| {friendly[name]} | {d['outcomes'].get('completed',0)}/10 | {d['extra_initializations']} | {d['exhausted_ids'] or 'none'} |")
    lines += ["", "## Confidence of coil assignments", "",
              "Percentages below refer to all residues, averaged across completed trajectories and cycles 01–05. Long uncertain coil uses the common descriptive criterion: at least 16 consecutive coil residues individually below pLDDT 50. These are descriptive prediction-confidence bins, not experimentally validated disorder classifications.", "",
              "| Condition | Coil with pLDDT ≥70 | Coil with pLDDT <50 | Long uncertain coil |", "|---|---:|---:|---:|"]
    for name in names:
        d = result["coil_confidence"][name]
        lines.append(f"| {friendly[name]} | {100*d['coil_plddt_at_least_70']:.1f}% | {100*d['coil_plddt_below_50']:.1f}% | {100*d['long_uncertain_coil']:.1f}% |")
    lines += ["", "Mixed initialization includes more confidently assigned coil than baseline (34.7% versus 25.6% of all residues at pLDDT ≥70). Its extra coil should not all be interpreted as uncertainty or disorder. Sustaining mixed control also increases low-confidence coil: 13.9% of all residues are coil below pLDDT 50, versus 7.7% for initialization-only mixed.", "",
              "## Output verification and limits", "",
              f"Reverified 44 cohort audit records against raw hashes, all frozen pipeline/assessor/geometry-validator identities, {result['checked_cycle_prediction_records']} cycle prediction records, and {result['checked_journal_prediction_records']} initialization-journal prediction records. Recomputed coordinate-based P-SEA, confidence, geometry checks and trajectory aggregates; reassessed every initialization decision. Identical coordinate/sequence pairs were checked once ({result['unique_sequence_coordinate_checks']} unique checks). The original geometry rejection was independently reproduced. Recorded SVD warning lines: {result['recorded_svd_warning_lines']} (warnings, not a count of individual CPU operations).", "",
              "Only 90 residues, one predictor and one paired seed cohort. Confidence and P-SEA are predictions, coil is not a disorder diagnosis, and a sequence prior does not guarantee a fold. The screen is not an exhaustive sweep or a full interaction design. No inference rerun, altered threshold, replacement seed or default promotion was used in this inspection.", ""]
    (output / "REPORT.md").write_text("\n".join(lines))


def plot(output, report, identities):
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({"font.family": "Arial", "text.color": "black", "axes.labelcolor": "black", "axes.edgecolor": "black",
                         "xtick.direction": "in", "ytick.direction": "in", "axes.grid": False})
    names = list(c.CONFIG["arms"]); y = np.arange(len(names)); left = np.zeros(len(names))
    fig, axes = plt.subplots(1, 3, figsize=(16, 10), gridspec_kw={"width_ratios": [2, 1, 1]}, layout="constrained")
    for metric, color in (("helix", "#d5916c"), ("sheet", "#73a2b9"), ("coil", "#d5d5d5")):
        values = np.array([100 * report['summaries'][n]['mean_' + metric] for n in names])
        axes[0].barh(y, values, left=left, label=metric.capitalize(), color=color, edgecolor="black", linewidth=.7); left += values
    axes[0].set_yticks(y, [f"{label} (n={report['summaries'][n]['completed_n']}/10)" for n, label in zip(names, LABELS)])
    axes[0].set_xlim(0,100); axes[0].set_xlabel("Mean residues (%)"); axes[0].legend(loc="upper center", bbox_to_anchor=(.5,1.06), ncol=3)
    for i, name in enumerate(names):
        t = [r for r in identities[name].values() if r['outcome']=='completed']
        jitter = np.linspace(-.17,.17,len(t))
        axes[1].scatter([100*r['mean_sheet'] for r in t], i+jitter, color="#73a2b9", edgecolor="black", linewidth=.5, s=18)
        axes[1].plot([100*report['summaries'][name]['mean_sheet']]*2,[i-.3,i+.3],color="black",linewidth=2)
    axes[1].set_xlim(-2,100); axes[1].set_xlabel("Sheet per trajectory (%)")
    axes[2].scatter([report['summaries'][n]['mean_plddt'] for n in names], y, color="black", s=23)
    axes[2].set_xlim(0,100); axes[2].set_xlabel("Mean CA pLDDT")
    for ax in axes:
        ax.set_ylim(len(names)-.6,-.6)
    for ax in axes[1:]:
        ax.set_yticks(y, [])
    fig.suptitle("Complete Boltz-2 monomer control screen · 90 residues · cycles 01–05\n214/220 completed trajectories; 5 budget exhaustions and 1 geometry rejection retained",fontsize=12)
    fig.savefig(output / "all_controls.svg", transparent=True); fig.savefig(output / "all_controls.png",dpi=170); plt.close(fig)


if __name__ == "__main__":
    main()
