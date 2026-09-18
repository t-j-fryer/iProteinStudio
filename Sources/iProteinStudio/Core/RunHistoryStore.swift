import Foundation
import Combine

enum StudioWorkflow: String, Codable, CaseIterable {
    case iterative
    case nise
    case rfdiffusion3
    case prediction

    var label: String {
        switch self {
        case .iterative: return "Protein Hunter"
        case .nise: return "NISE"
        case .rfdiffusion3: return "RFdiffusion3"
        case .prediction: return "Prediction"
        }
    }

    var systemImage: String {
        switch self {
        case .iterative: return "arrow.triangle.2.circlepath"
        case .nise: return "atom"
        case .rfdiffusion3: return "sparkles"
        case .prediction: return "cube.transparent"
        }
    }
}

enum StudioRunState: String, Codable {
    case running
    case completed
    case failed
    case stopped
    case interrupted

    var label: String {
        switch self {
        case .running: return "Running"
        case .completed: return "Completed"
        case .failed: return "Needs attention"
        case .stopped: return "Stopped"
        case .interrupted: return "Ready to resume"
        }
    }

    var systemImage: String {
        switch self {
        case .running: return "waveform.path"
        case .completed: return "checkmark.circle.fill"
        case .failed: return "exclamationmark.triangle.fill"
        case .stopped: return "stop.circle.fill"
        case .interrupted: return "arrow.clockwise.circle.fill"
        }
    }
}

/// The reproducible launch record written beside every new iterative campaign.
/// It is intentionally independent of AppState's schema so a run can be resumed
/// even if the project form has since changed.
struct StudioRunManifest: Codable {
    var version = 2
    var projectID: UUID
    var projectName: String
    var workflow: StudioWorkflow = .iterative
    var runName: String
    var createdAt: Date = Date()
    var updatedAt: Date = Date()
    var state: StudioRunState = .running
    var arguments: [String]
    var environmentOverrides: [String: String]? = nil
    /// Redundant human-readable budget provenance. The command remains
    /// authoritative; optional fields preserve decoding of older manifests.
    var requestedTrajectories: Int? = nil
    var optimizationCycles: Int? = nil
    var expectedOptimizedDesigns: Int? = nil
    /// Campaign-owned immutable policy/script snapshot. Optional so manifests
    /// written by older versions remain decodable.
    var pipelineSnapshot: String? = nil
    var request: DesignRequest? = nil
    var engineBatchRoot: String? = nil
}


