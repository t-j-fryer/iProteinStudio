import Foundation

// RunResult.swift only needs this enum from the history layer. Keeping the
// harness focused avoids pulling ObservableObject/AppState into a file-layout
// contract test.
enum StudioWorkflow: String {
    case iterative, rfdiffusion3, prediction
}

@main
struct PredictionResultsContractHarness {
    static func main() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("prediction-results-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let output = root.appendingPathComponent("intellifold-jax/bucket_128/chunk_0")
        let native = output.appendingPathComponent("intellifold_jax/Cobratoxin")
        let aggregate = native.appendingPathComponent("Cobratoxin_model.cif")
        let sample0 = native.appendingPathComponent("seed-42_sample-0/Cobratoxin_seed-42_sample-0_model.cif")
        let sample1 = native.appendingPathComponent("seed-42_sample-1/Cobratoxin_seed-42_sample-1_model.cif")
        let normalized = output.appendingPathComponent("pred_min/model_0.cif")
        for path in [aggregate, sample0, sample1, normalized] {
            try fm.createDirectory(at: path.deletingLastPathComponent(),
                                   withIntermediateDirectories: true)
            try "data_test\n".write(to: path, atomically: true, encoding: .utf8)
        }
        for structure in [sample0, sample1] {
            let confidence = structure.deletingLastPathComponent()
                .appendingPathComponent("confidence.json")
            try "{\"iptm\":0.7,\"ipsae_min\":0.55}\n"
                .write(to: confidence, atomically: true, encoding: .utf8)
        }
        try "job,predictor,bucket,exit_code,output\nCobratoxin,intellifold-jax,128,0,\(output.path)\n"
            .write(to: root.appendingPathComponent("predictions.csv"), atomically: true,
                   encoding: .utf8)
        let config: [String: Any] = ["jobs": [[
            "name": "Cobratoxin",
            "chains": [["id": "A", "kind": "protein", "sequence": "ACDEFG"]],
        ]]]
        try JSONSerialization.data(withJSONObject: config).write(
            to: root.appendingPathComponent("prediction_config.json"))

        let results = RunResultsLoader.load(root: root, workflow: .prediction)
        guard results.count == 2 else {
            throw NSError(domain: "PredictionResultsContract", code: 1,
                          userInfo: [NSLocalizedDescriptionKey:
                            "Expected two native stochastic outputs, got \(results.map(\.structureURL.path))"])
        }
        let foundPaths = Set(results.map { $0.structureURL.standardizedFileURL.path })
        let expectedPaths = Set([sample0, sample1].map { $0.standardizedFileURL.path })
        guard foundPaths == expectedPaths else {
            throw NSError(domain: "PredictionResultsContract", code: 2,
                          userInfo: [NSLocalizedDescriptionKey:
                            "Aggregate/normalized copies displaced native samples: \(results.map(\.structureURL.path))"])
        }
        guard results.allSatisfy({ $0.title.contains("seed 42") }) else {
            throw NSError(domain: "PredictionResultsContract", code: 3,
                          userInfo: [NSLocalizedDescriptionKey: "Sample identities are not visible"])
        }
        guard results.allSatisfy({ $0.subtitle.contains("retired") }) else {
            throw NSError(domain: "PredictionResultsContract", code: 4,
                          userInfo: [NSLocalizedDescriptionKey:
                            "Historical JAX results were not clearly labelled retired"])
        }
        guard results.allSatisfy({ item in
            item.metrics.contains { $0.kind == .ipsaeMinimum && abs($0.value - 0.55) < 1e-12 }
        }) else {
            throw NSError(domain: "PredictionResultsContract", code: 5,
                          userInfo: [NSLocalizedDescriptionKey:
                            "ipSAE(min) was not shown from saved confidence JSON"])
        }


        // An interrupted iterative campaign has no final comparison table yet.
        // Its per-cycle design and checker checkpoints must still reopen with
        // the engine that actually emitted each score.
        let iterative = fm.temporaryDirectory
            .appendingPathComponent("iterative-results-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: iterative) }
        let designRoot = iterative.appendingPathComponent("run_001/cycle_01", isDirectory: true)
        let postRoot = iterative.appendingPathComponent("run_001/post_intellifold/cycle_01", isDirectory: true)
        try fm.createDirectory(at: designRoot, withIntermediateDirectories: true)
        try fm.createDirectory(at: postRoot, withIntermediateDirectories: true)
        let designStructure = designRoot.appendingPathComponent("model.cif")
        let postStructure = postRoot.appendingPathComponent("model.cif")
        try "data_design\n".write(to: designStructure, atomically: true, encoding: .utf8)
        try "data_post\n".write(to: postStructure, atomically: true, encoding: .utf8)
        try "cycle,iptm,complex_plddt,confidence_json,structure_path,binder_sequence\n1,0.81,0.77,,\(designStructure.path),AAAA\n"
            .write(to: iterative.appendingPathComponent("run_001/metrics_per_cycle.csv"),
                   atomically: true, encoding: .utf8)
        try "run,cycle,iptm,complex_plddt,binder_sequence,structure_path,confidence_json\n1,1,0.74,0.72,AAAA,\(postStructure.path),\n"
            .write(to: postRoot.appendingPathComponent("post_metrics_row.csv"),
                   atomically: true, encoding: .utf8)
        let manifest = ["arguments": ["--predictor", "protenix-v2", "--iptm-threshold", "0.75"]]
        try JSONSerialization.data(withJSONObject: manifest).write(
            to: iterative.appendingPathComponent("studio_run.json"))

        let partial = RunResultsLoader.load(root: iterative, workflow: .iterative)
        guard partial.count == 2,
              partial.contains(where: { $0.stage == .design && $0.scoreSource == "Protenix v2" }),
              partial.contains(where: { $0.stage == .postPrediction && $0.scoreSource == "IntelliFold PyTorch" }) else {
            throw NSError(domain: "PredictionResultsContract", code: 6,
                          userInfo: [NSLocalizedDescriptionKey:
                            "Interrupted iterative checkpoints lost result or score provenance: \(partial.map { "\($0.stage.rawValue):\($0.scoreSource)" })"])
        }
        guard abs(RunResultsLoader.iterativeHitThreshold(root: iterative) - 0.75) < 1e-12 else {
            throw NSError(domain: "PredictionResultsContract", code: 7,
                          userInfo: [NSLocalizedDescriptionKey: "Recorded iterative hit threshold was not restored"])
        }
        print("PASS prediction result discovery contract")
    }
}
