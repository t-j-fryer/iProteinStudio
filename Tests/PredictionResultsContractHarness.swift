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
        print("PASS prediction result discovery contract")
    }
}