// Keep form restoration separate from the settings relevant to this run. Older
// manifests embedded the entire form under `request`; decode those unchanged.
extension StudioRunManifest {
    private enum CodingKeys: String, CodingKey {
        case version, projectID, projectName, runName, createdAt, updatedAt, state, arguments, environmentOverrides, requestedTrajectories, optimizationCycles, expectedOptimizedDesigns, pipelineSnapshot, engineBatchRoot
        case workflow, request, savedFormState, metadataNote
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        version = try c.decode(Int.self, forKey: .version)
        projectID = try c.decode(UUID.self, forKey: .projectID)
        projectName = try c.decode(String.self, forKey: .projectName)
        runName = try c.decode(String.self, forKey: .runName)
        createdAt = try c.decode(Date.self, forKey: .createdAt)
        updatedAt = try c.decode(Date.self, forKey: .updatedAt)
        state = try c.decode(StudioRunState.self, forKey: .state)
        arguments = try c.decode([String].self, forKey: .arguments)
        environmentOverrides = try c.decodeIfPresent([String: String].self, forKey: .environmentOverrides)
        requestedTrajectories = try c.decodeIfPresent(Int.self, forKey: .requestedTrajectories)
        optimizationCycles = try c.decodeIfPresent(Int.self, forKey: .optimizationCycles)
        expectedOptimizedDesigns = try c.decodeIfPresent(Int.self, forKey: .expectedOptimizedDesigns)
        pipelineSnapshot = try c.decodeIfPresent(String.self, forKey: .pipelineSnapshot)
        engineBatchRoot = try c.decodeIfPresent(String.self, forKey: .engineBatchRoot)
        workflow = try c.decodeIfPresent(StudioWorkflow.self, forKey: .workflow) ?? .iterative
        request = try c.decodeIfPresent(DesignRequest.self, forKey: .savedFormState)
            ?? c.decodeIfPresent(DesignRequest.self, forKey: .request)
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(2, forKey: .version)
        try c.encode(projectID, forKey: .projectID)
        try c.encode(projectName, forKey: .projectName)
        try c.encode(runName, forKey: .runName)
        try c.encode(createdAt, forKey: .createdAt)
        try c.encode(updatedAt, forKey: .updatedAt)
        try c.encode(state, forKey: .state)
        try c.encode(arguments, forKey: .arguments)
        try c.encodeIfPresent(environmentOverrides, forKey: .environmentOverrides)
        try c.encodeIfPresent(requestedTrajectories, forKey: .requestedTrajectories)
        try c.encodeIfPresent(optimizationCycles, forKey: .optimizationCycles)
        try c.encodeIfPresent(expectedOptimizedDesigns, forKey: .expectedOptimizedDesigns)
        try c.encodeIfPresent(pipelineSnapshot, forKey: .pipelineSnapshot)
        try c.encodeIfPresent(engineBatchRoot, forKey: .engineBatchRoot)
        try c.encode(workflow, forKey: .workflow)
        try c.encode("request contains applicable form settings; arguments, environmentOverrides and the saved pipeline define execution. savedFormState restores the UI and includes inactive settings.", forKey: .metadataNote)
        if let request {
            try c.encode(request, forKey: .savedFormState)
            var values = try JSONDecoder().decode([String: RunMetadataValue].self, from: JSONEncoder().encode(request))
            var inactive: Set<String> = ["secondaryStructureBias", "secondaryStructureBiasScope",
                "betaBiasStrength", "betaPatternStrength", "turnLocalizationStrength"]
            if request.designType != .nanobody {
                inactive.formUnion(["scaffoldID", "scaffoldSequence", "scaffoldSelections", "equalScaffoldBudgets", "trajectoriesPerScaffold", "cdrs"])
            } else {
                inactive.formUnion(["binderMinLen", "binderMaxLen", "helixKill"])
            }
            if !request.usesIntelliFold { inactive.insert("intellifoldModel") }
            if !request.hasTargetTemplate {
                inactive.formUnion(["targetTemplatePath", "targetTemplateMode", "targetTemplateThreshold"])
            }
            if request.targetKind == .protein {
                inactive.formUnion(values.keys.filter { $0.hasPrefix("ligand") })
                inactive.insert("targetSmiles")
            } else {
                inactive.formUnion(["targetSequence", "epitopeResidues"])
            }
            if request.effectivePostPredictors.isEmpty {
                inactive.formUnion(values.keys.filter { $0.hasPrefix("post") && $0 != "postPredictors" })
            }
            if request.targetKind != .ligand || !request.nesso.enabled { inactive.insert("nesso") }
            for key in inactive { values.removeValue(forKey: key) }
            try c.encode(values, forKey: .request)
        }
    }
}

/// Lossless JSON value used only to project already-typed request metadata.
private indirect enum RunMetadataValue: Codable {
    case null, bool(Bool), number(Double), string(String)
    case array([RunMetadataValue]), object([String: RunMetadataValue])
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(Double.self) { self = .number(v) }
        else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode([RunMetadataValue].self) { self = .array(v) }
        else { self = .object(try c.decode([String: RunMetadataValue].self)) }
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .null: try c.encodeNil()
        case .bool(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .string(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .object(let v): try c.encode(v)
        }
    }
}

struct StudioRunRecord: Identifiable, Hashable {
    var id: String { root.path }
    var projectID: UUID
    var projectName: String
    var workflow: StudioWorkflow
    var name: String
    var root: URL
    var date: Date
    var state: StudioRunState
    var detail: String
    var manifestURL: URL?
    var managedJobID: String? = nil
    var hasViewableResults: Bool

    var isResumable: Bool {
        (managedJobID != nil || (workflow == .iterative && manifestURL != nil))
            && (state == .interrupted || state == .failed || state == .stopped)
    }
}

/// Rebuilds project history from durable outputs rather than an in-memory list.
/// Old runs created before Studio wrote manifests remain visible; new iterative
/// runs additionally expose exact-command Resume.
@MainActor
final class RunHistoryStore: ObservableObject {
    @Published private(set) var runs: [StudioRunRecord] = []

    private var refreshTask: Task<Void, Never>?
    private var generation = 0

