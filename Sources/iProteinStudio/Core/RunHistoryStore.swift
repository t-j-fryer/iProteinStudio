import Foundation
import Combine

enum StudioWorkflow: String, Codable, CaseIterable {
    case iterative
    case rfdiffusion3
    case prediction

    var label: String {
        switch self {
        case .iterative: return "Iterative design"
        case .rfdiffusion3: return "RFdiffusion3"
        case .prediction: return "Prediction"
        }
    }

    var systemImage: String {
        switch self {
        case .iterative: return "arrow.triangle.2.circlepath"
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
    var version = 1
    var projectID: UUID
    var projectName: String
    var workflow: StudioWorkflow = .iterative
    var runName: String
    var createdAt: Date = Date()
    var updatedAt: Date = Date()
    var state: StudioRunState = .running
    var arguments: [String]
    var environmentOverrides: [String: String]? = nil
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
    var hasViewableResults: Bool

    var isResumable: Bool {
        workflow == .iterative && manifestURL != nil
            && (state == .interrupted || state == .failed || state == .stopped)
    }
}

/// Rebuilds project history from durable outputs rather than an in-memory list.
/// Old runs created before Studio wrote manifests remain visible; new iterative
/// runs additionally expose exact-command Resume.
@MainActor
final class RunHistoryStore: ObservableObject {
    @Published private(set) var runs: [StudioRunRecord] = []

    func refresh(projects: [Project]) {
        var found: [StudioRunRecord] = []
        for project in projects {
            let root = AppPaths.projectDir(project)
            found += iterativeRuns(project: project, root: root)
            found += predictionRuns(project: project, root: root)
            found += rfd3Runs(project: project, root: root)
        }
        runs = found.sorted { $0.date > $1.date }
    }

    func runs(for project: Project) -> [StudioRunRecord] {
        runs.filter { $0.projectID == project.id }
    }

    private func iterativeRuns(project: Project, root: URL) -> [StudioRunRecord] {
        let ignored = Set(["predictions", "prediction_runs", "prediction_input", "rfd3",
                           "rfd3_runs", "target_prep", "ligand", "rfd3_assets", "config"])
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
            let detail = runDirs.isEmpty ? "Campaign settings saved"
                : "\(exitCodes.filter { $0 == 0 }.count) of \(runDirs.count) design units completed"
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
                                   name: manifest?.runName ?? candidate.lastPathComponent,
                                   root: candidate,
                                   date: manifest?.createdAt ?? fileDate(candidate), state: state,
                                   detail: detail,
                                   manifestURL: manifest == nil ? nil : manifestURL,
                                   hasViewableResults: recordedResults > 0)
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
                                   workflow: .prediction, name: candidate.lastPathComponent,
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
            let hasViewableResults = AppPaths.fm.fileExists(
                atPath: candidate.appendingPathComponent("analysis/top100_manifest.json").path)
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
                                   workflow: .rfdiffusion3, name: candidate.lastPathComponent,
                                   root: candidate, date: fileDate(candidate), state: state,
                                   detail: detail, manifestURL: nil,
                                   hasViewableResults: hasViewableResults)
        }
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
