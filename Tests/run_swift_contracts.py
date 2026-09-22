#!/usr/bin/env python3
"""Compile and execute the existing pure Swift request/result harnesses."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "Sources/iProteinStudio/"
MODELS = ["NumericInputValue.swift", "ProteinSequenceInput.swift", "Predictor.swift", "RFD3Request.swift", "DesignRequest.swift", "DesignEngine.swift", "DesignPoint.swift", "RunResult.swift"]
with tempfile.TemporaryDirectory(prefix="studio-swift-contracts-") as raw:
    tmp = Path(raw)
    flags = ["swiftc", "-module-cache-path", str(tmp / "modules")]
    if os.environ.get("SDKROOT"):
        flags += ["-sdk", os.environ["SDKROOT"]]
    cases = {
        "workflow_requests": [SOURCE + "Models/" + name for name in [
            "Predictor.swift", "ProteinSequenceInput.swift", "RFD3Request.swift", "PredictionRequest.swift"
        ]] + ["Tests/WorkflowRequestContractHarness.swift"],
        "engine_batch_controller": [SOURCE + "Models/" + name for name in MODELS] + [
            SOURCE + "Models/NISERequest.swift", SOURCE + "Models/PredictionRequest.swift",
            SOURCE + "Models/RunNaming.swift",
            SOURCE + "Core/NISEController.swift", SOURCE + "Core/PredictionController.swift",
            SOURCE + "Core/RFD3Controller.swift", SOURCE + "Core/ProcessRunner.swift",
            SOURCE + "Core/RunController.swift", SOURCE + "Core/RunHistoryStore.swift",
            SOURCE + "Core/TemplateWriter.swift", SOURCE + "Core/CommandBuilder.swift",
            SOURCE + "Core/CDRDetector.swift", SOURCE + "Core/ResumeContract.swift", "Tests/EngineBatchControllerHarness.swift"],
        "prediction_templates": [SOURCE + "Models/Predictor.swift", SOURCE + "Models/PredictionRequest.swift", "Tests/PredictionTemplateContractHarness.swift"],
        "nise": [SOURCE + "Models/" + name for name in ["NISERequest.swift", "WorkspaceOrganization.swift", "Project.swift"]] + ["Tests/NISERequestContractHarness.swift"],
        "core": [str(path.relative_to(ROOT)) for path in sorted((ROOT / "Sources/StudioCore").glob("*.swift"))] + ["Tests/StudioCoreContractHarness.swift"],
        "nise_results": ["Tests/NISEResultsContractHarness.swift", SOURCE + "Models/RunResult.swift", SOURCE + "Core/Results/NISEResults.swift"],
        "results": ["Tests/PredictionResultsContractHarness.swift", SOURCE + "Models/RunResult.swift", SOURCE + "Core/Results/RunResultsLoader.swift", SOURCE + "Core/Results/NISEResults.swift"],
        "iterative": [SOURCE + "Models/" + name for name in MODELS] + [
            SOURCE + "Core/ResumeContract.swift", SOURCE + "Core/TemplateWriter.swift", SOURCE + "Core/CommandBuilder.swift",
            SOURCE + "Core/MetricsWatcher.swift", SOURCE + "Core/Results/RunResultsLoader.swift", SOURCE + "Core/Results/NISEResults.swift", "Tests/IterativeCommandContractHarness.swift"],
    }
    for name, sources in cases.items():
        sources += [SOURCE + "Core/ControlPython.swift"]
        binary = tmp / name
        subprocess.run(flags + ["-parse-as-library"] + sources + ["-o", str(binary)], cwd=ROOT, check=True)
        subprocess.run([str(binary)], cwd=ROOT, check=True)