    func refresh(projects: [Project]) {
        generation += 1
        let expected = generation
        refreshTask?.cancel()
        let jobs = JobCenter.shared.jobs
        refreshTask = Task {
            let found = await Task.detached(priority: .utility) {
                RunHistoryLoader().load(projects: projects, jobs: jobs)
            }.value
            guard !Task.isCancelled, expected == generation else { return }
            runs = found
        }
    }

    func runs(for project: Project) -> [StudioRunRecord] {
        runs.filter { $0.projectID == project.id }
    }
}

/// Filesystem discovery runs away from the UI actor; controllers publish only
/// completed snapshots, so tab changes cannot apply an obsolete scan.
private struct RunHistoryLoader {
    func load(projects: [Project], jobs: [ManagedJob]) -> [StudioRunRecord] {
        var found: [StudioRunRecord] = []
        for project in projects {
            let root = AppPaths.projects.appendingPathComponent(project.slug)
            found += batchRuns(project: project, root: root)
            found += iterativeRuns(project: project, root: root)
            found += predictionRuns(project: project, root: root)
            found += rfd3Runs(project: project, root: root)
            found += niseRuns(project: project, root: root)
        }
        return found.map { item in
            var item = item
            if let job = jobs.first(where: {
                $0.output?.standardizedFileURL == item.root.standardizedFileURL
                    || ($0.child_outputs ?? []).contains(item.root.path)
            }) {
                // A completed engine stays completed if a later engine fails.
                if job.child_outputs?.contains(item.root.path) == true && item.state == .completed { return item }
                item.managedJobID = job.id
                if job.child_outputs?.contains(item.root.path) == true && job.active_output != item.root.path {
                    item.state = job.isActive ? .running : .interrupted
                    item.detail = job.isActive ? "Queued in this engine batch" : "Not started; resume the engine batch to continue"
                    return item
                }
                item.detail = job.message ?? item.detail
                switch job.status {
                case "queued", "running", "stopping": item.state = .running
                case "completed": item.state = .completed
                case "cancelled": item.state = .stopped
                default: item.state = .failed
                }
            } else { item.managedJobID = BrokerClient.savedJobID(at: item.root) }
            return item
        }.sorted { $0.date > $1.date }
    }

    private func batchRuns(project: Project, root: URL) -> [StudioRunRecord] {
        directories(in: root).compactMap { batch in
            guard let descriptor = json(at: batch.appendingPathComponent("studio_engine_batch.json")),
                  let paths = descriptor["campaigns"] as? [String], !paths.isEmpty else { return nil }
            let children = paths.map { root.appendingPathComponent(URL(fileURLWithPath: $0).lastPathComponent) }
            let completion = json(at: batch.appendingPathComponent("engine_batch_progress.json"))?["completed"] as? [String: Any]
            let completed = completion?.count ?? children.filter { child in
                (json(at: child.appendingPathComponent("studio_run.json"))?["state"] as? String) == "completed"
            }.count
            let viewable = children.contains { csvRowCount($0.appendingPathComponent("summary_all_runs.csv")) > 0 }
            return StudioRunRecord(projectID: project.id, projectName: project.name, workflow: .iterative,
                name: RunNaming.read(at: batch, fallback: "Combined framework / engine batch"),
                root: batch, date: fileDate(batch), state: completed == paths.count ? .completed : .interrupted,
                detail: "\(completed)/\(paths.count) campaigns complete · all framework results",
                manifestURL: nil, managedJobID: BrokerClient.savedJobID(at: batch), hasViewableResults: viewable)
        }
    }

