import Foundation

/// Reads the durable output formats already written by PredictionController,
/// NanoHunter campaigns and RFdiffusion3 campaigns. It never invents a metric:
/// absent engine output stays absent in the UI.
enum RunResultsLoader {
    private static let fm = FileManager.default

    static func load(root: URL, workflow: StudioWorkflow) -> [StudioResultItem] {
        switch workflow {
        case .nise: return niseResults(root: root)
        case .prediction: return predictionResults(root: root)
        case .iterative:
            if fm.fileExists(atPath: root.appendingPathComponent("studio_engine_batch.json").path) { return batchResults(root: root) }
            return iterativeResults(root: root) + ligandScreeningResults(root: root)
        case .rfdiffusion3: return rfd3Results(root: root) + ligandScreeningResults(root: root)
        }
    }

    struct BatchCampaign: Identifiable {
        var id: String { root.lastPathComponent }
        let root: URL
        let frameworkID: String
        let frameworkName: String
        let engine: String
        let trajectories: Int
    }

    /// Children are siblings of the saved batch. Relocate by exact basename for
    /// copied archives; never follow an arbitrary path or escape the workspace.
    static func batchCampaigns(root: URL) -> [BatchCampaign] {
        guard let descriptor = jsonObject(at: root.appendingPathComponent("studio_engine_batch.json")),
              let paths = descriptor["campaigns"] as? [String] else { return [] }
        let workspace = root.deletingLastPathComponent().resolvingSymlinksInPath()
        return paths.enumerated().compactMap { index, path in
            let child = workspace.appendingPathComponent(URL(fileURLWithPath: path).lastPathComponent).resolvingSymlinksInPath()
            guard child.deletingLastPathComponent() == workspace,
                  let manifest = jsonObject(at: child.appendingPathComponent("studio_run.json")) else { return nil }
            let request = manifest["request"] as? [String: Any] ?? [:]
            let framework = request["scaffoldID"] as? String ?? "none"
            let labels = descriptor["engines"] as? [String] ?? []
            let label = index < labels.count ? labels[index] : framework
            let frameworkName = label.components(separatedBy: " · ").dropFirst().joined(separator: " · ")
            let engineIDs = descriptor["engineIDs"] as? [String] ?? []
            return BatchCampaign(root: child, frameworkID: framework,
                frameworkName: frameworkName.isEmpty ? framework : frameworkName,
                engine: index < engineIDs.count ? engineIDs[index] : (request["designPredictor"] as? String ?? label),
                trajectories: request["numDesigns"] as? Int ?? 0)
        }
    }

    static func batchResults(root: URL) -> [StudioResultItem] {
        batchCampaigns(root: root).flatMap { child in
            (iterativeResults(root: child.root) + ligandScreeningResults(root: child.root)).map { item in
                var value = StudioResultItem(id: child.id + "|" + item.id, title: item.title,
                    subtitle: child.frameworkName + " · " + child.engine + " · " + item.subtitle,
                    structureURL: item.structureURL, sequence: item.sequence, metrics: item.metrics,
                    confidenceURL: item.confidenceURL, stage: item.stage, scoreSource: item.scoreSource,
                    isHit: item.isHit, failedFilters: item.failedFilters, motifMapping: item.motifMapping,
                    motifResidueRMSDs: item.motifResidueRMSDs,
                    groupID: "iterative|" + child.id + "|" + item.groupID,
                    groupTitle: child.frameworkName + " · " + child.engine + " · " + item.groupTitle,
                    variantID: item.variantID, variantTitle: item.variantTitle, artifactRole: item.artifactRole)
                value.frameworkID = child.frameworkID; value.frameworkName = child.frameworkName
                value.campaignID = child.id; value.designEngine = child.engine
                value.designHitThreshold = iterativeHitThreshold(root: child.root)
                return value
            }
        }
    }

    static func groups(from items: [StudioResultItem]) -> [StudioResultGroup] {
        Dictionary(grouping: items, by: \.groupID).map { id, members in
            StudioResultGroup(id: id, title: members.first?.groupTitle ?? id, items: members)
        }.sorted { $0.title.localizedStandardCompare($1.title) == .orderedAscending }
    }

    private static func ligandScreeningResults(root: URL) -> [StudioResultItem] {
        let directory = root.appendingPathComponent("nesso_verification").standardizedFileURL.resolvingSymlinksInPath()
        let report = directory.appendingPathComponent("results.json")
        guard let data = try? Data(contentsOf: report),
              let rows = (try? JSONSerialization.jsonObject(with: data)) as? [[String: Any]] else { return [] }
        func artifact(_ path: String) -> URL? {
            guard !path.hasPrefix("/") else { return nil }
            let url = directory.appendingPathComponent(path).standardizedFileURL.resolvingSymlinksInPath()
            return url.path.hasPrefix(directory.path + "/") && fm.fileExists(atPath: url.path) ? url : nil
        }
        return rows.compactMap { row in
            guard let name = row["candidate"] as? String, let path = row["structure"] as? String,
                  let structure = artifact(path), let predictor = row["predictor"] as? String else { return nil }
            var metrics: [StudioResultMetric] = []
            let screeningLabel = row["screening_engine"] as? String == "psichic" ? "PSICHIC (experimental)" : "NESSO"
            let psichic = row["psichic"] as? [String: Any] ?? [:]
            for (key, kind) in [("binding_probability_proxy", StudioResultMetric.Kind.psichicBindingProxy), ("predicted_binding_affinity", .psichicAffinity), ("predicted_nonbinder", .psichicNonbinder), ("predicted_antagonist", .psichicAntagonist), ("predicted_agonist", .psichicAgonist)] {
                if let value = psichic[key] as? Double, value.isFinite { metrics.append(.init(kind: kind, value: value)) }
            }
            let nesso = row["nesso"] as? [String: Any] ?? [:]
            for (key, kind) in [("affinity_probability_binary", StudioResultMetric.Kind.nessoBindingProbability),
                                ("entropy_crop_pl", .nessoInterfaceEntropy), ("entropy_pl", .nessoPlacementEntropy),
                                ("screening_score", .nessoScreeningScore), ("affinity_pred_value", .nessoAffinity)] {
                if let value = nesso[key] as? Double, value.isFinite { metrics.append(.init(kind: kind, value: value)) }
            }
            let scores = row["structure_scores"] as? [String: Any] ?? [:]
            for (key, kind) in [("iptm", StudioResultMetric.Kind.iptm), ("ptm", .ptm), ("complex_plddt", .plddt)] {
                if let value = scores[key] as? Double, value.isFinite { metrics.append(.init(kind: kind, value: value)) }
            }
            let model = predictor == "intellifold" ? predictor + " " + (row["intellifold_model"] as? String ?? "") : predictor
            return StudioResultItem(id: "nesso-verification|" + name, title: name,
                subtitle: screeningLabel + " shortlist · " + model, structureURL: structure,
                sequence: row["sequence"] as? String, metrics: metrics,
                confidenceURL: (row["confidence_json"] as? String).flatMap(artifact),
                stage: .postPrediction, scoreSource: screeningLabel + " screen / " + model + " structure",
                groupID: "nesso-verification", groupTitle: screeningLabel + " shortlist verification",
                variantID: name, variantTitle: name, artifactRole: .complexReprediction)
        }
    }

