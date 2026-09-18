import Foundation
import CryptoKit

/// Presentation of committed NISE records. Never runs checks or changes the search.
enum NISEPhase: Int, CaseIterable, Identifiable {
    case preparation, optimisation, finalChecks
    var id: Int { rawValue }
    var label: String {
        switch self {
        case .preparation: return "Phase 0 · Preparation"
        case .optimisation: return "Phase 1 · Optimisation"
        case .finalChecks: return "Final checks"
        }
    }
    var explanation: String {
        switch self {
        case .preparation: return "Initial backbones → pocket refinement → unrestrained geometry gate → diverse seed expansion. Browse by stage and original lineage."
        case .optimisation: return "Independent trajectories expand and select their own parent beams. A passing candidate is not necessarily selected for the next cycle."
        case .finalChecks: return "Apo/holo preorganisation checks on the final shortlist. These are computed assessments, not experimentally confirmed hits."
        }
    }
}

struct NISERecord: Identifiable {
    let item: StudioResultItem
    let phase: NISEPhase
    let cycle: Int
    let geometryPassed: Bool?
    let eligible: Bool?
    let advanced: Bool?
    var id: String { item.id }
    var stageID: String { "\(phase.rawValue)|\(cycle)" }
}

struct NISEStageProgress: Identifiable {
    let phase: NISEPhase
    let cycle: Int
    let title: String
    var planned: Int?
    var completed = 0
    var geometryPassed = 0
    var geometryFailed = 0
    var awaitingChecks = 0
    var eligible = 0
    var selected = 0
    var screened = 0
    var shortlisted = 0
    var id: String { "\(phase.rawValue)|\(cycle)" }
    var progressLabel: String {
        if let planned { return "\(completed) / \(planned) structures" }
        return completed == 0 ? (screened > 0 ? "Screening · awaiting folds" : "No completed structures yet") : "\(completed) structures"
    }
}

struct NISESnapshot {
    var records: [NISERecord] = []
    var stages: [NISEStageProgress] = []
    var warnings: [String] = []
    var screening: [NISEScreeningRecord] = []
    var items: [StudioResultItem] { records.map(\.item) }
}

struct NISEScreeningRecord: Identifiable {
    let name: String
    let phase: NISEPhase
    let cycle: Int
    let sequence: String
    let metrics: [StudioResultMetric]
    let selected: Bool?
    let rejection: String?
    let receipt: URL
    var stageID: String { "\(phase.rawValue)|\(cycle)" }
    var id: String { stageID + "|" + name }
}