    private func iterativeRuns(project: Project, root: URL) -> [StudioRunRecord] {
        let ignored = Set(["predictions", "prediction_runs", "prediction_input", "rfd3",
                           "rfd3_runs", "nise_runs", "target_prep", "ligand", "rfd3_assets", "config"])
        let children = directories(in: root).filter { !ignored.contains($0.lastPathComponent) }
        return children.compactMap { candidate in
            let manifestURL = candidate.appendingPathComponent("studio_run.json")
            let manifest = decode(StudioRunManifest.self, at: manifestURL)
            let runDirs = directories(in: candidate).filter { $0.lastPathComponent.hasPrefix("run_") }
            guard manifest != nil || !runDirs.isEmpty
                    || AppPaths.fm.fileExists(atPath: candidate.appendingPathComponent("summary_all_runs.csv").path)
            else { return nil }

            let exitCodes = runDirs.compactMap { dir -> Int? in
                let url = dir.appendingPathComponent("run_exit_code.txt")
                guard let text = try? String(contentsOf: url, encoding: .utf8) else { return nil }
                return Int(text.trimmingCharacters(in: .whitespacesAndNewlines))
            }
            let state: StudioRunState
            if let manifest, manifest.state != .running {
                state = manifest.state
            } else if exitCodes.contains(where: { $0 != 0 }) {
                state = .failed
            } else if !runDirs.isEmpty && exitCodes.count == runDirs.count {
                state = .completed
            } else {
                state = .interrupted
            }
            let engineLabel = manifest?.request?.designEngineSummary
            let detail = (engineLabel.map { $0 + " · " } ?? "") + (runDirs.isEmpty ? "Campaign settings saved"
                : "\(exitCodes.filter { $0 == 0 }.count) of \(runDirs.count) design units completed")
            let recordedResults = csvRowCount(candidate.appendingPathComponent("comparison_scores_long.csv"))
                + csvRowCount(candidate.appendingPathComponent("summary_all_runs.csv"))
                + runDirs.reduce(0) { partial, directory in
                    partial + csvRowCount(directory.appendingPathComponent("metrics_per_cycle.csv"))
                        + directories(in: directory).filter { $0.lastPathComponent.hasPrefix("post_") }
                            .reduce(0) { postTotal, postRoot in
                                postTotal + directories(in: postRoot).reduce(0) { cycleTotal, cycleRoot in
                                    cycleTotal + csvRowCount(cycleRoot.appendingPathComponent("post_metrics_row.csv"))
                                }
                            }
                }
            return StudioRunRecord(projectID: project.id, projectName: project.name,
                                   workflow: .iterative,
                                   name: RunNaming.read(at: candidate, fallback: manifest?.runName ?? candidate.lastPathComponent),
                                   root: candidate,
                                   date: manifest?.createdAt ?? fileDate(candidate), state: state,
                                   detail: detail,
                                   manifestURL: manifest == nil ? nil : manifestURL,
                                   hasViewableResults: recordedResults > 0)
        }
    }

    private func niseRuns(project: Project, root: URL) -> [StudioRunRecord] {
        directories(in: root.appendingPathComponent("nise_runs")).compactMap { candidate in
            let config = candidate.appendingPathComponent("nise_config.json")
            guard AppPaths.fm.fileExists(atPath: config.path) else { return nil }
            let summary = json(at: candidate.appendingPathComponent("summary.json"))
            let completed = summary?["status"] as? String == "completed"
            let count = (try? AppPaths.fm.contentsOfDirectory(atPath: candidate.appendingPathComponent("candidates").path))?.filter { $0.hasSuffix(".json") }.count ?? 0
            return StudioRunRecord(projectID: project.id, projectName: project.name,
                                   workflow: .nise, name: RunNaming.read(at: candidate, fallback: candidate.lastPathComponent),
                                   root: candidate, date: fileDate(candidate), state: completed ? .completed : .interrupted,
                                   detail: count > 0 ? "\(count) evaluated candidates · phase progress available" : "Preparation · view live stage progress",
                                   manifestURL: config, hasViewableResults: true)
        }
    }

    private func predictionRuns(project: Project, root: URL) -> [StudioRunRecord] {
        var candidates = directories(in: root.appendingPathComponent("prediction_runs"))
        let legacy = root.appendingPathComponent("predictions", isDirectory: true)
        if AppPaths.fm.fileExists(atPath: legacy.path) { candidates.append(legacy) }
        return candidates.compactMap { candidate in
            let config = candidate.appendingPathComponent("prediction_config.json")
            guard AppPaths.fm.fileExists(atPath: config.path) else { return nil }
            let summaryURL = candidate.appendingPathComponent("run_summary.json")
            let summary = json(at: summaryURL)
            let failures = summary?["failures"] as? Int
                ?? summary?["num_failures"] as? Int ?? 0
            let completed = summary != nil
            let state: StudioRunState = completed ? (failures == 0 ? .completed : .failed) : .interrupted
            let results = summary?["results"] as? Int
                ?? summary?["num_results"] as? Int
                ?? csvRowCount(candidate.appendingPathComponent("predictions.csv"))
            return StudioRunRecord(projectID: project.id, projectName: project.name,
                                   workflow: .prediction, name: RunNaming.read(at: candidate, fallback: candidate.lastPathComponent),
                                   root: candidate, date: fileDate(candidate), state: state,
                                   detail: completed ? "\(results) result(s), \(failures) failed" : "Settings saved; no final summary",
                                   manifestURL: nil, hasViewableResults: results > 0)
        }
    }

