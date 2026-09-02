import Foundation

enum StudioResultStage: String, Hashable {
    case prediction
    case startingStructure
    case design
    case postPrediction
    case generatedBackbone
    case verificationPrediction
    case rankedDesign

    var label: String {
        switch self {
        case .prediction: return "Prediction"
        case .startingStructure: return "Unoptimized starting structure"
        case .design: return "Design stage"
        case .postPrediction: return "Independent post-prediction"
        case .generatedBackbone: return "RFdiffusion3 backbone"
        case .verificationPrediction: return "RFdiffusion3 verification in progress"
        case .rankedDesign: return "Ranked verification"
        }
    }
}

/// A structure and its most useful engine-emitted confidence summaries.
/// Values stay numeric here so every workflow uses the same formatting in the UI.
struct StudioResultItem: Identifiable, Hashable {
    let id: String
    let title: String
    let subtitle: String
    let structureURL: URL
    let sequence: String?
    let metrics: [StudioResultMetric]
    let confidenceURL: URL?
    let stage: StudioResultStage
    /// The engine that emitted `metrics`; never inferred from the engine that
    /// happened to create an earlier structure in the workflow.
    let scoreSource: String
    /// Explicit workflow verdict read from disk. Nil means that workflow did
    /// not apply a multi-metric filter; it must never be inferred silently.
    let isHit: Bool?
    let failedFilters: [String]
    /// Source motif residue -> generated chain-A residue. Kept on every stage
    /// so a design never loses the identity of its functional atoms merely
    /// because it has progressed from diffusion to MPNN or prediction.
    let motifMapping: [String: String]
    /// Optional per-source-residue geometry diagnostics. These are emitted by
    /// the MLX generator and independent-prediction recovery scorer, never
    /// inferred by the presentation layer.
    let motifResidueRMSDs: [String: Double]

    init(id: String, title: String, subtitle: String, structureURL: URL,
         sequence: String?, metrics: [StudioResultMetric], confidenceURL: URL?,
         stage: StudioResultStage, scoreSource: String, isHit: Bool? = nil,
         failedFilters: [String] = [], motifMapping: [String: String] = [:],
         motifResidueRMSDs: [String: Double] = [:]) {
        self.id = id
        self.title = title
        self.subtitle = subtitle
        self.structureURL = structureURL
        self.sequence = sequence
        self.metrics = metrics
        self.confidenceURL = confidenceURL
        self.stage = stage
        self.scoreSource = scoreSource
        self.isHit = isHit
        self.failedFilters = failedFilters
        self.motifMapping = motifMapping
        self.motifResidueRMSDs = motifResidueRMSDs
    }

    var primaryMetric: StudioResultMetric? {
        metrics.first { $0.kind == .iptm }
            ?? metrics.first { $0.kind == .ipsaeMinimum }
            ?? metrics.first { $0.kind == .plddt }
            ?? metrics.first
    }
}

struct StudioResultMetric: Identifiable, Hashable {
    enum Kind: String, CaseIterable, Hashable {
        case plddt
        case iptm
        case ptm
        case interfacePAEMinimum
        case ipsaeMinimum
        case interfacePDE
        case minimumIPTM
        case meanIPTM
        case bindingProbability
        case rankingScore
        case pocketMeanDistance
        case pocketFractionWithinCutoff
        case complexRMSD
        case binderBackboneRMSD
        case binderPLDDT
        case binderRMSD
        case motifInsertionRMSD
        case motifPredictionRMSD
        case motifMaximumDrift
        case backboneCAValidity

