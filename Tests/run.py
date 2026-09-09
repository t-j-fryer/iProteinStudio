#!/usr/bin/env python3
"""One explicit test entry point. Each Python file runs as a script, never just an import."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FAST_PYTHON = [
    "test_apple_build_tools.py", "test_install_download_recovery.py",
    "test_iterative_engine_batch.py",
    "test_nanobody_scaffold_catalog.py",
    "test_nise_contract.py", "test_rfd3_batch_resume.py",
    "test_nesso_screen.py",
    "test_initialization_refinement.py",
    "test_secondary_structure_control.py", "test_design_cardinality.py",
    "test_runtime_transaction.py", "test_storage_policy.py", "test_mcp_bridge.py",
    "test_desktop_jobs.py", "test_vendor_pipeline.py", "test_verified_downloader.py",
    "test_prediction_engine_safety.py", "test_prediction_msa_reliability.py",
    "test_installer_lock_contract.py", "test_managed_storage.py",
    "test_rfd3_predictor_scheduling.py", "test_rfd3_weight_provenance.py",
]
FAST_SHELL = [
    "test_apple_build_tools_ui.sh",
    "test_iterative_cli_contract.sh", "test_iterative_results_ui_contract.sh",
    "test_rfd3_results_ui_contract.sh", "test_ai_integrations_ui_contract.sh",
    "test_unsigned_beta_release_contract.sh", "test_update_release_contract.sh",
    "test_process_runner_cancellation.sh", "test_workspace_organization.sh", "test_pipeline_snapshot.sh",
]
SCIENCE = [
    "test_prediction_templates.py", "test_ligand_screening.py",
    "test_nise_science.py", "test_nise_rfd3.py",
    "test_monomer_initialization_pipeline.py",
    "test_workflow_pipelines.py", "test_rfd3_partial_validation.py", "test_rfd3_motif_scoring.py",
    "test_rfd3_worked_examples.py", "test_rfd3_surface_origins.py", "test_rfd3_target_export.py",
    "test_acbx_example_integrity.py", "test_ligand_conditioning.py",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=["fast", "science", "all"], default="fast")
    parser.add_argument("--science-python", type=Path)
    parser.add_argument("--scratch-path", type=Path, default=ROOT / ".build")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.suite != "fast" and not args.science_python:
        parser.error("science/all requires --science-python pointing to a prepared test environment; no engine is installed automatically")
    commands = []
    if args.suite in {"fast", "all"}:
        commands += [[sys.executable, "Tests/" + name] for name in FAST_PYTHON]
        commands += [["bash", "Tests/" + name] for name in FAST_SHELL]
        commands += [["swift", "test", "--scratch-path", str(args.scratch_path)]]
        commands += [[sys.executable, "Tests/run_swift_contracts.py"]]
    if args.suite in {"science", "all"}:
        commands += [[str(args.science_python), "Tests/" + name] for name in SCIENCE]
    if args.list:
        print(json.dumps(commands, indent=2)); return 0
    environment = dict(os.environ)
    cache = Path(tempfile.gettempdir()) / "iproteinstudio-test-modules"
    cache.mkdir(exist_ok=True)
    environment.setdefault("CLANG_MODULE_CACHE_PATH", str(cache))
    environment.setdefault("SWIFTPM_MODULECACHE_OVERRIDE", str(cache))
    environment.setdefault("SWIFT_MODULECACHE_PATH", str(cache))
    results = []
    for command in commands:
        label = " ".join(command)
        print("RUN " + label, flush=True)
        result = subprocess.run(command, cwd=ROOT, env=environment)
        results.append({"command": command, "passed": result.returncode == 0})
    omitted = ["Live network ligand acceptance", "Real-model inference campaigns", "Interactive VoiceOver/GUI acceptance", "Packaged app/Gatekeeper/Sparkle acceptance"]
    if args.suite == "fast": omitted.append("Science fixture suite (use --suite all --science-python PATH)")
    print(json.dumps({"passed": sum(r["passed"] for r in results), "total": len(results),
                      "failed": [r["command"] for r in results if not r["passed"]],
                      "not_run": omitted}, indent=2))
    return int(any(not result["passed"] for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