    private func rfd3Runs(project: Project, root: URL) -> [StudioRunRecord] {
        var candidates = directories(in: root.appendingPathComponent("rfd3_runs"))
        let legacy = root.appendingPathComponent("rfd3", isDirectory: true)
        if AppPaths.fm.fileExists(atPath: legacy.appendingPathComponent("config/campaign.json").path) {
            candidates.append(legacy)
        }
        return candidates.compactMap { candidate in
            let config = candidate.appendingPathComponent("config/campaign.json")
            guard AppPaths.fm.fileExists(atPath: config.path) else { return nil }
            let progress = json(at: candidate.appendingPathComponent("campaign_progress.json"))
            let completed = progress?["completed_stages"] as? [String] ?? []
            let current = progress?["current_stage"] as? String
            let pidAlive = processIsAlive(candidate.appendingPathComponent("campaign.pid"))
            let hasResults = AppPaths.fm.fileExists(atPath: candidate.appendingPathComponent("analysis/top100.csv").path)
            // Results are useful before final ranking: RFdiffusion3 checkpoints
            // accepted backbones and verification predictions incrementally.
            let hasViewableResults = AppPaths.fm.fileExists(
                atPath: candidate.appendingPathComponent("analysis/top100_manifest.json").path)
                || hasStructure(in: candidate.appendingPathComponent("rfd3"))
                || hasStructure(in: candidate.appendingPathComponent("predictions/holo"))
            let state: StudioRunState
            if pidAlive { state = .running }
            else if hasResults || completed.contains("score") || completed.contains("rmsd") { state = .completed }
            else if current != nil { state = .interrupted }
            else { state = .failed }
            let detail = hasResults
                ? "\(csvRowCount(candidate.appendingPathComponent("analysis/top100.csv"))) ranked result(s)"
                : (current.map { "Stopped during \($0)" }
                   ?? (completed.isEmpty ? "Campaign configured" : "Completed: \(completed.joined(separator: ", "))"))
            return StudioRunRecord(projectID: project.id, projectName: project.name,
                                   workflow: .rfdiffusion3, name: RunNaming.read(at: candidate, fallback: candidate.lastPathComponent),
                                   root: candidate, date: fileDate(candidate), state: state,
                                   detail: detail, manifestURL: nil,
                                   hasViewableResults: hasViewableResults)
        }
    }

    /// Stop at the first structure rather than parsing an entire active
    /// campaign merely to decide whether the Results button should be shown.
    private func hasStructure(in root: URL) -> Bool {
        guard let iterator = AppPaths.fm.enumerator(
            at: root, includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]) else { return false }
        while let url = iterator.nextObject() as? URL {
            if ["pdb", "cif", "mmcif", "bcif"].contains(url.pathExtension.lowercased()) {
                return true
            }
        }
        return false
    }

    private func directories(in root: URL) -> [URL] {
        (try? AppPaths.fm.contentsOfDirectory(at: root,
            includingPropertiesForKeys: [.isDirectoryKey], options: [.skipsHiddenFiles]))?
            .filter { (try? $0.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true } ?? []
    }

    private func fileDate(_ url: URL) -> Date {
        let values = try? url.resourceValues(forKeys: [.contentModificationDateKey, .creationDateKey])
        return values?.contentModificationDate ?? values?.creationDate ?? .distantPast
    }

    private func decode<T: Decodable>(_ type: T.Type, at url: URL) -> T? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(type, from: data)
    }

    private func json(at url: URL) -> [String: Any]? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    }

    private func csvRowCount(_ url: URL) -> Int {
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return 0 }
        return max(0, text.split(whereSeparator: \.isNewline).count - 1)
    }

    private func processIsAlive(_ pidURL: URL) -> Bool {
        guard let text = try? String(contentsOf: pidURL, encoding: .utf8),
              let pid = Int32(text.trimmingCharacters(in: .whitespacesAndNewlines)), pid > 1
        else { return false }
        return kill(pid, 0) == 0
    }
}