        var label: String {
            switch self {
            case .plddt: return "pLDDT"
            case .iptm: return "iPTM"
            case .ptm: return "pTM"
            case .interfacePAEMinimum: return "min interface PAE"
            case .ipsaeMinimum: return "ipSAE(min)"
            case .interfacePDE: return "interface PDE"
            case .minimumIPTM: return "minimum iPTM"
            case .meanIPTM: return "mean iPTM"
            case .bindingProbability: return "P(bind)"
            case .rankingScore: return "ranking score"
            case .pocketMeanDistance: return "epitope distance"
            case .pocketFractionWithinCutoff: return "epitope coverage"
            case .complexRMSD: return "binder pose RMSD"
            case .binderBackboneRMSD: return "binder fold RMSD"
            case .binderPLDDT: return "binder pLDDT"
            case .binderRMSD: return "binder-alone RMSD"
            case .motifInsertionRMSD: return "motif placement RMSD"
            case .motifPredictionRMSD: return "predicted motif RMSD"
            case .motifMaximumDrift: return "fixed-atom drift"
            case .backboneCAValidity: return "valid Cα spacing"
            }
        }

        var explanation: String {
            switch self {
            case .plddt: return "Local structural confidence; shown on the conventional 0–100 scale."
            case .iptm: return "Confidence in the relative placement of chains; higher is better."
            case .ptm: return "Confidence in the overall fold; higher is better."
            case .interfacePAEMinimum:
                return "The lowest predicted aligned error across a pair of different chains, in Å. Lower is better."
            case .ipsaeMinimum:
                return "The conservative smaller directional ipSAE score calculated from the engine's PAE. Higher is better."
            case .interfacePDE:
                return "Boltz interface predicted distance error, in Å. This is not relabelled as PAE. Lower is better."
            case .minimumIPTM: return "The weakest iPTM across the verification engines; higher is better."
            case .meanIPTM: return "Mean iPTM across the verification engines; higher is better."
            case .bindingProbability: return "Boltz probability that the small molecule binds; higher is better."
            case .rankingScore: return "The workflow's own score used to order these results."
            case .pocketMeanDistance:
                return "Mean nearest Cα distance from each requested epitope residue to the binder. This reports response to the soft pocket prior; lower is closer."
            case .pocketFractionWithinCutoff:
                return "Fraction of requested epitope residues whose nearest binder Cα is within the recorded Protenix pocket cutoff. This is geometry, not evidence of binding."
            case .complexRMSD:
                return "Cα RMSD of the complex binder to its designed pose after fitting the fixed target. This detects a good fold predicted on the wrong target surface; lower is better."
            case .binderBackboneRMSD:
                return "Cα RMSD of the independently predicted complex binder to the designed backbone after fitting the binder itself. This measures fold recovery without interface placement; lower is better."
            case .binderPLDDT:
                return "Local confidence of the binder predicted without its target. Higher is better."
            case .binderRMSD:
                return "Cα RMSD between binder-alone and complex predictions after fitting the binder. Lower suggests preorganisation."
            case .motifInsertionRMSD:
                return "Atom RMSD used to assign each unindexed source motif token to a generated scaffold residue before the fixed atoms are copied into the output. Lower is better."
            case .motifPredictionRMSD:
                return "RMSD of the explicitly selected motif atoms in an independent sequence prediction after fitting those motif atoms to the generated design. Lower means the functional geometry was recovered."
            case .motifMaximumDrift:
                return "Largest displacement of an explicitly fixed motif atom during RFdiffusion3 sampling. It should remain near zero."
            case .backboneCAValidity:
                return "Percentage of adjacent binder Cα distances between 3.6 and 4.0 Å in the generated backbone."
            }
        }
    }

    let kind: Kind
    let value: Double
    var id: String { kind.rawValue }

    var displayValue: String {
        switch kind {
        case .plddt:
            let conventional = value <= 1.000_001 ? value * 100 : value
            return String(format: "%.1f", conventional)
        case .interfacePAEMinimum, .interfacePDE, .pocketMeanDistance,
             .complexRMSD, .binderBackboneRMSD, .binderRMSD,
             .motifInsertionRMSD, .motifPredictionRMSD, .motifMaximumDrift:
            return String(format: "%.2f Å", value)
        case .binderPLDDT:
            let conventional = value <= 1.000_001 ? value * 100 : value
            return String(format: "%.1f", conventional)
        case .pocketFractionWithinCutoff:
            return String(format: "%.0f%%", value * 100)
        case .backboneCAValidity:
            return String(format: "%.0f%%", value)
        default:
            return String(format: "%.3f", value)
        }
    }
}

