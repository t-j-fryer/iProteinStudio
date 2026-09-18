import Foundation

// RunResult.swift only needs this enum from the history layer. Keeping the
// harness focused avoids pulling ObservableObject/AppState into a file-layout
// contract test.
enum StudioWorkflow: String, Codable {
    case iterative, nise, rfdiffusion3, prediction
    var label: String { rawValue }
}

@main
struct PredictionResultsContractHarness {
    static func main() throws {
        let csvRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: csvRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: csvRoot) }
        let malformed = csvRoot.appendingPathComponent("partial.csv")
        try "iptm,iptm\n0.8,0.9\n".write(to: malformed, atomically: true, encoding: .utf8)
        guard CSVTable.rows(at: malformed).isEmpty else { fatalError("duplicate CSV headers were accepted") }
        try "iptm,name\n0.8,complete\n0.9,\"unfinished".write(to: malformed, atomically: true, encoding: .utf8)
        guard CSVTable.rows(at: malformed).count == 1 else { fatalError("partial quoted CSV row was accepted") }

        let batch = csvRoot.appendingPathComponent("engine-batch-test")
        try FileManager.default.createDirectory(at: batch, withIntermediateDirectories: true)
        for name in ["framework-a", "framework-b"] {
            let child = csvRoot.appendingPathComponent(name)
            try FileManager.default.createDirectory(at: child, withIntermediateDirectories: true)
            try "data_fixture".write(to: child.appendingPathComponent("model.cif"), atomically: true, encoding: .utf8)
            try JSONSerialization.data(withJSONObject: ["request": ["scaffoldID": name, "designPredictor": "boltz", "numDesigns": 1]])
                .write(to: child.appendingPathComponent("studio_run.json"))
            try "run,cycle,stage,predictor,structure_path,iptm,is_hit\n1,0,design,boltz,model.cif,0.8,\n1,1,design,boltz,model.cif,0.9,\n1,1,post,boltz,model.cif,0.9,true\n"
                .write(to: child.appendingPathComponent("comparison_scores_long.csv"), atomically: true, encoding: .utf8)
        }
        try JSONSerialization.data(withJSONObject: ["campaigns": ["/old/workspace/framework-a", "/old/workspace/framework-b"],
            "engines": ["Boltz · Framework A", "Boltz · Framework B"]]).write(to: batch.appendingPathComponent("studio_engine_batch.json"))
        let combined = RunResultsLoader.load(root: batch, workflow: .iterative)
        precondition(combined.count == 6 && Set(combined.map(\.id)).count == 6)
        let combinedGroups = RunResultsLoader.groups(from: combined)
        precondition(combinedGroups.count == 2 && combinedGroups.allSatisfy { $0.iterativeTrajectoryItems.count == 2 })
        precondition(combined.filter { $0.frameworkID == "framework-a" }.count == 3)
        precondition(combined.allSatisfy { $0.designEngine == "boltz" && $0.campaignID != nil })
        // A later child refresh must preserve the earlier child's records and verdict.
        let again = RunResultsLoader.load(root: batch, workflow: .iterative)
        precondition(again == combined)
        if let archive = ProcessInfo.processInfo.environment["STUDIO_ARCHIVE_BATCH"] {
            let archived = RunResultsLoader.load(root: URL(fileURLWithPath: archive), workflow: .iterative)
            precondition(RunResultsLoader.groups(from: archived).count == 12)
            precondition(archived.filter { $0.stage == .design }.count == 60)
            precondition(archived.filter { $0.stage == .startingStructure }.count == 12)
            precondition(Set(archived.compactMap(\.frameworkID)).count == 8)
            print("PASS student archive: eight frameworks, 12 distinct trajectories, 60 optimized cycle outputs")
        }
        print("PASS combined batch relocation, framework identity, duplicate run numbers and trajectory playback")

        let shortlist = csvRoot.appendingPathComponent("nesso_verification")
        try FileManager.default.createDirectory(at: shortlist, withIntermediateDirectories: true)
        try "data_fixture".write(to: shortlist.appendingPathComponent("fold.cif"), atomically: true, encoding: .utf8)
        let screenRow: [String: Any] = ["candidate": "run_001_cycle_02", "structure": "fold.cif", "predictor": "intellifold", "intellifold_model": "v2",
            "sequence": "ACDE", "nesso": ["affinity_probability_binary": 0.8, "entropy_crop_pl": 0.2, "screening_score": 1.6],
            "structure_scores": ["iptm": 0.6]]
        try JSONSerialization.data(withJSONObject: [screenRow]).write(to: shortlist.appendingPathComponent("results.json"))
        for workflow in [StudioWorkflow.iterative, .rfdiffusion3] {
            let items = RunResultsLoader.load(root: csvRoot, workflow: workflow)
            precondition(items.count == 1 && items[0].isHit == nil)
            precondition(items[0].metrics.contains { $0.kind == .nessoInterfaceEntropy && $0.value == 0.2 })
            precondition(items[0].metrics.contains { $0.kind == .iptm && $0.value == 0.6 })
            precondition(!items[0].metrics.contains { $0.kind == .ligandPLDDT })
        }

        let nise = csvRoot.appendingPathComponent("nise")
        try FileManager.default.createDirectory(at: nise.appendingPathComponent("candidates"), withIntermediateDirectories: true)
        try "fixture".write(to: nise.appendingPathComponent("holo.pdb"), atomically: true, encoding: .utf8)
        try "fixture".write(to: nise.appendingPathComponent("apo.pdb"), atomically: true, encoding: .utf8)
        for name in ["c01_t0_n0_s0", "c01_t0_n0_s1"] {
            var row: [String: Any] = ["name": name, "pdb": "holo.pdb", "sequence": "ACDE", "trajectory": 0,
                                     "cycle": 1, "nesso": ["affinity_probability_binary": 0.73, "affinity_pred_value": -0.8], "passed": true, "pbind": 0.9, "ligand_plddt": 95.0]
            if name.hasSuffix("s1") {
                row["nesso"] = ["affinity_probability_binary": 0.73, "affinity_pred_value": -0.8,
                                "entropy_pl": 0.2, "screening_score": 1.53]
            }
            try JSONSerialization.data(withJSONObject: row).write(to: nise.appendingPathComponent("candidates/\(name).json"))
        }
        let analysis: [String: Any] = ["ranked": [["name": "c01_t0_n0_s0", "apo_pdb": "apo.pdb", "preorg_rmsd": 0.75, "combined_score": 2.2]]]
        try JSONSerialization.data(withJSONObject: analysis).write(to: nise.appendingPathComponent("preorg.json"))
        let niseItems = RunResultsLoader.load(root: nise, workflow: .nise)
        let niseGroups = RunResultsLoader.groups(from: niseItems)
        precondition(niseItems.count == 3 && niseGroups.count == 1 && niseGroups[0].variants.count == 2)
        precondition(niseItems.allSatisfy { $0.isHit == nil })
        precondition(niseItems.contains { $0.metrics.contains { $0.kind == .nessoBindingProbability && $0.value == 0.73 } })
        precondition(niseItems.filter { $0.metrics.contains { $0.kind == .nessoScreeningScore && $0.value == 1.53 } }.count == 1)
        precondition(niseItems.filter { $0.metrics.contains { $0.kind == .nessoPlacementEntropy && $0.value == 0.2 } }.count == 1)

        precondition(niseItems.first(where: { $0.artifactRole == .binderAlone })?.metrics.contains(where: { $0.kind == .pocketPreorgRMSD }) == true)
        precondition(niseItems.first(where: { $0.artifactRole == .designedComplex })?.metrics.contains(where: { $0.kind == .ligandPLDDT }) == true)
        let skipped: [String: Any] = ["name": "skipped", "trajectory": 0, "cycle": 1,
            "pdb": "holo.pdb", "sequence": "AAA", "passed": false, "geometry_passed": true,
            "score_status": "score_upper_bound_below_selection_boundary", "score": NSNull()]
        try JSONSerialization.data(withJSONObject: skipped).write(to: nise.appendingPathComponent("candidates/skipped.json"))
        let skippedItem = RunResultsLoader.load(root: nise, workflow: .nise).first { $0.title == "skipped" }!
        precondition(skippedItem.subtitle.contains("Affinity skipped"))
        precondition(!skippedItem.metrics.contains { $0.kind == .rankingScore })

        let masked: [String: Any] = ["name": "masked", "trajectory": 0, "cycle": 2,
            "pdb": "holo.pdb", "sequence": "AXA", "passed": false, "geometry_passed": true,
            "branch": "masked-backbone", "score_status": "scored", "score": 1.99]
        try JSONSerialization.data(withJSONObject: masked).write(to: nise.appendingPathComponent("candidates/masked.json"))
        let maskedItem = RunResultsLoader.load(root: nise, workflow: .nise).first { $0.title == "masked" }!
        precondition(maskedItem.subtitle.contains("Masked backbone · intermediate"))
        precondition(maskedItem.isHit == nil)

        if CommandLine.arguments.count == 3, CommandLine.arguments[1] == "iterative" {
            let root = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
            let results = RunResultsLoader.load(root: root, workflow: .iterative)
            let groups = RunResultsLoader.groups(from: results)
            let variants = groups.flatMap(\.variants)
            let hits = variants.filter { $0.isHit == true }
            let completeComparisons = variants.filter { variant in
                let roles = Set(variant.items.map(\.artifactRole))
                return roles.contains(.designedComplex)
                    && roles.contains(.complexReprediction)
                    && roles.contains(.binderAlone)
            }
            let trajectories = groups.filter { $0.iterativeTrajectoryItems.count > 1 }
            print("ITERATIVE_RESULTS|runs=\(groups.count)|cycles=\(variants.count)|artifacts=\(results.count)|hits=\(hits.count)|complete_comparisons=\(completeComparisons.count)|trajectories=\(trajectories.count)")
            guard hits.count == 1,
                  groups.first(where: { $0.id == "iterative|12" })?.variants
                    .contains(where: { $0.id == "cycle|5" && $0.isHit == true }) == true,
                  completeComparisons.count > 0,
                  trajectories.count == groups.count,
                  trajectories.allSatisfy({ $0.iterativeTrajectoryItems.count == 6 }) else {
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
            let variants = groups.flatMap(\.variants)
            let compared = variants.filter { variant in
                let roles = Set(variant.items.map(\.artifactRole))
                return roles.contains(.complexReprediction)
                    && roles.contains(.binderAlone)
            }.count
            let correctlyNested = groups.filter { !$0.variants.isEmpty }.allSatisfy { group in
                group.primaryItems.contains { $0.artifactRole == .generatedBackbone }
            }
            let sources = Set(results.map(\.scoreSource)).sorted().joined(separator: ", ")
            print("RFD3_RESULTS|backbone_groups=\(groups.count)|derivatives=\(variants.count)|total=\(results.count)|backbones=\(backbones)|complexes=\(complexes)|binders=\(binders)|complete_comparisons=\(compared)|sources=\(sources)")
            guard backbones > 0, complexes > 0, binders > 0,
                  compared > 0, correctlyNested,
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
        guard grouped.count == 1,
              grouped.first?.variants.count == 2,
              grouped.first?.iterativeTrajectoryItems.map(\.variantID) == ["cycle|0", "cycle|1"],
              grouped.first?.variants.first(where: { $0.id == "cycle|1" })?.items.count == 3,
              grouped.first?.variants.first(where: { $0.id == "cycle|1" })?.isHit == true else {
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
        for relative in ["rfd3/backbones", "mpnn", "predictions/holo", "predictions/apo",
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
        try "design,name,ok,pdb,complex_plddt,iptm\ndesign_0001_0,design_0001_0,True,\(holo.path),0.91,0.82\n"
            .write(to: rfd3.appendingPathComponent("predictions/holo/prediction_metrics.csv"),
                   atomically: true, encoding: .utf8)
        try "design,name,ok,pdb,complex_plddt,iptm\ndesign_0001_0,design_0001_0,True,\(apo.path),0.88,0\n"
            .write(to: rfd3.appendingPathComponent("predictions/apo/prediction_metrics.csv"),
                   atomically: true, encoding: .utf8)
        try "design,name,holo_vs_apo_ca_rmsd\ndesign_0001_0,design_0001_0,1.25\n"
            .write(to: rfd3.appendingPathComponent("analysis/rmsd_metrics.csv"),
                   atomically: true, encoding: .utf8)
        try "design,seq_index,sequence,backbone_pdb\ndesign_0001,0,AAAA,\(backbone.path)\n"
            .write(to: rfd3.appendingPathComponent("mpnn/sequences.csv"),
                   atomically: true, encoding: .utf8)
        let ranked: [[String: Any]] = [[
            "design": "design_0001_0", "name": "design_0001_0",
            "backbone_pdb": backbone.path, "sequence": "AAAA",
            "pdb": holo.path, "iptm": 0.82, "score": 0.9,
        ]]
        try JSONSerialization.data(withJSONObject: ranked).write(
            to: rfd3.appendingPathComponent("analysis/top100_manifest.json"))
        try JSONSerialization.data(withJSONObject: ["target_kind": "small_molecule"]).write(
            to: rfd3.appendingPathComponent("config/campaign.json"))

        let rfd3Results = RunResultsLoader.load(root: rfd3, workflow: .rfdiffusion3)
        let rfd3Groups = RunResultsLoader.groups(from: rfd3Results)
        guard rfd3Results.count == 3,
              rfd3Groups.count == 1,
              rfd3Groups.first?.id == "rfd3|design_0001",
              rfd3Groups.first?.primaryItems.count == 1,
              rfd3Groups.first?.variants.first?.id == "design_0001_0",
              rfd3Groups.first?.variants.first?.items.count == 2,
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
        // A shortlist must not erase unranked but completed derivatives.
        let unranked = rfd3.appendingPathComponent("predictions/holo/design_0001_1.pdb")
        try "ATOM fixture".write(to: unranked, atomically: true, encoding: .utf8)
        let holoCSV = rfd3.appendingPathComponent("predictions/holo/prediction_metrics.csv")
        let originalHolo = try String(contentsOf: holoCSV, encoding: .utf8)
        let parsed = CSVTable.rows(at: holoCSV)
        precondition(!parsed.isEmpty)
        // Preserve the actual fixture's header/columns by replacing its first data row.
        let extra = originalHolo.split(separator: "\n").dropFirst().first!.replacingOccurrences(of: "design_0001_0", with: "design_0001_1")
        try (originalHolo + (originalHolo.hasSuffix("\n") ? "" : "\n") + extra + "\n").write(to: holoCSV, atomically: true, encoding: .utf8)
        let expanded = RunResultsLoader.load(root: rfd3, workflow: .rfdiffusion3)
        precondition(expanded.contains { $0.variantID == "design_0001_1" && $0.stage == .verificationPrediction && $0.isHit == nil })
        precondition(expanded.filter { $0.variantID == "design_0001_0" }.count == 2)
        let filter = ResultBrowserFilter(query: "design_0001_1", stage: StudioResultStage.verificationPrediction.rawValue, source: "Boltz-2")
        precondition(expanded.filter(filter.includes).count == 1)

        // Two Boltz samples in one directory receive their own confidences, not
        // a task-level representative score or another model's confidence.
        let multi = root.appendingPathComponent("boltz-multiple")
        try fm.createDirectory(at: multi, withIntermediateDirectories: true)
        for (index, value) in [(1, 0.6), (10, 0.9)] {
            try "data_fixture".write(to: multi.appendingPathComponent("input_model_\(index).cif"), atomically: true, encoding: .utf8)
            try JSONSerialization.data(withJSONObject: ["iptm": value, "ligand_plddt": 81.0]).write(to: multi.appendingPathComponent("confidence_input_model_\(index).json"))
        }
        try "job,predictor,exit_code,output,iptm\ninput,boltz,0,\(multi.path),0.99\n".write(to: root.appendingPathComponent("predictions.csv"), atomically: true, encoding: .utf8)
        try JSONSerialization.data(withJSONObject: ["template": ["path": "template.cif"], "jobs": [["name": "input", "chains": [["kind": "protein", "sequence": "AAAA"]]]]])
            .write(to: root.appendingPathComponent("prediction_config.json"))
        let samples = RunResultsLoader.load(root: root, workflow: .prediction)
        precondition(samples.count == 2 && RunResultsLoader.groups(from: samples).count == 1)
        precondition(Set(samples.compactMap { $0.metrics.first { $0.kind == .iptm }?.value }) == Set([0.6, 0.9]))
        precondition(samples.allSatisfy { $0.subtitle.contains("Template-conditioned") && $0.isHit == nil })
        precondition(samples.allSatisfy { $0.metrics.contains { $0.kind == .ligandPLDDT && $0.value == 81 } && !$0.metrics.contains { $0.kind == .plddt } })
        // Live Predict has no final predictions.csv yet; only committed chunks
        // may expose native files. A copied raw file without a marker is ignored.
        let livePredict = csvRoot.appendingPathComponent("live-predict")
        let chunk = livePredict.appendingPathComponent("boltz/bucket_128/chunk_0")
        try fm.createDirectory(at: chunk, withIntermediateDirectories: true)
        try "data_fixture".write(to: chunk.appendingPathComponent("input_model_0.cif"), atomically: true, encoding: .utf8)
        precondition(RunResultsLoader.load(root: livePredict, workflow: .prediction).isEmpty)
        try JSONSerialization.data(withJSONObject: ["predictor": "boltz", "jobs": ["input"]]).write(to: chunk.appendingPathComponent("chunk_complete.json"))
        try JSONSerialization.data(withJSONObject: ["affinity_probability_binary": 0.78]).write(to: chunk.appendingPathComponent("affinity_input.json"))
        let liveItems = RunResultsLoader.load(root: livePredict, workflow: .prediction)
        precondition(liveItems.count == 1 && liveItems[0].metrics.contains { $0.kind == .bindingProbability && $0.value == 0.78 })
        precondition(RunResultsLoader.predictionRows(root: livePredict).count == 1)
        try "job,predictor,exit_code,output\ninput,boltz,0,\(chunk.path)\n".write(to: livePredict.appendingPathComponent("predictions.csv"), atomically: true, encoding: .utf8)
        precondition(RunResultsLoader.load(root: livePredict, workflow: .prediction).count == 1)
        print("PASS live Predict chunk receipts, unfinished output exclusion, CSV deduplication and unambiguous affinity attribution")
        print("PASS unranked RFD3 preservation, shared filters, Predict input/sample grouping, template provenance and exact confidence attribution")
        print("PASS prediction result discovery contract")
    }
}