    private static func niseResults(root: URL) -> [StudioResultItem] {
        NISEResultsLoader.load(root: root).items
    }

    // MARK: Prediction batches

    /// Predict writes its final CSV after all engines finish. Successful chunk
    /// receipts provide the same task identity while the batch is still running.
    static func predictionRows(root: URL) -> [[String: String]] {
        func key(_ row: [String: String]) -> String { (row["predictor"] ?? "") + "|" + (row["job"] ?? "") }
        let csv = CSVTable.rows(at: root.appendingPathComponent("predictions.csv"))
        var rows = Dictionary(csv.map { (key($0), $0) }, uniquingKeysWith: { _, last in last })
        func children(_ url: URL) -> [URL] { (try? fm.contentsOfDirectory(at: url, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles])) ?? [] }
        let boundary = root.standardizedFileURL.resolvingSymlinksInPath().path + "/"
        for engine in children(root) {
            for bucket in children(engine) where bucket.lastPathComponent.hasPrefix("bucket_") {
                for chunk in children(bucket) where chunk.lastPathComponent.hasPrefix("chunk_") {
                    let marker = chunk.appendingPathComponent("chunk_complete.json").resolvingSymlinksInPath()
                    guard marker.path.hasPrefix(boundary), let receipt = jsonObject(at: marker),
                          let predictor = receipt["predictor"] as? String, predictor == engine.lastPathComponent,
                          let jobs = receipt["jobs"] as? [String] else { continue }
                    for job in jobs {
                        let row = ["job": job, "predictor": predictor, "bucket": String(bucket.lastPathComponent.dropFirst(7)),
                                   "exit_code": "0", "output": chunk.path]
                        rows[key(row)] = row
                    }
                }
            }
        }
        return rows.values.sorted { key($0) < key($1) }
    }

    private static func predictionResults(root: URL) -> [StudioResultItem] {
        let rows = predictionRows(root: root)
        let sequences = predictionSequences(root: root)
        let configuration = jsonObject(at: root.appendingPathComponent("prediction_config.json")) ?? [:]
        let conditioned = configuration["template"] as? [String: Any] != nil
        let outputCounts = Dictionary(grouping: rows, by: { $0["output"] ?? "" }).mapValues(\.count)
        return rows.flatMap { row -> [StudioResultItem] in
            guard row["exit_code"] == "0", let outputText = row["output"],
                  let output = resolvedURL(outputText, relativeTo: root)
            else { return [] }

            let structures = predictionStructures(in: output, job: row["job"] ?? "",
                                                   allowGeneric: outputCounts[outputText] == 1)
            guard !structures.isEmpty else { return [] }

            let job = row["job"]?.trimmingCharacters(in: .whitespacesAndNewlines)
            let predictor = friendlyPredictor(row["predictor"] ?? "Prediction")
            let baseTitle = (job?.isEmpty == false ? job! : "Prediction")
            return structures.map { structure in
                var documents = confidenceDocuments(near: structure,
                                                    within: structure.deletingLastPathComponent())
                if structures.count == 1, let name = row["job"] {
                    let affinity = structure.deletingLastPathComponent().appendingPathComponent("affinity_" + name + ".json")
                    if fm.fileExists(atPath: affinity.path) { documents.append(affinity) }
                }
                let metrics = collectMetrics(row: structures.count == 1 ? row : [:], documents: documents)
                let suffix = structures.count > 1 ? sampleLabel(for: structure) : nil
                let title = suffix.map { "\(baseTitle) · \($0)" } ?? baseTitle
                return StudioResultItem(
                    id: "\(predictor)|\(title)|\(structure.path)", title: title,
                    subtitle: predictor + (conditioned ? " · Template-conditioned" : ""), structureURL: structure,
                    sequence: job.flatMap { sequences[$0] }, metrics: metrics,
                    confidenceURL: documents.first, stage: .prediction,
                    scoreSource: predictor, groupID: "prediction|" + baseTitle, groupTitle: baseTitle,
                    variantID: predictor + "|" + (suffix ?? structure.lastPathComponent),
                    variantTitle: predictor + " · " + (suffix ?? "Prediction"), artifactRole: .prediction
                )
            }
        }
    }

    private static func predictionSequences(root: URL) -> [String: String] {
        guard let object = jsonObject(at: root.appendingPathComponent("prediction_config.json")),
              let jobs = object["jobs"] as? [[String: Any]] else { return [:] }
        return Dictionary(jobs.compactMap { job -> (String, String)? in
            guard let name = job["name"] as? String,
                  let chains = job["chains"] as? [[String: Any]] else { return nil }
            let proteins = chains.compactMap { chain -> String? in
                guard (chain["kind"] as? String) == "protein" else { return nil }
                return chain["sequence"] as? String
            }
            guard !proteins.isEmpty else { return nil }
            return (name, proteins.joined(separator: ":"))
        }, uniquingKeysWith: { first, second in first == second ? first : "" })
    }

    // MARK: Iterative designs

    private static func iterativeResults(root: URL) -> [StudioResultItem] {
        let rows = iterativeRows(root: root)
        let recordedDesignPredictor = iterativeDesignPredictor(root: root)
        return rows.flatMap { row -> [StudioResultItem] in
            guard let path = row["structure_path"],
                  let structure = resolvedURL(path, relativeTo: root),
                  fm.fileExists(atPath: structure.path) else { return [] }
            let isPost = row["stage"]?.lowercased() == "post"
            let predictorKey = nonempty(row["predictor"]) ?? (isPost ? nil : recordedDesignPredictor) ?? "Unknown engine"
            let predictor = friendlyPredictor(predictorKey)
            let run = Int(row["run"] ?? "") ?? 0
            let cycle = Int(row["cycle"] ?? "") ?? 0
            let resultStage: StudioResultStage = isPost
                ? .postPrediction
                : (cycle == 0 ? .startingStructure : .design)
            let confidence = row["confidence_json"].flatMap { resolvedURL($0, relativeTo: root) }
            let documents = confidence.map { [$0] } ?? confidenceDocuments(near: structure, within: structure.deletingLastPathComponent())
            let groupID = "iterative|\(run)"
            let groupTitle = String(format: "Run %02d", run)
            let variantID = "cycle|\(cycle)"
            let variantTitle = cycle == 0
                ? "Starting structure"
                : String(format: "Cycle %02d", cycle)
            let role: StudioResultArtifactRole = isPost
                ? .complexReprediction
                : (cycle == 0 ? .startingStructure : .designedComplex)
            var results = [StudioResultItem(
                id: "\(resultStage.rawValue)|\(predictor)|\(run)|\(cycle)|\(structure.path)",
                title: role.label,
                subtitle: "\(resultStage.label) · \(predictor)",
                structureURL: structure, sequence: nonempty(row["binder_sequence"]),
                metrics: collectMetrics(row: row, documents: documents),
                confidenceURL: documents.first, stage: resultStage,
                scoreSource: predictor,
                isHit: boolean(row["is_hit"]),
                failedFilters: splitFilters(row["failed_filters"]),
                groupID: groupID, groupTitle: groupTitle,
                variantID: variantID, variantTitle: variantTitle,
                artifactRole: role
            )]

            if isPost, let binderPath = nonempty(row["binder_structure_path"]),
               let binderStructure = resolvedURL(binderPath, relativeTo: root),
               fm.fileExists(atPath: binderStructure.path) {
                let binderConfidence = row["binder_confidence_json"].flatMap {
                    resolvedURL($0, relativeTo: root)
                }
                let binderDocuments = binderConfidence.map { [$0] }
                    ?? confidenceDocuments(near: binderStructure,
                                           within: binderStructure.deletingLastPathComponent())
                let binderMetrics = collectMetrics(row: row, documents: binderDocuments).filter {
                    [.binderPLDDT, .binderRMSD].contains($0.kind)
                }
                results.append(StudioResultItem(
                    id: "binderAlone|\(predictor)|\(run)|\(cycle)|\(binderStructure.path)",
                    title: StudioResultArtifactRole.binderAlone.label,
                    subtitle: "Independent binder fold · \(predictor)",
                    structureURL: binderStructure, sequence: nonempty(row["binder_sequence"]),
                    metrics: binderMetrics, confidenceURL: binderDocuments.first,
                    stage: .postPrediction, scoreSource: predictor,
                    isHit: boolean(row["is_hit"]),
                    failedFilters: splitFilters(row["failed_filters"]),
                    groupID: groupID, groupTitle: groupTitle,
                    variantID: variantID, variantTitle: variantTitle,
                    artifactRole: .binderAlone
                ))
            }
            return results
        }
    }

    /// The final comparison table is convenient but is written only after all
    /// design and post-prediction work succeeds. Rebuild the same provenance
    /// columns from per-cycle checkpoints so stopped and failed runs remain
    /// browseable without changing their source files.
    private static func iterativeRows(root: URL) -> [[String: String]] {
        let comparison = CSVTable.rows(at: root.appendingPathComponent("comparison_scores_long.csv"))
        if !comparison.isEmpty { return comparison }

        let designPredictor = iterativeDesignPredictor(root: root) ?? "Unknown engine"
        let runDirectories = childDirectories(root).filter { $0.lastPathComponent.hasPrefix("run_") }
        var rows: [[String: String]] = []
        for runDirectory in runDirectories {
            let run = String(Int(runDirectory.lastPathComponent.dropFirst("run_".count)) ?? 0)
            for var row in CSVTable.rows(at: runDirectory.appendingPathComponent("metrics_per_cycle.csv")) {
                row["stage"] = "design"
                row["predictor"] = designPredictor
                row["run"] = run
                rows.append(row)
            }
            for postRoot in childDirectories(runDirectory) where postRoot.lastPathComponent.hasPrefix("post_") {
                let predictor = String(postRoot.lastPathComponent.dropFirst("post_".count))
                for cycleRoot in childDirectories(postRoot) where cycleRoot.lastPathComponent.hasPrefix("cycle_") {
                    for var row in CSVTable.rows(at: cycleRoot.appendingPathComponent("post_metrics_row.csv")) {
                        row["stage"] = "post"
                        row["predictor"] = predictor
                        if row["run"] == nil { row["run"] = run }
                        rows.append(row)
                    }
                }
            }
        }
        if !rows.isEmpty { return rows }

        // Compatibility with older completed campaigns that retained only the
        // aggregate design summary.
        return CSVTable.rows(at: root.appendingPathComponent("summary_all_runs.csv")).map { raw in
            var row = raw
            row["stage"] = "design"
            row["predictor"] = designPredictor
            return row
        }
    }

    static func iterativeHitThreshold(root: URL) -> Double {
        let arguments = iterativeManifestArguments(root: root)
        guard let index = arguments.firstIndex(of: "--iptm-threshold"),
              arguments.indices.contains(index + 1),
              let threshold = Double(arguments[index + 1]) else { return 0.70 }
        return threshold
    }

    private static func iterativeDesignPredictor(root: URL) -> String? {
        let arguments = iterativeManifestArguments(root: root)
        guard let index = arguments.firstIndex(of: "--predictor"),
              arguments.indices.contains(index + 1) else { return nil }
        return arguments[index + 1]
    }

    private static func iterativeManifestArguments(root: URL) -> [String] {
        jsonObject(at: root.appendingPathComponent("studio_run.json"))?["arguments"] as? [String] ?? []
    }

    private static func childDirectories(_ root: URL) -> [URL] {
        (try? fm.contentsOfDirectory(at: root, includingPropertiesForKeys: [.isDirectoryKey],
                                     options: [.skipsHiddenFiles]))?.filter {
            (try? $0.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true
        } ?? []
    }

    // MARK: RFdiffusion3 live and ranked designs

    private enum RFD3PredictionContext: String {
        case complex
        case binderAlone

        var label: String {
            switch self {
            case .complex: return "Complex"
            case .binderAlone: return "Binder alone"
            }
        }
    }

    private static func rfd3Results(root: URL) -> [StudioResultItem] {
        let backbones = liveRFD3Backbones(root: root)
        let ranked = rankedRFD3Results(root: root)
        // Ranked summaries cover a shortlist, not the whole prediction pool.
        // Replace matching provisional artifacts and retain all other completed work.
        if !ranked.isEmpty {
            func identity(_ item: StudioResultItem) -> String {
                [item.groupID, item.variantID ?? "", item.artifactRole.rawValue, item.scoreSource].joined(separator: "|")
            }
            let promoted = Set(ranked.map(identity))
            return backbones + ranked + liveRFD3Predictions(root: root).filter { !promoted.contains(identity($0)) }
        }

        // Prediction rows are append-only checkpoints. Prefer them as soon as
        // structures exist, but fall back to raw generated backbones while the
        // predictor stage has not started yet.
        let predicted = liveRFD3Predictions(root: root)
        return backbones + predicted
    }

    private static func rankedRFD3Results(root: URL) -> [StudioResultItem] {
        let manifest = root.appendingPathComponent("analysis/top100_manifest.json")
        guard let data = try? Data(contentsOf: manifest),
              let rows = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
        else { return [] }

        let holoRows = CSVTable.rows(at: root.appendingPathComponent("predictions/holo/prediction_metrics.csv"))
        let monomerRows = CSVTable.rows(at: root.appendingPathComponent("predictions/monomer/prediction_metrics.csv"))
        let apoRows = CSVTable.rows(at: root.appendingPathComponent("predictions/apo/prediction_metrics.csv"))
        let rmsdRows = CSVTable.rows(at: root.appendingPathComponent("analysis/rmsd_metrics.csv"))
        let sequenceRows = CSVTable.rows(at: root.appendingPathComponent("mpnn/sequences.csv"))
        let sequenceByDerivative = rfd3SequencesByDerivative(sequenceRows)
        let complexLabel = rfd3ComplexLabel(root: root)
        var results: [StudioResultItem] = []
        for (rankIndex, raw) in rows.enumerated() {
            let row = stringRow(raw)
            let name = nonempty(row["name"]) ?? nonempty(row["design"]) ?? "Design \(rankIndex + 1)"
            let derivativeID = name
            let sourceDesign = rfd3BackboneIdentity(
                selected: row, derivativeID: derivativeID,
                sequenceByDerivative: sequenceByDerivative)
            let groupID = "rfd3|\(sourceDesign)"
            let groupTitle = sourceDesign
            let variantTitle = rfd3VariantTitle(derivativeID, backbone: sourceDesign)
            let sequence = nonempty(row["sequence"])
            let matchingHolo = matchingPredictionRows(for: row, in: holoRows)
            let matchingBinder = matchingPredictionRows(for: row, in: monomerRows + apoRows)
            let matchingRMSD = matchingPredictionRows(for: row, in: rmsdRows).first ?? [:]
            var structures: [(String, String)] = []
            if let map = raw["structures"] as? [String: String] {
                structures = map.sorted { $0.key < $1.key }
            } else if let encoded = raw["structures"] as? String,
                      let data = encoded.data(using: .utf8),
                      let map = try? JSONSerialization.jsonObject(with: data) as? [String: String] {
                structures = map.sorted { $0.key < $1.key }
            } else if let path = nonempty(row["pdb"]) ?? nonempty(row["structure"]) {
                structures = [(nonempty(row["predictor"]) ?? "boltz", path)]
            }

            for (savedPredictorKey, path) in structures {
                guard let structure = resolvedURL(path, relativeTo: root),
                      fm.fileExists(atPath: structure.path) else { continue }
                let predictorKey = nonempty(savedPredictorKey) ?? nonempty(row["predictor"]) ?? "boltz"
                let predictorRow = matchingHolo.first {
                    (nonempty($0["predictor"]) ?? predictorKey).lowercased() == predictorKey.lowercased()
                } ?? [:]
                var metricRow = row
                matchingRMSD.forEach { metricRow[$0.key] = $0.value }
                predictorRow.forEach { metricRow[$0.key] = $0.value }
                if let value = row["iptm_\(predictorKey)"] { metricRow["iptm"] = value }
                if let value = row["ipsae_min_\(predictorKey)"] { metricRow["ipsae_min"] = value }
                addPredictorAggregate(raw: raw, key: "complex_rmsd_by_predictor",
                                      predictor: predictorKey, to: "maximum_complex_rmsd", row: &metricRow)
                addPredictorAggregate(raw: raw, key: "binder_backbone_rmsd_by_predictor",
                                      predictor: predictorKey, to: "maximum_binder_backbone_rmsd", row: &metricRow)
                if let values = dictionaryOfDoubles(raw["motif_rmsd_by_predictor"]),
                   let value = values[predictorKey] {
                    metricRow["motif_prediction_rmsd"] = String(value)
                }
                let documents = confidenceDocuments(near: structure, within: structure.deletingLastPathComponent())
                let predictor = friendlyPredictor(predictorKey)
                results.append(StudioResultItem(
                    id: "ranked|complex|\(rankIndex)|\(predictorKey)|\(structure.path)",
                    title: "#\(rankIndex + 1) · \(name) · complex",
                    subtitle: "\(complexLabel) · \(predictor)", structureURL: structure,
                    sequence: sequence, metrics: collectMetrics(row: metricRow, documents: documents),
                    confidenceURL: documents.first, stage: .rankedDesign,
                    scoreSource: predictor,
                    isHit: boolean(row["is_hit"]),
                    failedFilters: splitFilters(row["failed_filters"]),
                    motifMapping: dictionaryOfStrings(raw["diffused_index_map"])
                        ?? dictionaryOfStrings(row["diffused_index_map"]) ?? [:],
                    motifResidueRMSDs: predictorDictionaryOfDoubles(
                        raw["motif_rmsd_by_residue"], predictor: predictorKey)
                        ?? predictorDictionaryOfDoubles(
                            row["motif_rmsd_by_residue"], predictor: predictorKey) ?? [:],
                    groupID: groupID, groupTitle: groupTitle,
                    variantID: derivativeID, variantTitle: variantTitle,
                    artifactRole: .complexReprediction
                ))
            }

            for binderRow in matchingBinder where predictionSucceeded(binderRow) {
                guard let path = nonempty(binderRow["structure"]) ?? nonempty(binderRow["pdb"]),
                      let structure = resolvedURL(path, relativeTo: root),
                      fm.fileExists(atPath: structure.path) else { continue }
                let predictorKey = nonempty(binderRow["predictor"]) ?? nonempty(row["predictor"]) ?? "boltz"
                let predictor = friendlyPredictor(predictorKey)
                var metricRow = row
                matchingRMSD.forEach { metricRow[$0.key] = $0.value }
                binderRow.forEach { metricRow[$0.key] = $0.value }
                if let confidence = nonempty(binderRow["plddt"])
                    ?? nonempty(binderRow["complex_plddt"])
                    ?? nonempty(binderRow["protein_plddt"])
                    ?? nonempty(binderRow["mean_plddt"]) {
                    metricRow["minimum_binder_plddt"] = confidence
                }
                addPredictorAggregate(raw: raw, key: "binder_rmsd_by_predictor",
                                      predictor: predictorKey, to: "maximum_binder_rmsd", row: &metricRow)
                if metricRow["maximum_binder_rmsd"] == nil,
                   let value = nonempty(matchingRMSD["holo_vs_apo_ca_rmsd"]) {
                    metricRow["maximum_binder_rmsd"] = value
                }
                let documents = confidenceDocuments(near: structure, within: structure.deletingLastPathComponent())
                let metrics = collectMetrics(row: metricRow, documents: documents).filter {
                    [.binderPLDDT, .binderRMSD, .motifPredictionRMSD].contains($0.kind)
                }
                results.append(StudioResultItem(
                    id: "ranked|binder|\(rankIndex)|\(predictorKey)|\(structure.path)",
                    title: "#\(rankIndex + 1) · \(name) · binder alone",
                    subtitle: "Binder alone · \(predictor)", structureURL: structure,
                    sequence: sequence, metrics: metrics,
                    confidenceURL: documents.first, stage: .rankedDesign,
                    scoreSource: predictor,
                    isHit: boolean(row["is_hit"]),
                    failedFilters: splitFilters(row["failed_filters"]),
                    motifMapping: dictionaryOfStrings(raw["diffused_index_map"])
                        ?? dictionaryOfStrings(row["diffused_index_map"]) ?? [:],
                    motifResidueRMSDs: predictorDictionaryOfDoubles(
                        raw["motif_rmsd_by_residue"], predictor: predictorKey)
                        ?? predictorDictionaryOfDoubles(
                            row["motif_rmsd_by_residue"], predictor: predictorKey) ?? [:],
                    groupID: groupID, groupTitle: groupTitle,
                    variantID: derivativeID, variantTitle: variantTitle,
                    artifactRole: .binderAlone
                ))
            }
        }
        return results
    }

    private static func liveRFD3Predictions(root: URL) -> [StudioResultItem] {
        liveRFD3Predictions(root: root, directory: "holo", context: .complex)
            + liveRFD3Predictions(root: root, directory: "monomer", context: .binderAlone)
            + liveRFD3Predictions(root: root, directory: "apo", context: .binderAlone)
    }

    private static func liveRFD3Predictions(root: URL, directory: String,
                                            context: RFD3PredictionContext) -> [StudioResultItem] {
        let rows = CSVTable.rows(at: root.appendingPathComponent("predictions/\(directory)/prediction_metrics.csv"))
        guard !rows.isEmpty else { return [] }
        let sequenceRows = CSVTable.rows(at: root.appendingPathComponent("mpnn/sequences.csv"))
        let sequences = rfd3SequencesByDerivative(sequenceRows)
        let backboneRows = rfd3BackboneRows(root: root)
        let backboneByDesign = Dictionary(uniqueKeysWithValues: backboneRows.compactMap { row -> (String, [String: String])? in
            nonempty(row["design"]).map { ($0, row) }
        })

        return rows.compactMap { row in
            guard predictionSucceeded(row),
                  let path = nonempty(row["structure"]) ?? nonempty(row["pdb"]),
                  let structure = resolvedURL(path, relativeTo: root),
                  fm.fileExists(atPath: structure.path) else { return nil }
            let design = nonempty(row["design"]) ?? nonempty(row["name"]) ?? structure.deletingPathExtension().lastPathComponent
            let source = sequences[design]
            let backboneName = rfd3BackboneIdentity(
                selected: source ?? row, derivativeID: design,
                sequenceByDerivative: sequences)
            let backbone = backboneByDesign[backboneName] ?? [:]
            var metricRow = backbone
            source?.forEach { metricRow[$0.key] = $0.value }
            row.forEach { metricRow[$0.key] = $0.value }
            let predictorKey = nonempty(row["predictor"]) ?? "boltz"
            let predictor = friendlyPredictor(predictorKey)
            if context == .binderAlone,
               let confidence = nonempty(row["plddt"])
                ?? nonempty(row["complex_plddt"])
                ?? nonempty(row["protein_plddt"])
                ?? nonempty(row["mean_plddt"]) {
                metricRow["minimum_binder_plddt"] = confidence
            }
            let documents = confidenceDocuments(near: structure, within: structure.deletingLastPathComponent())
            var metrics = collectMetrics(row: metricRow, documents: documents)
            if context == .binderAlone {
                metrics = metrics.filter { [.binderPLDDT, .binderRMSD].contains($0.kind) }
            }
            return StudioResultItem(
                id: "live|\(context.rawValue)|\(predictorKey)|\(design)|\(structure.path)",
                title: "\(design) · \(context == .complex ? "complex" : "binder alone")",
                subtitle: "\(context == .complex ? rfd3ComplexLabel(root: root) : context.label) · \(predictor)",
                structureURL: structure, sequence: source.flatMap { nonempty($0["sequence"]) },
                metrics: metrics,
                confidenceURL: documents.first, stage: .verificationPrediction,
                scoreSource: predictor,
                motifMapping: dictionaryOfStrings(backbone["diffused_index_map"]) ?? [:],
                motifResidueRMSDs: dictionaryOfDoubles(backbone["motif_insertion_rmsd_by_token"]) ?? [:],
                groupID: "rfd3|\(backboneName)", groupTitle: backboneName,
                variantID: design,
                variantTitle: rfd3VariantTitle(design, backbone: backboneName),
                artifactRole: context == .complex ? .complexReprediction : .binderAlone
            )
        }.sorted { $0.title.localizedStandardCompare($1.title) == .orderedAscending }
    }

    private static func predictionSucceeded(_ row: [String: String]) -> Bool {
        row["exit_code"] == "0" || row["ok"]?.lowercased() == "true"
    }

    private static func matchingPredictionRows(for selected: [String: String],
                                               in candidates: [[String: String]]) -> [[String: String]] {
        if let name = nonempty(selected["name"]) {
            let exact = candidates.filter {
                nonempty($0["name"]) == name || nonempty($0["design"]) == name
            }
            if !exact.isEmpty { return exact }
        }
        guard let design = nonempty(selected["design"]) else { return [] }
        return candidates.filter { nonempty($0["design"]) == design }
    }

    private static func addPredictorAggregate(raw: [String: Any], key: String,
                                              predictor: String, to outputKey: String,
                                              row: inout [String: String]) {
        if let values = dictionaryOfDoubles(raw[key]), let value = values[predictor] {
            row[outputKey] = String(value)
        }
    }

    private static func rfd3ComplexLabel(root: URL) -> String {
        let kind = jsonObject(at: root.appendingPathComponent("config/campaign.json"))?["target_kind"] as? String
        return kind == "small_molecule" ? "Complex with ligand" : "Complex with target"
    }

    /// MPNN tables have used both a source-backbone `design` value plus a
    /// `seq_index`, and an already suffixed derivative identity. Normalize
    /// both without assuming the schema of one particular campaign version.
    private static func rfd3SequencesByDerivative(
        _ rows: [[String: String]]
    ) -> [String: [String: String]] {
        rows.reduce(into: [:]) { result, row in
            guard let design = nonempty(row["design"]) else { return }
            let derivative: String
            if let index = nonempty(row["seq_index"]),
               !design.hasSuffix("_\(index)") {
                derivative = "\(design)_\(index)"
            } else {
                derivative = design
            }
            result[derivative] = row
        }
    }

    /// The source PDB is the durable backbone identity. Prefer it over
    /// manifest `design`, which newer pipelines legitimately use for the MPNN
    /// derivative (for example design_0002_1 rather than design_0002).
    private static func rfd3BackboneIdentity(
        selected: [String: String], derivativeID: String,
        sequenceByDerivative: [String: [String: String]]
    ) -> String {
        let source = sequenceByDerivative[derivativeID] ?? selected
        if let path = nonempty(source["backbone_pdb"]) ?? nonempty(selected["backbone_pdb"]) {
            return URL(fileURLWithPath: path).deletingPathExtension().lastPathComponent
        }
        if let design = nonempty(source["design"]), design != derivativeID {
            return design
        }
        return derivativeID.replacingOccurrences(
            of: #"_[0-9]+$"#, with: "", options: .regularExpression)
    }

    private static func rfd3VariantTitle(_ derivativeID: String,
                                         backbone: String) -> String {
        let prefix = backbone + "_"
        if derivativeID.hasPrefix(prefix) {
            let suffix = String(derivativeID.dropFirst(prefix.count))
            if !suffix.isEmpty { return "MPNN sequence \(suffix)" }
        }
        return derivativeID
    }

    private static func liveRFD3Backbones(root: URL) -> [StudioResultItem] {
        rfd3BackboneRows(root: root).compactMap { row in
            guard let path = nonempty(row["backbone_pdb"]) ?? nonempty(row["source_pdb"]),
                  let structure = resolvedURL(path, relativeTo: root),
                  fm.fileExists(atPath: structure.path) else { return nil }
            let design = nonempty(row["design"]) ?? structure.deletingPathExtension().lastPathComponent
            return StudioResultItem(
                id: "backbone|\(structure.path)", title: design,
                subtitle: "Generated backbone · awaiting sequence verification",
                structureURL: structure, sequence: nil,
                metrics: collectMetrics(row: row, documents: []), confidenceURL: nil,
                stage: .generatedBackbone, scoreSource: "RFdiffusion3 MLX",
                motifMapping: dictionaryOfStrings(row["diffused_index_map"]) ?? [:],
                motifResidueRMSDs: dictionaryOfDoubles(row["motif_insertion_rmsd_by_token"]) ?? [:],
                groupID: "rfd3|\(design)", groupTitle: design,
                artifactRole: .generatedBackbone
            )
        }.sorted { $0.title.localizedStandardCompare($1.title) == .orderedAscending }
    }

    private static func rfd3BackboneRows(root: URL) -> [[String: String]] {
        let table = CSVTable.rows(at: root.appendingPathComponent("rfd3/backbone_metrics.csv"))
        if !table.isEmpty { return table }

        // During generation, queues checkpoint one JSON and PDB per accepted
        // sample before the bin is flattened. Reading those immutable files is
        // what makes structures visible while diffusion is still running.
        let resultFiles = recursiveFiles(in: root.appendingPathComponent("rfd3")).filter {
            $0.pathExtension.lowercased() == "json"
                && $0.deletingLastPathComponent().lastPathComponent == "results"
                && $0.lastPathComponent.hasPrefix("design_")
        }
        return resultFiles.compactMap { result -> [String: String]? in
            guard let object = jsonObject(at: result) else { return nil }
            var row = stringRow(object)
            for key in ["diffused_index_map", "motif_fixed_atoms", "motif_insertion_rmsd_by_token"] {
                if let value = object[key],
                   let data = try? JSONSerialization.data(withJSONObject: value),
                   let text = String(data: data, encoding: .utf8) { row[key] = text }
            }
            let pdb = result.deletingLastPathComponent().deletingLastPathComponent()
                .appendingPathComponent("backbones/\(result.deletingPathExtension().lastPathComponent).pdb")
            row["backbone_pdb"] = pdb.path
            row["design"] = result.deletingPathExtension().lastPathComponent
            return row
        }
    }

    // MARK: Metric extraction

    private static func collectMetrics(row: [String: String], documents: [URL]) -> [StudioResultMetric] {
        var values: [StudioResultMetric.Kind: Double] = [:]
        func add(_ kind: StudioResultMetric.Kind, _ value: Double?) {
            if let value, value.isFinite, values[kind] == nil { values[kind] = value }
        }
        func rowNumber(_ keys: [String]) -> Double? {
            for key in keys {
                if let text = row[key], let value = Double(text), value.isFinite { return value }
            }
            return nil
        }

        add(.plddt, rowNumber(["complex_plddt", "plddt"]))
        add(.ligandPLDDT, rowNumber(["ligand_plddt"]))
        add(.iptm, rowNumber(["iptm", "ipTM"]))
        add(.ptm, rowNumber(["ptm", "pTM"]))
        add(.interfacePAEMinimum, rowNumber(["ipae_min", "interface_pae_min", "min_interface_pae"]))
        add(.ipsaeMinimum, rowNumber(["ipsae_min", "ipSAE_min", "ipsae(min)"]))
        add(.interfacePDE, rowNumber(["complex_ipde", "interface_pde"]))
        add(.minimumIPTM, rowNumber(["min_iptm"]))
        add(.meanIPTM, rowNumber(["mean_iptm"]))
        add(.bindingProbability, rowNumber(["pbind", "affinity_probability_binary"]))
        add(.rankingScore, rowNumber(["score", "ranking_score"]))
        add(.pocketMeanDistance, rowNumber(["constraint_pocket_mean_min_ca_distance"]))
        add(.pocketFractionWithinCutoff, rowNumber(["constraint_pocket_fraction_within_max_distance"]))
        add(.complexRMSD, rowNumber(["maximum_complex_rmsd", "complex_rmsd"]))
        add(.binderBackboneRMSD, rowNumber(["maximum_binder_backbone_rmsd", "binder_backbone_rmsd"]))
        add(.binderPLDDT, rowNumber(["minimum_binder_plddt", "binder_plddt"]))
        add(.binderRMSD, rowNumber(["maximum_binder_rmsd", "binder_rmsd"]))
        add(.motifInsertionRMSD, rowNumber(["motif_insertion_rmsd"]))
        add(.motifPredictionRMSD, rowNumber(["motif_prediction_rmsd", "maximum_motif_rmsd"]))
        add(.motifMaximumDrift, rowNumber(["motif_max_drift"]))
        add(.backboneCAValidity, rowNumber(["ca_valid_pct"]))

        for document in documents {
            guard let object = jsonObject(at: document) else { continue }
            add(.plddt, number(in: object, keys: ["complex_plddt", "protein_plddt", "mean_plddt", "plddt"]))
            add(.ligandPLDDT, number(in: object, keys: ["ligand_plddt"]))
            add(.iptm, number(in: object, keys: ["iptm", "ipTM"]))
            add(.ptm, number(in: object, keys: ["ptm", "pTM"]))
            add(.interfacePAEMinimum, number(in: object, keys: ["ipae_min", "interface_pae_min", "min_interface_pae"]))
            add(.interfacePAEMinimum, offDiagonalMinimum(object["chain_pair_pae_min"]))
            add(.ipsaeMinimum, number(in: object, keys: ["ipsae_min", "ipSAE_min", "ipsae(min)"]))
            add(.interfacePDE, number(in: object, keys: ["complex_ipde", "interface_pde"]))
            add(.bindingProbability, number(in: object, keys: ["affinity_probability_binary", "pbind"]))
            add(.rankingScore, number(in: object, keys: ["ranking_score", "score"]))
            add(.pocketMeanDistance, number(in: object, keys: ["constraint_pocket_mean_min_ca_distance"]))
            add(.pocketFractionWithinCutoff, number(in: object, keys: ["constraint_pocket_fraction_within_max_distance"]))
        }

        let order = StudioResultMetric.Kind.allCases
        return order.compactMap { kind in values[kind].map { StudioResultMetric(kind: kind, value: $0) } }
    }

    private static func number(in object: [String: Any], keys: [String]) -> Double? {
        for key in keys {
            if let value = object[key] as? NSNumber { return value.doubleValue }
            if let value = object[key] as? Double { return value }
            if let values = object[key] as? [NSNumber], !values.isEmpty {
                return values.map(\.doubleValue).reduce(0, +) / Double(values.count)
            }
        }
        // AF3-style detailed confidence output stores per-atom pLDDT values.
        if keys.contains("plddt"), let values = object["atom_plddts"] as? [NSNumber], !values.isEmpty {
            return values.map(\.doubleValue).reduce(0, +) / Double(values.count)
        }
        return nil
    }

    private static func offDiagonalMinimum(_ value: Any?) -> Double? {
        guard let rows = value as? [[Any]], rows.count > 1 else { return nil }
        var result: Double?
        for (i, row) in rows.enumerated() {
            for (j, item) in row.enumerated() where i != j {
                guard let number = item as? NSNumber else { continue }
                result = min(result ?? number.doubleValue, number.doubleValue)
            }
        }
        return result
    }

    // MARK: Files and formats

    private static func predictionStructures(in root: URL, job: String,
                                             allowGeneric: Bool) -> [URL] {
        let preferred = root.appendingPathComponent("pred_min/model_0.cif")
        let files = recursiveFiles(in: root).filter { ["cif", "pdb"].contains($0.pathExtension.lowercased()) }
        let jobKey = lookupKey(job)
        let matching = jobKey.isEmpty ? [] : files.filter { lookupKey($0.path).contains(jobKey) }
        let eligible = matching.isEmpty && allowGeneric ? files : matching
        let samples = eligible.filter { sampleLabel(for: $0) != nil }
        if !samples.isEmpty {
            return samples.sorted { $0.path.localizedStandardCompare($1.path) == .orderedAscending }
        }
        if allowGeneric, fm.fileExists(atPath: preferred.path) { return [preferred] }
        return eligible.sorted { structureRank($0, root: root) < structureRank($1, root: root) }
            .prefix(1).map { $0 }
    }

    /// Native engines use a few spelling variants. Aggregate `*_model.cif`
    /// and Studio's `pred_min/model_0.cif` are copies, while these names denote
    /// genuinely distinct stochastic outputs that must remain browseable.
    private static func sampleLabel(for url: URL) -> String? {
        let text = url.deletingPathExtension().lastPathComponent
        let patterns: [(String, String)] = [
            (#"seed[-_]([0-9]+)[-_]sample[-_]([0-9]+)"#, "seed $1 · sample $2"),
            (#"model[-_]([0-9]+)$"#, "sample $1"),
        ]
        for (pattern, template) in patterns {
            guard let regex = try? NSRegularExpression(pattern: pattern),
                  let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text))
            else { continue }
            var label = template
            for index in stride(from: match.numberOfRanges - 1, through: 1, by: -1) {
                guard let range = Range(match.range(at: index), in: text) else { continue }
                label = label.replacingOccurrences(of: "$\(index)", with: String(text[range]))
            }
            return label
        }
        return nil
    }

    private static func structureRank(_ url: URL, root: URL) -> String {
        let relative = url.path.replacingOccurrences(of: root.path, with: "")
        let seedPenalty = relative.contains("/seed-") ? "9" : "0"
        let topModel = url.lastPathComponent.contains("_model.") ? "0" : "1"
        return seedPenalty + topModel + String(format: "%05d", relative.count) + relative
    }

    private static func confidenceDocuments(near structure: URL, within root: URL) -> [URL] {
        let nearby = structure.deletingLastPathComponent().appendingPathComponent("confidence.json")
        var candidates: [URL] = fm.fileExists(atPath: nearby.path) ? [nearby] : []
        candidates += recursiveFiles(in: root).filter { url in
            let name = url.lastPathComponent.lowercased()
            guard name.hasSuffix(".json") else { return false }
            return name == "confidence.json" || name.contains("summary_confidences")
                || name.hasPrefix("confidence_") || name.hasSuffix("_confidences.json")
        }
        let unique = Dictionary(grouping: candidates, by: \.path).compactMap { $0.value.first }
        let stem = structure.deletingPathExtension().lastPathComponent.lowercased()
        let escaped = NSRegularExpression.escapedPattern(for: stem)
        let exact = unique.filter { $0.lastPathComponent.lowercased().range(of: escaped + "(?![0-9])", options: .regularExpression) != nil }
        if !exact.isEmpty { return exact.sorted { confidenceRank($0) < confidenceRank($1) } }
        // Confidence belonging to another stochastic sample must never leak in.
        func sampleIndex(_ name: String) -> String? {
            guard let regex = try? NSRegularExpression(pattern: "(?:model_|sample[-_])([0-9]+)"),
                  let match = regex.firstMatch(in: name, range: NSRange(name.startIndex..., in: name)),
                  let range = Range(match.range(at: 1), in: name) else { return nil }
            return String(name[range])
        }
        let siblings = (try? fm.contentsOfDirectory(at: structure.deletingLastPathComponent(), includingPropertiesForKeys: nil)) ?? []
        let multiple = siblings.filter { ["cif", "pdb"].contains($0.pathExtension) }.count > 1
        let filtered = unique.filter {
            guard $0.deletingLastPathComponent() == structure.deletingLastPathComponent() else { return false }
            if let index = sampleIndex($0.lastPathComponent.lowercased()) { return index == sampleIndex(stem) }
            return !multiple
        }
        return filtered.sorted { confidenceRank($0) < confidenceRank($1) }.prefix(4).map { $0 }
    }

    private static func confidenceRank(_ url: URL) -> String {
        let path = url.path.lowercased()
        let exact = url.lastPathComponent == "confidence.json" ? "0" : "1"
        let summary = path.contains("summary_confidences") ? "0" : "1"
        let seed = path.contains("/seed-") ? "9" : "0"
        return exact + summary + seed + String(format: "%05d", path.count) + path
    }

    private static func recursiveFiles(in root: URL) -> [URL] {
        guard let iterator = fm.enumerator(at: root, includingPropertiesForKeys: [.isRegularFileKey],
                                           options: [.skipsHiddenFiles]) else { return [] }
        return iterator.compactMap { item -> URL? in
            guard let url = item as? URL,
                  (try? url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true else { return nil }
            return url
        }
    }

    static func resolvedURL(_ path: String, relativeTo root: URL) -> URL? {
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        guard trimmed.hasPrefix("/") else { return root.appendingPathComponent(trimmed) }
        let original = URL(fileURLWithPath: trimmed)
        if fm.fileExists(atPath: original.path) { return original }

        // Campaign CSVs retain their original absolute provenance. If a user
        // moves or shares the self-contained run, recover the suffix below the
        // campaign basename without modifying the recorded evidence.
        let components = original.pathComponents
        if let runRootIndex = components.lastIndex(of: root.lastPathComponent),
           runRootIndex + 1 < components.count {
            let relocated = components[(runRootIndex + 1)...].reduce(root) {
                $0.appendingPathComponent($1)
            }
            if fm.fileExists(atPath: relocated.path) { return relocated }
        }
        return original
    }

    private static func jsonObject(at url: URL) -> [String: Any]? {
        guard fm.fileExists(atPath: url.path), let data = try? Data(contentsOf: url),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return object
    }

    private static func stringRow(_ object: [String: Any]) -> [String: String] {
        object.reduce(into: [:]) { result, pair in
            if let text = pair.value as? String { result[pair.key] = text }
            else if let number = pair.value as? NSNumber { result[pair.key] = number.stringValue }
        }
    }

    private static func dictionaryOfStrings(_ value: Any?) -> [String: String]? {
        if let value = value as? [String: String] { return value }
        guard let text = value as? String, let data = text.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return object.reduce(into: [:]) { result, pair in
            if let text = pair.value as? String { result[pair.key] = text }
            else if let number = pair.value as? NSNumber { result[pair.key] = number.stringValue }
        }
    }

    private static func dictionaryOfDoubles(_ value: Any?) -> [String: Double]? {
        let object: [String: Any]?
        if let map = value as? [String: Any] { object = map }
        else if let text = value as? String, let data = text.data(using: .utf8) {
            object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        } else { object = nil }
        guard let object else { return nil }
        return object.reduce(into: [:]) { result, pair in
            if let number = pair.value as? NSNumber { result[pair.key] = number.doubleValue }
            else if let text = pair.value as? String, let number = Double(text) { result[pair.key] = number }
        }
    }

    /// Accept either a flat residue map or the scorer's auditable
    /// predictor -> residue -> RMSD representation.
    private static func predictorDictionaryOfDoubles(_ value: Any?, predictor: String) -> [String: Double]? {
        if let flat = dictionaryOfDoubles(value), !flat.isEmpty { return flat }
        let object: [String: Any]?
        if let value = value as? [String: Any] { object = value }
        else if let text = value as? String, let data = text.data(using: .utf8) {
            object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        } else { object = nil }
        guard let nested = object?[predictor] else { return nil }
        return dictionaryOfDoubles(nested)
    }

    private static func nonempty(_ text: String?) -> String? {
        guard let text = text?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else { return nil }
        return text
    }

    private static func boolean(_ text: String?) -> Bool? {
        guard let text = nonempty(text)?.lowercased() else { return nil }
        if ["true", "1", "yes"].contains(text) { return true }
        if ["false", "0", "no"].contains(text) { return false }
        return nil
    }

    private static func splitFilters(_ text: String?) -> [String] {
        guard let text = nonempty(text) else { return [] }
        return text.split(separator: ";").map(String.init)
    }

    private static func friendlyPredictor(_ key: String) -> String {
        switch key.lowercased() {
        case "boltz", "boltz2", "boltz-2": return "Boltz-2"
        case "af3", "alphafold3", "alphafold-3": return "AlphaFold 3 (retired)"
        case "openfold3", "openfold-3", "openfold-3-mlx": return "OpenFold-3"
        case "intellifold": return "IntelliFold PyTorch"
        case "protenix", "protenix-v2": return "Protenix v2"
        case "protenix-mini": return "Protenix Mini"
        case "protenix-constraint-v0.5": return "Protenix Constraint v0.5"
        case "intellifold-jax", "intellifold_jax": return "IntelliFold JAX/Metal (retired)"
        default: return key.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    private static func lookupKey(_ text: String) -> String {
        text.lowercased().unicodeScalars
            .filter { CharacterSet.alphanumerics.contains($0) }
            .map(String.init).joined()
    }
}
