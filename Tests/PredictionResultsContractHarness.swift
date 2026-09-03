import Foundation

// RunResult.swift only needs this enum from the history layer. Keeping the
// harness focused avoids pulling ObservableObject/AppState into a file-layout
// contract test.
enum StudioWorkflow: String, Codable {
    case iterative, rfdiffusion3, prediction
    var label: String { rawValue }
}

@main
struct PredictionResultsContractHarness {
    static func main() throws {
        if CommandLine.arguments.count == 3, CommandLine.arguments[1] == "iterative" {
            let root = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
            let results = RunResultsLoader.load(root: root, workflow: .iterative)
            let groups = RunResultsLoader.groups(from: results)
            let hits = groups.filter { $0.isHit == true }
            let completeComparisons = groups.filter { group in
                let roles = Set(group.items.map(\.artifactRole))
                return roles.contains(.designedComplex)
                    && roles.contains(.complexReprediction)
                    && roles.contains(.binderAlone)
            }
            print("ITERATIVE_RESULTS|groups=\(groups.count)|artifacts=\(results.count)|hits=\(hits.count)|complete_comparisons=\(completeComparisons.count)")
            guard hits.count == 1,
                  hits.first?.id == "iterative|12|5",
                  completeComparisons.count > 0 else {
                throw NSError(domain: "PredictionResultsContract", code: 10,
                              userInfo: [NSLocalizedDescriptionKey:
                                "Moved iterative campaign did not preserve the saved hit and related structure groups"])
            }
            return
        }
        if CommandLine.arguments.count == 2 {
            let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
            let results = RunResultsLoader.load(root: root, workflow: .rfdiffusion3)
            let backbones = results.filter { $0.stage == .generatedBackbone }.count
            let complexes = results.filter { $0.subtitle.hasPrefix("Complex with ") }.count
            let binders = results.filter { $0.subtitle.hasPrefix("Binder alone ·") }.count
            let groups = RunResultsLoader.groups(from: results)
            let compared = groups.filter { group in
                let roles = Set(group.items.map(\.artifactRole))
                return roles.contains(.generatedBackbone)
                    && roles.contains(.complexReprediction)
                    && roles.contains(.binderAlone)
            }.count
            let sources = Set(results.map(\.scoreSource)).sorted().joined(separator: ", ")
            print("RFD3_RESULTS|groups=\(groups.count)|total=\(results.count)|backbones=\(backbones)|complexes=\(complexes)|binders=\(binders)|complete_comparisons=\(compared)|sources=\(sources)")
            guard backbones > 0, complexes > 0, binders > 0,
                  compared > 0,
                  !results.contains(where: { $0.scoreSource == "Prediction" }) else {
                throw NSError(domain: "PredictionResultsContract", code: 9,
                              userInfo: [NSLocalizedDescriptionKey:
                                "Real campaign did not expose backbone, complex, binder-alone and exact engine provenance"])
            }
            return
        }
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
        let startRoot = iterative.appendingPathComponent("run_001/cycle_00", isDirectory: true)
        let designRoot = iterative.appendingPathComponent("run_001/cycle_01", isDirectory: true)
        let postRoot = iterative.appendingPathComponent("run_001/post_intellifold/cycle_01", isDirectory: true)
        let binderRoot = postRoot.appendingPathComponent("binder_alone", isDirectory: true)
        try fm.createDirectory(at: startRoot, withIntermediateDirectories: true)
        try fm.createDirectory(at: designRoot, withIntermediateDirectories: true)
        try fm.createDirectory(at: postRoot, withIntermediateDirectories: true)
        try fm.createDirectory(at: binderRoot, withIntermediateDirectories: true)
        let startStructure = startRoot.appendingPathComponent("model.cif")
        let designStructure = designRoot.appendingPathComponent("model.cif")
        let postStructure = postRoot.appendingPathComponent("model.cif")
        let binderStructure = binderRoot.appendingPathComponent("model.cif")
        try "data_start\n".write(to: startStructure, atomically: true, encoding: .utf8)
        try "data_design\n".write(to: designStructure, atomically: true, encoding: .utf8)
        try "data_post\n".write(to: postStructure, atomically: true, encoding: .utf8)
        try "data_binder\n".write(to: binderStructure, atomically: true, encoding: .utf8)
        try "cycle,iptm,complex_plddt,confidence_json,structure_path,binder_sequence\n0,0.40,0.50,,\(startStructure.path),AAAA\n1,0.81,0.77,,\(designStructure.path),AAAA\n"
            .write(to: iterative.appendingPathComponent("run_001/metrics_per_cycle.csv"),
                   atomically: true, encoding: .utf8)
        let movedPrefix = "/a/different/mac/\(iterative.lastPathComponent)"
        try "run,cycle,predictor,iptm,ipsae_min,complex_plddt,binder_plddt,complex_rmsd,binder_backbone_rmsd,binder_rmsd,binder_sequence,structure_path,confidence_json,binder_structure_path,binder_confidence_json,is_hit,failed_filters\n1,1,intellifold,0.84,0.71,0.82,0.91,1.40,0.70,1.20,AAAA,\(movedPrefix)/run_001/post_intellifold/cycle_01/model.cif,,\(movedPrefix)/run_001/post_intellifold/cycle_01/binder_alone/model.cif,,True,\n"
            .write(to: postRoot.appendingPathComponent("post_metrics_row.csv"),
                   atomically: true, encoding: .utf8)
        let manifest = ["arguments": ["--predictor", "protenix-v2", "--iptm-threshold", "0.75"]]
        try JSONSerialization.data(withJSONObject: manifest).write(
            to: iterative.appendingPathComponent("studio_run.json"))

        let partial = RunResultsLoader.load(root: iterative, workflow: .iterative)
        guard partial.count == 4,
              partial.filter({ $0.stage == .startingStructure }).count == 1,
              partial.contains(where: { $0.stage == .design && $0.scoreSource == "Protenix v2" }),
              partial.contains(where: { $0.artifactRole == .complexReprediction && $0.scoreSource == "IntelliFold PyTorch" }),
              partial.contains(where: { $0.artifactRole == .binderAlone && $0.structureURL == binderStructure }) else {
            throw NSError(domain: "PredictionResultsContract", code: 6,
                          userInfo: [NSLocalizedDescriptionKey:
                            "Interrupted iterative checkpoints lost result or score provenance: \(partial.map { "\($0.stage.rawValue):\($0.scoreSource)" })"])
        }
        let grouped = RunResultsLoader.groups(from: partial)
        guard grouped.count == 2,
              grouped.first(where: { $0.id == "iterative|1|1" })?.items.count == 3,
              grouped.first(where: { $0.id == "iterative|1|1" })?.isHit == true else {
            throw NSError(domain: "PredictionResultsContract", code: 8,
                          userInfo: [NSLocalizedDescriptionKey:
                            "Related iterative structures were not grouped under the saved hit verdict"])
        }
        guard abs(RunResultsLoader.iterativeHitThreshold(root: iterative) - 0.75) < 1e-12 else {
            throw NSError(domain: "PredictionResultsContract", code: 7,
                          userInfo: [NSLocalizedDescriptionKey: "Recorded iterative hit threshold was not restored"])
        }

        // A completed ligand RFdiffusion3 campaign historically wrote only
        // the holo path to top100_manifest.json even though apo folds existed.
        // The browser must recover all three scientific artifacts and the
        // implicit Boltz provenance from the durable checkpoint tables.
        let rfd3 = fm.temporaryDirectory
            .appendingPathComponent("rfd3-results-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: rfd3) }
        for relative in ["rfd3/backbones", "predictions/holo", "predictions/apo",
                         "analysis", "config"] {
            try fm.createDirectory(at: rfd3.appendingPathComponent(relative),
                                   withIntermediateDirectories: true)
        }
        let backbone = rfd3.appendingPathComponent("rfd3/backbones/design_0001.pdb")
        let holo = rfd3.appendingPathComponent("predictions/holo/design_0001_0.pdb")
        let apo = rfd3.appendingPathComponent("predictions/apo/design_0001_0.pdb")
        for structure in [backbone, holo, apo] {
            try "ATOM\n".write(to: structure, atomically: true, encoding: .utf8)
        }
        try "design,backbone_pdb,ca_valid_pct\ndesign_0001,\(backbone.path),100\n"
            .write(to: rfd3.appendingPathComponent("rfd3/backbone_metrics.csv"),
                   atomically: true, encoding: .utf8)
        try "design,name,ok,pdb,complex_plddt,iptm\ndesign_0001,design_0001_0,True,\(holo.path),0.91,0.82\n"
            .write(to: rfd3.appendingPathComponent("predictions/holo/prediction_metrics.csv"),
                   atomically: true, encoding: .utf8)
        try "design,name,ok,pdb,complex_plddt,iptm\ndesign_0001,design_0001_0,True,\(apo.path),0.88,0\n"
            .write(to: rfd3.appendingPathComponent("predictions/apo/prediction_metrics.csv"),
                   atomically: true, encoding: .utf8)
        try "design,name,holo_vs_apo_ca_rmsd\ndesign_0001,design_0001_0,1.25\n"
            .write(to: rfd3.appendingPathComponent("analysis/rmsd_metrics.csv"),
                   atomically: true, encoding: .utf8)
        let ranked: [[String: Any]] = [[
            "design": "design_0001", "name": "design_0001_0",
            "sequence": "AAAA", "pdb": holo.path, "iptm": 0.82, "score": 0.9,
        ]]
        try JSONSerialization.data(withJSONObject: ranked).write(
            to: rfd3.appendingPathComponent("analysis/top100_manifest.json"))
        try JSONSerialization.data(withJSONObject: ["target_kind": "small_molecule"]).write(
            to: rfd3.appendingPathComponent("config/campaign.json"))

        let rfd3Results = RunResultsLoader.load(root: rfd3, workflow: .rfdiffusion3)
        guard rfd3Results.count == 3,
              rfd3Results.contains(where: { $0.stage == .generatedBackbone
                  && $0.scoreSource == "RFdiffusion3 MLX" }),
              rfd3Results.contains(where: { $0.subtitle == "Complex with ligand · Boltz-2" }),
              rfd3Results.contains(where: { $0.subtitle == "Binder alone · Boltz-2"
                  && $0.metrics.contains { $0.kind == .binderPLDDT && abs($0.value - 0.88) < 1e-12 }
                  && $0.metrics.contains { $0.kind == .binderRMSD && abs($0.value - 1.25) < 1e-12 } }) else {
            throw NSError(domain: "PredictionResultsContract", code: 8,
                          userInfo: [NSLocalizedDescriptionKey:
                            "RFD3 browser lost backbone/holo/apo artifacts or provenance: \(rfd3Results.map { "\($0.subtitle):\($0.scoreSource):\($0.metrics)" })"])
        }
        print("PASS prediction result discovery contract")
    }
}
