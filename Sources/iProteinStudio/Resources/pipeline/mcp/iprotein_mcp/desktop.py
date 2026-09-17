"""Private native-app adapter. Deliberately absent from the MCP tool catalog.

The app has already validated and saved its request. Freeze its exact command
and inputs using the same registry, provenance checks and worker as MCP plans.
No shell/executable/environment fields are accepted from this request.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .common import StudioError, load_json, project_root, runtime_root, stable_environment, validate_slug
from .plans import _persist, _script_provenance, rfd3_runtime_scripts


def desktop_plan(request: Dict[str, Any]) -> Dict[str, Any]:
    project = validate_slug(request.get("project", ""))
    root = runtime_root()
    workflow = request.get("workflow")
    workspace = (root / "target_predictions").resolve() if workflow == "target_prepare" else project_root(project)
    output = Path(request.get("output", "")).resolve()
    if workspace not in output.parents:
        raise StudioError("The run must be inside its workspace.")
    workflow = request.get("workflow")
    inputs = []
    scripts = []
    steps = []
    environment = {}
    context = {}
    label_path = output / "studio_run_label.json"
    label_files = [label_path] if label_path.is_file() else []
    display_name = load_json(label_path).get("name") if label_files else None
    # The native form bounds grapheme length. Python code-point counts differ
    # for combining characters and emoji, so do not reject valid native labels.
    if display_name is not None and (not isinstance(display_name, str) or not display_name.strip()):
        raise StudioError("The saved run name must be nonempty text.")
    if workflow == "iterative_batch":
        descriptor_path = output / "studio_engine_batch.json"
        descriptor = load_json(descriptor_path)
        campaigns = descriptor.get("campaigns")
        labels = descriptor.get("engines")
        trajectories = descriptor.get("trajectoriesPerEngine")
        version = descriptor.get("version")
        if (version not in (1, 2) or not isinstance(campaigns, list)
                or not 2 <= len(campaigns) <= (256 if version == 2 else 16) or not all(isinstance(p, str) for p in campaigns)
                or len(set(campaigns)) != len(campaigns)
                or not isinstance(labels, list) or len(labels) != len(campaigns)
                or not all(isinstance(label, str) and label for label in labels)
                or type(trajectories) is not int or trajectories < 1):
            raise StudioError("The saved engine batch is incomplete or invalid.")
        budgets = [trajectories] * len(campaigns)
        if version == 2:
            budgets = descriptor.get("campaignBudgets")
            engine_ids, scaffold_ids = descriptor.get("engineIDs"), descriptor.get("scaffoldIDs")
            if (not isinstance(budgets, list) or len(budgets) != len(campaigns)
                    or any(type(n) is not int or not 1 <= n <= 10000 for n in budgets)
                    or any(not isinstance(items, list) or len(items) != len(campaigns)
                           or not all(isinstance(value, str) and value for value in items)
                           for items in (engine_ids, scaffold_ids))):
                raise StudioError("The saved scaffold allocations are incomplete or invalid.")
            groups = {}
            for engine, scaffold, budget in zip(engine_ids, scaffold_ids, budgets):
                group = groups.setdefault(engine, {})
                if scaffold in group:
                    raise StudioError("An engine/scaffold pair appears more than once.")
                group[scaffold] = budget
            if any(sum(group.values()) != trajectories or group != next(iter(groups.values())) for group in groups.values()):
                raise StudioError("Every engine must receive the same scaffold allocation and total trajectory budget.")
        children, provenance = [], _script_provenance([descriptor_path] + label_files)
        for index, (path, label, budget) in enumerate(zip(campaigns, labels, budgets)):
            child = Path(path).resolve()
            if child.parent != workspace or child == output:
                raise StudioError("Every engine campaign must belong to the same workspace.")
            manifest = load_json(child / "studio_run.json")
            if Path(manifest.get("engineBatchRoot", "")).resolve() != output:
                raise StudioError("An engine campaign belongs to a different batch.")
            if version == 2:
                form = manifest.get("request", {})
                identity = form.get("designPredictor")
                if identity == "intellifold" and form.get("intellifoldModel") == "v2":
                    identity = "intellifold_full"
                if (form.get("designType") != "nanobody" or form.get("scaffoldID") != scaffold_ids[index]
                        or identity != engine_ids[index] or form.get("numDesigns") != budget
                        or manifest.get("requestedTrajectories") != budget):
                    raise StudioError("The campaign does not match its saved scaffold, engine or trajectory allocation.")
            planned = desktop_plan({"project": project, "workflow": "iterative", "output": str(child)})
            command = planned["normalized_request"]["steps"][0]["command"]
            if command.count("--num-runs") != 1 or command[command.index("--num-runs") + 1] != str(budget):
                raise StudioError("Every campaign must receive its exact recorded trajectory budget.")
            children.append({**planned["normalized_request"], "label": label})
            provenance.extend(planned["provenance"])
        normalized = {"workflow": workflow, "output": str(output), "engine_campaigns": children, "display_name": display_name,
                      "child_outputs": [child["output"] for child in children]}
        # All children are preflighted before a worker can be submitted.
        return _persist("desktop_iterative_batch", project, normalized,
                        children[0]["steps"][0]["command"], "apple_gpu_exclusive",
                        list({item["path"]: item for item in provenance}.values()))
    elif workflow == "iterative":
        manifest = load_json(output / "studio_run.json")
        snapshot = Path(manifest.get("pipelineSnapshot", "")).resolve()
        if output not in snapshot.parents:
            raise StudioError("The iterative pipeline snapshot must belong to this campaign.")
        arguments = manifest.get("arguments")
        if not isinstance(arguments, list) or not all(isinstance(v, str) for v in arguments):
            raise StudioError("The recorded iterative command is unreadable.")
        # A GUI regression emitted resident for OpenFold-3, which has no such
        # worker. Reject the whole batch at preflight, before any engine runs.
        if ("--predictor" in arguments and "--design-scheduler" in arguments
                and arguments[arguments.index("--predictor") + 1:][:1] == ["openfold-3-mlx"]
                and arguments[arguments.index("--design-scheduler") + 1:][:1] in (["resident"], ["campaign-resident"])):
            raise StudioError("OpenFold-3 has no resident worker. Recreate the unfinished OpenFold-3 run with --design-scheduler run; the saved plan cannot be changed in place.")
        # Exact GUI argv is retained, including MSA and resident scheduling.
        for flag in ("--template-yaml", "--target-template"):
            if flag in arguments:
                inputs.append(Path(arguments[arguments.index(flag) + 1]))
        if "--out-root" not in arguments or "--run-name" not in arguments:
            raise StudioError("The recorded command has no output destination.")
        destination = Path(arguments[arguments.index("--out-root") + 1]) / arguments[arguments.index("--run-name") + 1]
        if destination.resolve() != output:
            raise StudioError("The recorded command points to a different campaign.")
        if "--resume" not in arguments:
            arguments = arguments + ["--resume"]
        environment = manifest.get("environmentOverrides") or {}
        stable_environment(environment)  # validate the same restricted overrides
        scripts = [snapshot / "nanohunter_run.sh"] + sorted((snapshot / "scripts").rglob("*.py"))
        steps = [{"command": ["/usr/bin/caffeinate", "-dimsu", str(scripts[0])] + arguments,
                  "cwd": str(snapshot), "stage": "iterative-design"}]
        context = {"pipeline_snapshot": str(snapshot), "manifest": manifest}
        form = manifest.get("request", {})
        if form.get("targetKind") == "ligand" and (form.get("nesso") or {}).get("enabled"):
            from .ligand_screening import prepare
            step, assets = prepare(root, output, workflow, form["nesso"], form.get("targetSmiles"))
            steps.append(step); inputs += assets

    elif workflow in {"nise", "nise_branch_test"}:
        from .nise import contract as load_contract
        config = output / "nise_config.json"
        settings = load_json(config)
        if Path(settings.get("output", "")).resolve() != output:
            raise StudioError("The NISE settings point to a different campaign.")
        snapshot = output / ".studio_runtime/pipeline"
        contract_path = snapshot / "scripts/nise/contract.py"
        if not contract_path.is_file():
            raise StudioError("The NISE pipeline snapshot is missing.")
        contract = load_contract()
        try:
            normalized_request = contract.preflight(root, contract.saved_request(settings.get("request")))
        except ValueError as exc:
            raise StudioError(str(exc)) from exc
        scripts = sorted((snapshot / "scripts").rglob("*.py"))
        # All model bytes remain in the managed installation; plans fingerprint
        # them and the executed engine code without copying or shipping weights.
        inputs = [config] + contract.required_files(root, normalized_request)
        inputs += sorted(p for p in (snapshot / "scripts/nise/nesso_assets").glob("*") if p.is_file())
        inputs += sorted((root / "src/LASErMPNN").rglob("*.py"))
        inputs += sorted((root / "venvs/NanoHunter_boltz/lib").glob("python*/site-packages/boltz/**/*.py"))
        if normalized_request["backbone_method"] == "rfdiffusion3":
            scripts += sorted((root / "rfd3/scripts").rglob("*.py"))
            scripts += sorted((root / "rfd3/mlx_port").rglob("*.py"))
            scripts += sorted((root / "rfd3").glob("*.py"))
            inputs += sorted((root / "rfd3/.venv/lib").glob("python*/site-packages/rfd3/**/*.py"))
            inputs += sorted((root / "rfd3/.venv/lib").glob("python*/site-packages/atomworks/**/*.py"))
        steps = [{"command": ["/usr/bin/caffeinate", "-dimsu",
                              str(root / "venvs/NanoHunter_boltz/bin/python"),
                              str(snapshot / "scripts/nise/campaign.py"), "--config", str(config), "--resume"],
                  "cwd": str(snapshot), "stage": "nise"}]
        context = {"pipeline_snapshot": str(snapshot), "request": normalized_request,
                   "prediction_budget": contract.prediction_budget(normalized_request)}
        if workflow == "nise_branch_test":
            import importlib.util
            spec = importlib.util.spec_from_file_location("studio_nise_branch_test", snapshot / "scripts/nise/branch_test.py")
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            try:
                assets = module.validate(output, normalized_request, settings.get("branch_test"))
            except (ValueError, OSError, KeyError) as exc:
                raise StudioError(str(exc)) from exc
            inputs += assets
            steps[0]["command"].append("--branch-test")
            steps[0]["stage"] = "partial-noising-validation"
            context["branch_test"] = settings["branch_test"]
            context["prediction_budget"] = {
                "maximum_structure_predictions": normalized_request["noise_predictions"] + normalized_request["noise_mpnn_seqs"],
                "masked_predictions": normalized_request["noise_predictions"],
                "repair_predictions": normalized_request["noise_mpnn_seqs"],
                "initial_generation": 0, "ordinary_mpnn": 0,
                "interpretation": "One imported parent; branch integration test, not a full campaign"}
        elif "branch_test" in settings:
            raise StudioError("Use the explicit nise_branch_test workflow for a branch-test request.")
    elif workflow in {"prediction", "target_prepare"}:
        config = output / "prediction_config.json"
        settings = load_json(config)
        if Path(settings.get("output", "")).resolve() != output:
            raise StudioError("The prediction settings point to a different output folder.")
        inputs = [config]
        if settings.get("template") is not None:
            import importlib.util
            path = root / "scripts/prediction_templates.py"
            spec = importlib.util.spec_from_file_location("studio_prediction_templates", path)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            try:
                module.validate(settings)
            except ValueError as exc:
                raise StudioError(str(exc)) from exc
            inputs += [Path(settings["template"]["path"])] + sorted((root / "scripts").glob("*.py"))
        for item in settings.get("jobs", []):
            for chain in item.get("chains", []):
                msa = chain.get("msa", "auto")
                if msa and msa.lower() not in {"auto", "empty"}:
                    inputs.append(Path(msa))
        scripts = [root / "rfd3_scripts/predict_batch.py"] + sorted((root / "rfd3_scripts").rglob("*.py"))
        steps = [{"command": ["/usr/bin/caffeinate", "-dimsu", "/usr/bin/python3",
                              str(root / "rfd3_scripts/predict_batch.py"), "--config", str(config)],
                  "cwd": str(root), "stage": "prediction"}]
    elif workflow == "rfdiffusion3":
        source = output / "config/studio_request.json"
        settings = load_json(source)
        if Path(settings.get("campaign_dir", "")).resolve() != output:
            raise StudioError("The RFdiffusion3 settings point to a different campaign.")
        protein = settings.get("target_kind") == "protein"
        if (settings.get("nesso") or {}).get("enabled"):
            if protein:
                raise StudioError("NESSO screening requires a small-molecule target.")
            from .ligand_screening import prepare
            _, assets = prepare(root, output, workflow, settings["nesso"], settings.get("smiles"))
            inputs += assets

        runner = root / "rfd3_scripts/rfd3_protein_campaign.py" if protein else root / "rfd3/scripts/run_rfd3_nise_campaign.py"
        python = root / "rfd3/.venv/bin/python"
        inputs += [source]
        # Target structures and ligand files referenced by the native request
        # are also frozen, so an edit while queued cannot change this run.
        for key in ("target_pdb", "target_structure", "target_structure_path", "ligand_pdb", "ligand_structure", "motif_pdb", "origins_file"):
            if settings.get(key):
                inputs.append(Path(settings[key]))
        inputs += [Path(item["path"]) for item in settings.get("conformers", []) if item.get("path")]
        scripts = [root / "rfd3_scripts/prepare_campaign.py", runner] + rfd3_runtime_scripts(root)
        steps = [
            {"command": [str(python), str(root / "rfd3_scripts/prepare_campaign.py"), str(source)],
             "cwd": str(root / "rfd3"), "stage": "prepare"},
            {"command": ["/usr/bin/caffeinate", "-dimsu", str(python), str(runner),
                         "--config", str(output / "config/campaign.json"), "--resume"],
             "cwd": str(root / "rfd3"), "stage": "rfd3"},
        ]
    else:
        raise StudioError("Unknown native workflow.")
    normalized = {"output": str(output), "workflow": workflow, "steps": steps, "display_name": display_name,
                  "environment_overrides": environment, **context}
    return _persist("desktop_" + workflow, project, normalized,
                    steps[0]["command"], "apple_gpu_exclusive",
                    _script_provenance(list(dict.fromkeys(scripts + inputs + label_files))))