/// Reads the durable output formats already written by PredictionController,
/// NanoHunter campaigns and RFdiffusion3 campaigns. It never invents a metric:
/// absent engine output stays absent in the UI.
enum RunResultsLoader {
    private static let fm = FileManager.default

    static func load(root: URL, workflow: StudioWorkflow) -> [StudioResultItem] {
        switch workflow {
        case .prediction: return predictionResults(root: root)
        case .iterative: return iterativeResults(root: root)
        case .rfdiffusion3: return rfd3Results(root: root)
        }
    }

    // MARK: Prediction batches

    private static func predictionResults(root: URL) -> [StudioResultItem] {
        let rows = CSVTable.rows(at: root.appendingPathComponent("predictions.csv"))
        let sequences = predictionSequences(root: root)
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
                let documents = confidenceDocuments(near: structure,
                                                    within: structure.deletingLastPathComponent())
                let metrics = collectMetrics(row: row, documents: documents)
                let suffix = structures.count > 1 ? sampleLabel(for: structure) : nil
                let title = suffix.map { "\(baseTitle) · \($0)" } ?? baseTitle
                return StudioResultItem(
                    id: "\(predictor)|\(title)|\(structure.path)", title: title,
                    subtitle: predictor, structureURL: structure,
                    sequence: job.flatMap { sequences[$0] }, metrics: metrics,
                    confidenceURL: documents.first, stage: .prediction,
                    scoreSource: predictor
                )
            }
        }
    }

    private static func predictionSequences(root: URL) -> [String: String] {
        guard let object = jsonObject(at: root.appendingPathComponent("prediction_config.json")),
              let jobs = object["jobs"] as? [[String: Any]] else { return [:] }
        return Dictionary(uniqueKeysWithValues: jobs.compactMap { job in
            guard let name = job["name"] as? String,
                  let chains = job["chains"] as? [[String: Any]] else { return nil }
            let proteins = chains.compactMap { chain -> String? in
                guard (chain["kind"] as? String) == "protein" else { return nil }
                return chain["sequence"] as? String
            }
            guard !proteins.isEmpty else { return nil }
            return (name, proteins.joined(separator: ":"))
        })
    }

    // MARK: Iterative designs

    private static func iterativeResults(root: URL) -> [StudioResultItem] {
        let rows = iterativeRows(root: root)
        let recordedDesignPredictor = iterativeDesignPredictor(root: root)
        return rows.compactMap { row in
            guard let path = row["structure_path"],
                  let structure = resolvedURL(path, relativeTo: root),
                  fm.fileExists(atPath: structure.path) else { return nil }
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
            return StudioResultItem(
                id: "\(resultStage.rawValue)|\(predictor)|\(run)|\(cycle)|\(structure.path)",
                title: String(format: "Run %02d · cycle %02d", run, cycle),
                subtitle: "\(resultStage.label) · \(predictor)",
                structureURL: structure, sequence: nonempty(row["binder_sequence"]),
                metrics: collectMetrics(row: row, documents: documents),
                confidenceURL: documents.first, stage: resultStage,
                scoreSource: predictor,
                isHit: boolean(row["is_hit"]),
                failedFilters: splitFilters(row["failed_filters"])
            )
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

    private static func rfd3Results(root: URL) -> [StudioResultItem] {
        let ranked = rankedRFD3Results(root: root)
        if !ranked.isEmpty { return ranked }

        // Prediction rows are append-only checkpoints. Prefer them as soon as
        // structures exist, but fall back to raw generated backbones while the
        // predictor stage has not started yet.
        let predicted = liveRFD3Predictions(root: root)
        let backbones = liveRFD3Backbones(root: root)
        return backbones + predicted
    }

    private static func rankedRFD3Results(root: URL) -> [StudioResultItem] {
        let manifest = root.appendingPathComponent("analysis/top100_manifest.json")
        guard let data = try? Data(contentsOf: manifest),
              let rows = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
        else { return [] }

        var results: [StudioResultItem] = []
        for (rankIndex, raw) in rows.enumerated() {
            let row = stringRow(raw)
            let name = nonempty(row["name"]) ?? nonempty(row["design"]) ?? "Design \(rankIndex + 1)"
            let sequence = nonempty(row["sequence"])
            var structures: [(String, String)] = []
            if let map = raw["structures"] as? [String: String] {
                structures = map.sorted { $0.key < $1.key }
            } else if let encoded = raw["structures"] as? String,
                      let data = encoded.data(using: .utf8),
                      let map = try? JSONSerialization.jsonObject(with: data) as? [String: String] {
                structures = map.sorted { $0.key < $1.key }
            } else if let path = nonempty(row["pdb"]) ?? nonempty(row["structure"]) {
                structures = [("Prediction", path)]
            }

            for (predictorKey, path) in structures {
                guard let structure = resolvedURL(path, relativeTo: root),
                      fm.fileExists(atPath: structure.path) else { continue }
                var metricRow = row
                if let value = row["iptm_\(predictorKey)"] { metricRow["iptm"] = value }
                if let value = row["ipsae_min_\(predictorKey)"] { metricRow["ipsae_min"] = value }
                if let values = dictionaryOfDoubles(raw["motif_rmsd_by_predictor"]),
                   let value = values[predictorKey] {
                    metricRow["motif_prediction_rmsd"] = String(value)
                }
                let documents = confidenceDocuments(near: structure, within: structure.deletingLastPathComponent())
                results.append(StudioResultItem(
                    id: "\(rankIndex)|\(predictorKey)|\(structure.path)",
                    title: "#\(rankIndex + 1) · \(name)",
                    subtitle: friendlyPredictor(predictorKey), structureURL: structure,
                    sequence: sequence, metrics: collectMetrics(row: metricRow, documents: documents),
                    confidenceURL: documents.first, stage: .rankedDesign,
                    scoreSource: friendlyPredictor(predictorKey),
                    isHit: boolean(row["is_hit"]),
                    failedFilters: splitFilters(row["failed_filters"]),
                    motifMapping: dictionaryOfStrings(raw["diffused_index_map"])
                        ?? dictionaryOfStrings(row["diffused_index_map"]) ?? [:],
                    motifResidueRMSDs: predictorDictionaryOfDoubles(
                        raw["motif_rmsd_by_residue"], predictor: predictorKey)
                        ?? predictorDictionaryOfDoubles(
                            row["motif_rmsd_by_residue"], predictor: predictorKey) ?? [:]
                ))
            }
        }
        return results
    }

    private static func liveRFD3Predictions(root: URL) -> [StudioResultItem] {
        let rows = CSVTable.rows(at: root.appendingPathComponent("predictions/holo/prediction_metrics.csv"))
        guard !rows.isEmpty else { return [] }
        let sequenceRows = CSVTable.rows(at: root.appendingPathComponent("mpnn/sequences.csv"))
        let sequences = Dictionary(uniqueKeysWithValues: sequenceRows.compactMap { row -> (String, [String: String])? in
            guard let design = nonempty(row["design"]) else { return nil }
            let index = nonempty(row["seq_index"])
            return (index.map { "\(design)_\($0)" } ?? design, row)
        })
        let backboneRows = rfd3BackboneRows(root: root)
        let backboneByDesign = Dictionary(uniqueKeysWithValues: backboneRows.compactMap { row -> (String, [String: String])? in
            nonempty(row["design"]).map { ($0, row) }
        })

        return rows.compactMap { row in
            let succeeded = row["exit_code"] == "0" || row["ok"]?.lowercased() == "true"
            guard succeeded,
                  let path = nonempty(row["structure"]) ?? nonempty(row["pdb"]),
                  let structure = resolvedURL(path, relativeTo: root),
                  fm.fileExists(atPath: structure.path) else { return nil }
            let design = nonempty(row["design"]) ?? nonempty(row["name"]) ?? structure.deletingPathExtension().lastPathComponent
            let source = sequences[design]
            let backboneName = source.flatMap { nonempty($0["design"]) } ?? design.replacingOccurrences(
                of: #"_[0-9]+$"#, with: "", options: .regularExpression)
            let backbone = backboneByDesign[backboneName] ?? [:]
            var metricRow = backbone
            source?.forEach { metricRow[$0.key] = $0.value }
            row.forEach { metricRow[$0.key] = $0.value }
            let predictorKey = nonempty(row["predictor"]) ?? "Prediction"
            let predictor = friendlyPredictor(predictorKey)
            let documents = confidenceDocuments(near: structure, within: structure.deletingLastPathComponent())
            return StudioResultItem(
                id: "live|\(predictorKey)|\(design)|\(structure.path)",
                title: design, subtitle: "Verification arriving · \(predictor)",
                structureURL: structure, sequence: source.flatMap { nonempty($0["sequence"]) },
                metrics: collectMetrics(row: metricRow, documents: documents),
                confidenceURL: documents.first, stage: .verificationPrediction,
                scoreSource: predictor,
                motifMapping: dictionaryOfStrings(backbone["diffused_index_map"]) ?? [:],
                motifResidueRMSDs: dictionaryOfDoubles(backbone["motif_insertion_rmsd_by_token"]) ?? [:]
            )
        }.sorted { $0.title.localizedStandardCompare($1.title) == .orderedAscending }
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
                motifResidueRMSDs: dictionaryOfDoubles(row["motif_insertion_rmsd_by_token"]) ?? [:]
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

        add(.plddt, rowNumber(["complex_plddt", "plddt", "ligand_plddt"]))
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
        return unique.sorted { confidenceRank($0) < confidenceRank($1) }.prefix(4).map { $0 }
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

    private static func resolvedURL(_ path: String, relativeTo root: URL) -> URL? {
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        return trimmed.hasPrefix("/") ? URL(fileURLWithPath: trimmed) : root.appendingPathComponent(trimmed)
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

/// Minimal RFC 4180 reader. RFdiffusion3 stores JSON maps in quoted CSV cells,
/// so splitting on commas would silently attach structures to the wrong design.
private enum CSVTable {
    static func rows(at url: URL) -> [[String: String]] {
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return [] }
        let records = parse(text)
        guard let header = records.first else { return [] }
        return records.dropFirst().filter { !$0.allSatisfy(\.isEmpty) }.map { values in
            Dictionary(uniqueKeysWithValues: header.enumerated().map { index, name in
                (name.trimmingCharacters(in: .whitespacesAndNewlines), index < values.count ? values[index] : "")
            })
        }
    }

    private static func parse(_ text: String) -> [[String]] {
        // Swift treats CRLF as a single extended grapheme cluster, so normalize
        // it before the character state machine looks for line boundaries.
        let text = text.replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")
        var records: [[String]] = []
        var record: [String] = []
        var field = ""
        var quoted = false
        var index = text.startIndex
        while index < text.endIndex {
            let character = text[index]
            if quoted {
                if character == "\"" {
                    let next = text.index(after: index)
                    if next < text.endIndex, text[next] == "\"" {
                        field.append("\"")
                        index = next
                    } else {
                        quoted = false
                    }
                } else {
                    field.append(character)
                }
            } else {
                switch character {
                case "\"": quoted = true
                case ",": record.append(field); field = ""
                case "\n":
                    record.append(field); records.append(record)
                    record = []; field = ""
                case "\r": break
                default: field.append(character)
                }
            }
            index = text.index(after: index)
        }
        if !field.isEmpty || !record.isEmpty { record.append(field); records.append(record) }
        return records
    }
}
