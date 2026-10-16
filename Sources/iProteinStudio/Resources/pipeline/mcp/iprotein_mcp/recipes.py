"""Pure authoring contracts. A recipe is deliberately NOT an execution plan.

No engine detection, file access to user inputs, scheduling, or scientific imports.
The browser prototype and MCP use these same catalogue/validation functions.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from .common import StudioError, validate_schema

CATALOG_VERSION = "studio-recipes-prototype-1"
SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "schemas/recipe-v1.json").read_text())


def module(label, role, takes, gives, goals, explanation, icon):
    return dict(label=label, role=role, input=takes, output=gives, goals=goals,
                explanation=explanation, icon=icon)


PROTEIN = ["protein_binder"]
ALL = ["protein_binder", "nanobody", "ligand_binder"]
MODULES = {
    "protein_target": module("Choose a protein target", "input", "none", "protein_target", PROTEIN,
        "Start with the protein you want to bind. Target chains and any known binding site must be inspected before a real plan.", "◎"),
    "scaffold_target": module("Choose target + nanobody scaffold", "input", "none", "scaffold_target", ["nanobody"],
        "A fixed framework is part of the input. Keep framework identity and per-framework budgets in the route.", "◎"),
    "ligand_target": module("Choose a small molecule", "input", "none", "ligand_target", ["ligand_binder"],
        "A small molecule needs an exact chemical identity and reviewed atom selections. A protein target is a different problem.", "◎"),
    "rfd3": module("Build a backbone", "generate", "protein_target", "backbone", PROTEIN,
        "RFdiffusion3 proposes a shape. The backbone still needs an amino-acid sequence. Studio derives the de-novo contig.", "〰"),
    "solublempnn": module("Write the sequence · SolubleMPNN", "sequence", "backbone", "sequence", PROTEIN,
        "Assign amino acids to the backbone. SolubleMPNN is Studio’s default for a soluble protein–protein binder.", "Aa"),
    "proteinmpnn": module("Write the sequence · ProteinMPNN", "sequence", "backbone", "sequence", PROTEIN,
        "An explicit alternative to SolubleMPNN for protein interfaces. Changing designers is a scientific comparison.", "Aa"),
    "lasermpnn": module("LASErMPNN · ligand interfaces only", "sequence", "ligand_backbone", "sequence", ["ligand_binder"],
        "LASErMPNN belongs inside the ligand workflow. It cannot replace SolubleMPNN on a protein target.", "Aa"),
    "boltz": module("Predict the complex · Boltz-2", "predict", "sequence", "predicted_complex", PROTEIN,
        "Predict the completed binder with its target. A prediction is a hypothesis, not evidence of experimental binding.", "◇"),
    "protenix": module("Predict the complex · Protenix v2", "predict", "sequence", "predicted_complex", PROTEIN,
        "Use an alternative complex predictor. Keep its own scores and MSA policy; do not combine scores into a universal rating.", "◇"),
    "hunter": module("Redesign + predict · Protein Hunter", "refine", "predicted_complex", "predicted_complex", PROTEIN,
        "A bounded redesign/re-prediction block. Guidance belongs to each stage; generation guidance is not inherited automatically.", "↻"),
    "nanobody_hunter": module("Redesign a nanobody · Protein Hunter", "workflow", "scaffold_target", "predicted_complex", ["nanobody"],
        "A guided block for the existing iterative workflow, including sequence assignment and prediction. RFdiffusion3 de novo does not preserve fixed nanobody frameworks.", "↻"),
    "nise": module("Explore a ligand binder · NISE", "workflow", "ligand_target", "predicted_complex", ["ligand_binder"],
        "A guided block for ligand generation, LASErMPNN proposals and Boltz scoring. Its full budgets and chemical controls stay in NISE’s existing plan schema.", "↻"),
    "assess": module("Check independently", "assess", "predicted_complex", "checked_candidate", ALL,
        "Plan separate, untemplated complex and binder-alone checks. Preserve native metrics and the exact cycle/derivative; confidence does not prove binding.", "✓"),
    "save": module("Prepare a candidate record", "save", "checked_candidate", "candidate_record", ALL,
        "Keep the sequence, structures, recipe and plan digests, run/cycle/derivative, checks and later assay IDs together. No candidate is created by this demo.", "▤"),
}

GOALS = {
    "protein_binder": dict(label="Bind a protein", detail="From target to backbone, sequence and checked candidate.",
        guide="rfd3_protein_binder", kind="protein", stages=["protein_target", "rfd3", "solublempnn", "boltz", "assess", "save"]),
    "nanobody": dict(label="Redesign a nanobody", detail="Keep the framework; explore a guided redesign route.",
        guide="iterative_design", kind="protein", stages=["scaffold_target", "nanobody_hunter", "assess", "save"]),
    "ligand_binder": dict(label="Bind a small molecule", detail="Explore the dedicated ligand NISE workflow.",
        guide="nise", kind="ligand", stages=["ligand_target", "nise", "assess", "save"]),
}


def example(goal):
    g = GOALS[goal]
    return dict(schema_version=1, catalog_version=CATALOG_VERSION, name=g["label"], goal=goal,
                input=dict(label="Illustrative target", kind=g["kind"], source="sample",
                           target_msa="auto" if g["kind"] == "protein" else "not_applicable", binder_msa="empty"),
                budget=dict(starts=3, sequences_per_backbone=2, refinement_cycles=0),
                assessment=dict(predictor="esmfold2-full-mlx", independent=True, binder_alone=True),
                stages=[dict(id=f"s{i+1}", module=m) for i, m in enumerate(g["stages"])])


def recipe_catalog():
    return dict(catalog_version=CATALOG_VERSION, prototype=True, executable=False,
                modules=copy.deepcopy(MODULES), goals=copy.deepcopy(GOALS),
                examples={g: example(g) for g in GOALS}, schema=copy.deepcopy(SCHEMA))


def recipe_check(recipe):
    """Check a draft without normalizing, repairing, or replacing requested choices."""
    issues = []

    def issue(code, path, message):
        issues.append(dict(code=code, path=path, message=message))

    try:
        validate_schema(recipe, SCHEMA, "recipe")
    except StudioError as exc:
        return dict(valid=False, executable=False, prototype=True,
                    issues=[dict(code="length" if str(exc).endswith(" is too long.") else "schema", path="recipe", message=str(exc))])
    goal = recipe["goal"]
    expected = GOALS[goal]
    if recipe["input"]["kind"] != expected["kind"]:
        issue("target_kind", "input.kind", "Choose a target of the kind required by this scientific goal.")
    msa = recipe["input"]["target_msa"]
    if (expected["kind"] == "ligand") != (msa == "not_applicable"):
        issue("msa", "input.target_msa", "Protein targets need an explicit alignment policy; small molecules have no protein MSA.")
    state, ids, roles = "none", set(), []
    edges = []
    previous = None
    for i, stage in enumerate(recipe["stages"]):
        path = f"stages[{i}]"
        if stage["id"] in ids:
            issue("duplicate_id", path, "Each stage needs a unique ID so lineage is unambiguous.")
        ids.add(stage["id"])
        m = MODULES.get(stage["module"])
        if m is None:
            issue("unknown_module", path, "This module is not in the versioned catalogue. New engines require a separate qualification process.")
            continue
        roles.append(m["role"])
        if goal not in m["goals"]:
            issue("goal", path, f"{m['label']} is incompatible with this goal. {m['explanation']}")
        if m["input"] != state:
            issue("connection", path, f"{m['label']} needs {m['input'].replace('_', ' ')}; the preceding stage supplies {state.replace('_', ' ')}.")
        if previous:
            edges.append(dict(source=previous, destination=stage["id"], artifact=state))
        state, previous = m["output"], stage["id"]
    expected_roles = ["input", "generate", "sequence", "predict"] if goal == "protein_binder" else ["input", "workflow"]
    if "refine" in roles:
        expected_roles += ["refine"]
    expected_roles += ["assess", "save"]
    if roles != expected_roles:
        issue("order", "stages", "Complete the route in order: input, generation/sequence/prediction (or one guided workflow block), optional protein refinement, independent check, candidate record.")
    has_refine = "refine" in roles
    if has_refine != (recipe["budget"]["refinement_cycles"] > 0):
        issue("loop", "budget.refinement_cycles", "A Protein Hunter refinement block needs 1–5 cycles; without that block use 0. Guided workflow blocks keep their internal budgets in the existing planner.")
    if not recipe["assessment"]["independent"] or not recipe["assessment"]["binder_alone"]:
        issue("assessment", "assessment", "Keep separate complex and binder-alone checks before preparing a candidate record.")
    digest = hashlib.sha256(json.dumps(recipe, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    notices = ["This is an authoring prototype, not a scientific plan. It cannot start or queue jobs.",
               "Sample targets are labels, not structures. No engine installation, weights, chemistry or scientific outcome has been verified.",
               "Recipe compatibility does not establish scientific quality. A recipe digest is not a plan_sha256."]
    if goal != "protein_binder":
        notices.append("The guided block is not expanded here. Prototype budgets are placeholders; full workflow budgets must be reviewed in its existing planner.")
    return dict(valid=not issues, executable=False, prototype=True, issues=issues,
                recipe_sha256=digest, edges=edges, notices=notices,
                guide=expected["guide"], authoring_recipe=copy.deepcopy(recipe),
                handoff=["workflow_guide", "system_detect", "artifact_import / target_inspect when applicable",
                         "existing workflow-specific plan (recipe compiler not implemented)",
                         "review normalized request, pinned provenance and immutable plan digest",
                         "job_start only when running is authorized", "job_status / job_wait",
                         "results_overview", "results_query"],
                required_before_execution=["Replace the sample with exact content-addressed inputs and inspect chains/chemistry.",
                    "Bind all stage parameters, seeds, alignments, guidance, models and outputs to existing plan schemas; do not silently drop stages.",
                    "Qualify the complete route with an authorized small end-to-end smoke test before a campaign over 10 backbones."],
                candidate_record_fields=["recipe_sha256", "plan_id", "plan_sha256", "input_digests", "run_id", "cycle_or_derivative_id",
                                         "sequence", "structure_artifacts", "native_metrics", "check_verdicts", "assay_ids"])


def recipe_compare(baseline, variant, purpose="design_strategy"):
    a, b = recipe_check(baseline), recipe_check(variant)
    if not a["valid"] or not b["valid"]:
        raise StudioError("Both recipes must pass recipe_check before comparison.")
    if purpose not in {"design_strategy", "runtime"}:
        raise StudioError("Comparison purpose must be design_strategy or runtime.")
    differences = []

    def walk(x, y, path):
        if isinstance(x, dict) and isinstance(y, dict):
            for key in sorted(set(x) | set(y)):
                if key not in {"name", "id"}:
                    walk(x.get(key), y.get(key), f"{path}.{key}" if path else key)
        elif isinstance(x, list) and isinstance(y, list) and len(x) == len(y):
            for i, (left, right) in enumerate(zip(x, y)):
                walk(left, right, f"{path}[{i}]")
        elif x != y:
            differences.append(dict(path=path, baseline=x, variant=y))

    walk(baseline, variant, "")
    controls = ["goal", "input", "budget", "assessment"]
    changed_controls = [key for key in controls if baseline[key] != variant[key]]
    ready = bool(differences) and not changed_controls and purpose == "design_strategy"
    return dict(prototype=True, executable=False, purpose=purpose, differences=differences,
                matched_controls=not changed_controls, changed_controls=changed_controls,
                comparison_ready_for_review=ready, baseline_sha256=a["recipe_sha256"], variant_sha256=b["recipe_sha256"],
                advice=("Review the changed stage choices as a design-strategy comparison; predeclare comparable compute budgets and an experimental endpoint."
                        if ready else "Resolve changed controls or choose a meaningful stage change before comparing. Runtime comparisons need identical scientific settings plus a qualified runtime intervention; this prototype cannot specify one."),
                requirements=["Keep exact inputs, seeds, sampling budgets and independent assessment fixed; record failures and ancestry.",
                              "Measure elapsed time and memory on declared hardware; do not infer speed from this prototype.",
                              "Preserve native metrics and assay lineage. Improving an optimized score does not establish better binding."])