enum NISEResultsLoader {
    private static let fm = FileManager.default
    private static func object(_ url: URL) -> [String: Any]? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }
    private static func children(_ url: URL) -> [URL] {
        ((try? fm.contentsOfDirectory(at: url, includingPropertiesForKeys: [.isDirectoryKey], options: [.skipsHiddenFiles])) ?? [])
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
    }
    private static func number(_ text: String, prefix: String) -> Int? {
        guard text.hasPrefix(prefix) else { return nil }
        return Int(text.dropFirst(prefix.count))
    }
    private static func trajectory(_ name: String) -> Int? {
        name.split(separator: "_").compactMap { number(String($0), prefix: "t") }.first
    }

    static func load(root: URL) -> NISESnapshot {
        let root = root.standardizedFileURL.resolvingSymlinksInPath()
        let settings = object(root.appendingPathComponent("config.json"))
            ?? (object(root.appendingPathComponent("nise_config.json"))?["request"] as? [String: Any]) ?? [:]
        let refinements = max(0, min(100, settings["phase0_refine_cycles"] as? Int ?? 2))
        var snapshot = NISESnapshot()
        var rows: [String: [String: Any]] = [:]
        var rowFiles: [String: URL] = [:]
        var stages: [String: NISEStageProgress] = [:]
        var invalidRecords = 0
        var screeningScores: [String: (sequence: String, values: [String: Any])] = [:]
        // Accept historical absolute references only when they resolve inside this run.
        // Copied receipts relocate using their explicit, relative artifact inventory.
        func artifact(_ path: String, inventory: [String: Any] = [:]) -> URL? {
            let direct = path.hasPrefix("/") ? URL(fileURLWithPath: path) : root.appendingPathComponent(path)
            func safe(_ url: URL) -> URL? {
                let value = url.standardizedFileURL.resolvingSymlinksInPath()
                guard value.path.hasPrefix(root.path + "/"),
                      (try? value.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true else { return nil }
                return value
            }
            if let value = safe(direct) { return value }
            guard path.hasPrefix("/") else { return nil }
            let matches = inventory.keys.filter { !$0.hasPrefix("/") && path.hasSuffix("/" + $0) }
            guard matches.count == 1 else { return nil }
            return safe(root.appendingPathComponent(matches[0]))
        }
        func stage(_ phase: NISEPhase, _ cycle: Int) -> String {
            let key = "\(phase.rawValue)|\(cycle)"
            if stages[key] == nil {
                let title: String
                if phase == .preparation {
                    if cycle == 0 { title = "Initial backbones" }
                    else if cycle <= refinements { title = "Pocket refinement \(cycle)" }
                    else if cycle == refinements + 1 { title = "Unrestrained geometry gate" }
                    else { title = "Seed expansion" }
                } else if phase == .optimisation { title = "Optimisation cycle \(cycle)" }
                else { title = "Apo/holo shortlist" }
                stages[key] = NISEStageProgress(phase: phase, cycle: cycle, title: title)
            }
            return key
        }
        for cycle in 0...(refinements + 2) { _ = stage(.preparation, cycle) }
        stages["0|0"]?.planned = settings["num_starts"] as? Int

        // Candidate records supersede fold receipts without changing their identity.
        for file in children(root.appendingPathComponent("candidates")) where file.pathExtension == "json" {
            guard let row = object(file), let name = row["name"] as? String else { invalidRecords += 1; continue }
            rows[name] = row; rowFiles[name] = file
        }
        let candidateNames = Set(rows.keys)
        var provenance: [String: (NISEPhase, Int)] = [:]
        var selection: [String: Bool] = [:]
        let initial = object(root.appendingPathComponent("phase0/cycle00/initial_geometry.json")) ?? [:]
        let initialPassed = initial["passed"] as? [String: Bool] ?? [:]
        let initialAtoms = initial["atom_checks"] as? [String: Any] ?? [:]
        var scannedDirectories = Set<String>()

        // Walk only journal locations; never traverse native tensor caches or batch
        // copies. An incomplete output has no completed.json and is not displayed.
        func scan(_ directory: URL, phase: NISEPhase, cycle: Int, depth: Int = 0) {
            guard depth < 9 else { return }
            let key = stage(phase, cycle)
            let resolved = directory.resolvingSymlinksInPath()
            guard resolved.path.hasPrefix(root.path + "/") else { return }
            guard scannedDirectories.insert(resolved.path).inserted else { return }
            let completedURL = directory.appendingPathComponent("completed.json")
            let savedReceipt = object(completedURL)
            if fm.fileExists(atPath: completedURL.path), savedReceipt == nil {
                invalidRecords += 1
                return
            }
            if let receipt = savedReceipt,
               let result = receipt["result"] as? [String: Any],
               let prediction = result["prediction"] as? [String: Any],
               let name = prediction["name"] as? String, let path = prediction["pdb"] as? String {
                provenance[name] = (phase, cycle)
                if rows[name] == nil {
                    guard let structure = artifact(path, inventory: receipt["files"] as? [String: Any] ?? [:]) else {
                        invalidRecords += 1; return
                    }
                    let input = receipt["input"] as? [String: Any] ?? [:]
                    var row = prediction
                    row["name"] = name; row["pdb"] = structure.path
                    row["sequence"] = input["sequence"]; row["cycle"] = cycle
                    // Complete-phase receipts may already have affinity. Structure-only
                    // receipts must not be assigned an invented score or pass verdict.
                    row["score_status"] = "awaiting_checks"
                    rows[name] = row; rowFiles[name] = directory.appendingPathComponent("completed.json")
                }
                // Affinity can commit before the surrounding score batch finishes.
                // Bind it to this exact structure receipt, not just a candidate name.
                if let affinity = object(directory.appendingPathComponent("affinity_completed.json")),
                   let spec = affinity["input"] as? [String: Any],
                   let data = try? Data(contentsOf: completedURL),
                   spec["structure_receipt_sha256"] as? String == SHA256.hash(data: data).map({ String(format: "%02x", $0) }).joined(),
                   let scored = (affinity["result"] as? [String: Any])?["prediction"] as? [String: Any],
                   scored["name"] as? String == name,
                   let pbind = scored["pbind"] as? Double, pbind.isFinite {
                    rows[name]?["pbind"] = pbind
                }
                return
            }
            let file = directory.appendingPathComponent("selection.json")
            if directory.lastPathComponent == "nesso" {
                let receipt = object(file)
                let input = receipt?["input"] as? [String: Any] ?? [:]
                let selected = (receipt?["result"] as? [String]).map(Set.init)
                let assessments = input["assessments"] as? [String: [String: Any]] ?? [:]
                var savedScores = input["scores"] as? [String: [String: Any]] ?? [:]
                var sequences = input["sequences"] as? [String: String] ?? [:]
                var receipts: [String: URL] = [:]
                for unit in children(directory) {
                    let path = unit.appendingPathComponent("completed.json")
                    guard path.resolvingSymlinksInPath().path.hasPrefix(root.path + "/") else { invalidRecords += 1; continue }
                    guard let saved = object(path), let result = saved["result"] as? [String: Any],
                          let scores = result["scores"] as? [String: Any],
                          let spec = saved["input"] as? [String: Any], let sequence = spec["sequence"] as? String else { continue }
                    let name = unit.lastPathComponent
                    if savedScores[name] == nil { savedScores[name] = scores; sequences[name] = sequence }
                    receipts[name] = path
                }
                for (name, raw) in savedScores {
                    guard let sequence = sequences[name] else { continue }
                    var values = raw
                    // Display the recorded assessment; never recompute old policies.
                    if let score = assessments[name]?["score"] { values["screening_score"] = score }
                    screeningScores[name] = (sequence, values)
                    snapshot.screening.append(NISEScreeningRecord(name: name, phase: phase, cycle: cycle,
                        sequence: sequence, metrics: metrics(["nesso": values]), selected: selected.map { $0.contains(name) },
                        rejection: assessments[name]?["rejection_reason"] as? String, receipt: receipts[name] ?? file))
                }
                stages[key]?.screened += max(savedScores.count, selected == nil ? 0 : sequences.count)
                stages[key]?.shortlisted += selected?.count ?? 0
                return
            }
            for child in children(directory) {
                let name = child.lastPathComponent
                if ["out", "yaml", "design", "rfd3", "sessions"].contains(name) || name.hasPrefix("_") || name.hasPrefix("interrupted") { continue }
                if (try? child.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true {
                    scan(child, phase: phase, cycle: cycle, depth: depth + 1)
                }
            }
            // Per-input directories exist before inference; count the unique requested
            // identifiers, including pending work. Top-up directories are additive.
            if directory.lastPathComponent == "fold" {
                let count = children(directory).filter {
                    !$0.lastPathComponent.hasPrefix("_") && (try? $0.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true
                }.count
                if count > 0 {
                    let total = (stages[key]?.planned ?? 0) + count
                    stages[key]?.planned = total
                }
            }
        }
        let phase0 = root.appendingPathComponent("phase0")
        for directory in children(phase0) {
            if let cycle = number(directory.lastPathComponent, prefix: "cycle") { scan(directory, phase: .preparation, cycle: cycle) }
        }
        for directory in children(root) {
            guard let cycle = number(directory.lastPathComponent, prefix: "cycle") else { continue }
            scan(directory, phase: .optimisation, cycle: cycle)
            if let advancement = object(directory.appendingPathComponent("advancement.json")),
               let trajectories = advancement["trajectories"] as? [[String: Any]] {
                for trajectory in trajectories {
                    let selected = Set(trajectory["selected"] as? [String] ?? [])
                    let tid = trajectory["trajectory"] as? Int
                    for (name, row) in rows where (row["cycle"] as? Int) == cycle && (row["trajectory"] as? Int ?? self.trajectory(name)) == tid {
                        selection[name] = selected.contains(name)
                    }
                }
            }
        }
        // RFdiffusion3 generation uses one atomic receipt for its completed set.
        let rfdReceipt = phase0.appendingPathComponent("cycle00/initial_backbones.json")
        if let receipt = object(rfdReceipt), let paths = receipt["result"] as? [String: String] {
            for (name, path) in paths {
                guard artifact(path) != nil else { invalidRecords += 1; continue }
                if rows[name] == nil {
                    rows[name] = ["name": name, "pdb": path, "cycle": 0, "generator": "RFdiffusion3"]
                    rowFiles[name] = rfdReceipt; provenance[name] = (.preparation, 0)
                }
            }
        }
        let preorg = object(root.appendingPathComponent("preorg.json"))?["ranked"] as? [[String: Any]] ?? []
        let apoByName = Dictionary(preorg.compactMap { row -> (String, [String: Any])? in
            guard let name = row["name"] as? String else { return nil }; return (name, row)
        }, uniquingKeysWith: { _, last in last })

        for name in rows.keys.sorted() {
            guard var row = rows[name], let path = row["pdb"] as? String, let structure = artifact(path) else {
                invalidRecords += 1; continue
            }
            if row["nesso"] == nil, let screening = screeningScores[name], row["sequence"] as? String == screening.sequence {
                row["nesso"] = screening.values
            }
            let tid = row["trajectory"] as? Int ?? trajectory(name)
            let phase = provenance[name]?.0 ?? (tid == nil ? .preparation : .optimisation)
            let cycle = provenance[name]?.1 ?? row["cycle"] as? Int ?? 0
            let key = stage(phase, cycle)
            let isInitial = phase == .preparation && cycle == 0
            let geometry = isInitial ? initialPassed[name] : (row["geometry_passed"] as? Bool ?? row["passed"] as? Bool)
            let status = row["score_status"] as? String
            let eligible = isInitial ? initialPassed[name] :
                (["not_evaluated", "awaiting_checks"].contains(status ?? "") && row["geometry_passed"] as? Bool != false ? nil : row["passed"] as? Bool)
            var label = geometry.map { $0 ? "Passed geometry checks" : "Did not pass geometry checks" } ?? "Fold complete · awaiting geometry checks"
            if isInitial, geometry == true { label = "Initial geometry passed · affinity not required" }
            if geometry == true, !isInitial {
                switch status {
                case "below_early_score_gate": label = "Below first-refinement score gate"
                case "score_upper_bound_below_selection_boundary": label = "Affinity skipped · cannot enter selection"
                case "omitted_geometry_only_stage": label = "Geometry gate passed · affinity not required"
                case "not_evaluated": label = "Geometry passed · awaiting scoring decision"
                default: if eligible == true { label = "Eligible after recorded checks" }
                }
            }
            if selection[name] == true { label = "Selected for the next cycle" }
            else if selection[name] == false, eligible == true { label += " · not selected for next cycle" }
            let branch = row["branch"] as? String ?? "mpnn"
            let branchLabel = isInitial ? (row["generator"] as? String ?? "Protein Hunter start") :
                (branch == "masked-backbone" ? "Masked backbone · intermediate" : (branch == "partial-noising-repair" ? "Partial-noising redesign" : "MPNN"))
            let lineage = String(name.split(separator: "_").first ?? Substring(name))
            let groupTitle = tid.map { "Trajectory \($0 + 1)" } ?? "Lineage \(lineage)"
            let groupID = "nise|\(phase.rawValue)|" + (tid.map(String.init) ?? lineage)
            let metrics = metrics(row)
            let item = StudioResultItem(id: "nise|\(name)|holo", title: name,
                subtitle: "\(stages[key]!.title) · \(branchLabel) · \(label)", structureURL: structure,
                sequence: row["sequence"] as? String, metrics: metrics, confidenceURL: rowFiles[name],
                stage: isInitial ? .startingStructure : .design,
                scoreSource: row["generator"] as? String ?? (row["nesso"] == nil ? "Boltz 2" : "Boltz 2 · NESSO prescreen"),
                failedFilters: ((row["atom_checks"] as? [String: Any] ?? initialAtoms[name] as? [String: Any])?["failures"] as? [String]) ?? [],
                groupID: groupID, groupTitle: groupTitle, variantID: "cycle-\(cycle)-\(name)",
                variantTitle: "Cycle \(cycle) · \(name)", artifactRole: isInitial ? .startingStructure : .designedComplex)
            snapshot.records.append(NISERecord(item: item, phase: phase, cycle: cycle, geometryPassed: geometry,
                eligible: candidateNames.contains(name) || isInitial ? eligible : nil, advanced: selection[name]))
            stages[key]?.completed += 1
            if geometry == true { stages[key]?.geometryPassed += 1 }
            else if geometry == false { stages[key]?.geometryFailed += 1 }
            else { stages[key]?.awaitingChecks += 1 }
            if eligible == true { stages[key]?.eligible += 1 }
            if selection[name] == true { stages[key]?.selected += 1 }
            if let check = apoByName[name] {
                guard let path = check["apo_pdb"] as? String, let apo = artifact(path) else {
                    invalidRecords += 1
                    continue
                }
                let finalKey = stage(.finalChecks, 0)
                let apoMetrics: [StudioResultMetric] = [("preorg_rmsd", StudioResultMetric.Kind.pocketPreorgRMSD), ("global_ca_rmsd", .binderRMSD), ("combined_score", .preorgScore)].compactMap { key, kind in
                    guard let v = check[key] as? Double, v.isFinite else { return nil }; return .init(kind: kind, value: v)
                }
                let apoItem = StudioResultItem(id: "nise|\(name)|apo", title: name + " · apo", subtitle: "Final shortlist · ligand removed",
                    structureURL: apo, sequence: item.sequence, metrics: apoMetrics, confidenceURL: root.appendingPathComponent("preorg.json"),
                    stage: .design, scoreSource: "Boltz 2 apo / beta preorganisation", groupID: groupID, groupTitle: groupTitle,
                    variantID: item.variantID, variantTitle: item.variantTitle, artifactRole: .binderAlone)
                snapshot.records.append(NISERecord(item: apoItem, phase: .finalChecks, cycle: 0, geometryPassed: nil, eligible: nil, advanced: nil))
                stages[finalKey]?.completed += 1
            }
        }
        snapshot.stages = stages.values.sorted { ($0.phase.rawValue, $0.cycle) < ($1.phase.rawValue, $1.cycle) }
        snapshot.screening.sort { $0.id.localizedStandardCompare($1.id) == .orderedAscending }
        if invalidRecords > 0 { snapshot.warnings.append("\(invalidRecords) saved records could not be displayed because their metadata or structure files are missing, unreadable or outside this run. Use Reveal Run to inspect them.") }
        return snapshot
    }

    private static func metrics(_ row: [String: Any]) -> [StudioResultMetric] {
        let mappings: [(String, StudioResultMetric.Kind)] = [("ligand_plddt", .ligandPLDDT), ("pbind", .bindingProbability),
            ("score", .rankingScore), ("ca_rmsd", .binderBackboneRMSD), ("ligand_rmsd", .ligandRMSD), ("complex_plddt", .plddt), ("iptm", .iptm)]
        var values = mappings.compactMap { key, kind -> StudioResultMetric? in
            guard let value = row[key] as? Double, value.isFinite else { return nil }; return .init(kind: kind, value: value)
        }
        if let nesso = row["nesso"] as? [String: Any] {
            for (key, kind) in [("affinity_probability_binary", StudioResultMetric.Kind.nessoBindingProbability), ("affinity_pred_value", .nessoAffinity), ("entropy_pl", .nessoPlacementEntropy), ("entropy_crop_pl", .nessoInterfaceEntropy), ("screening_score", .nessoScreeningScore)] {
                if let value = nesso[key] as? Double, value.isFinite { values.append(.init(kind: kind, value: value)) }
            }
        }
        return values
    }
}
