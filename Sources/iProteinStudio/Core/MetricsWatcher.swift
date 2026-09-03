import Foundation
import Combine

/// Polls a campaign directory for design + validation metrics and publishes
/// de-duplicated, growing lists for the live dashboard.
///
/// Design (per cycle):      <run>/metrics_per_cycle.csv
///   cycle,iptm,complex_plddt,confidence_json,structure_path,binder_sequence
/// Validation (per checker/cycle): <run>/post_<predictor>/cycle_YY/post_metrics_row.csv
///   run,cycle,iptm,complex_plddt,binder_sequence,structure_path,confidence_json
@MainActor
final class MetricsWatcher: ObservableObject {
    @Published private(set) var designPoints: [DesignPoint] = []
    @Published private(set) var validationPoints: [DesignPoint] = []

    private var timer: Timer?
    private var seen = Set<String>()
    private var root: URL?
    private var designPredictor = "unknown"

    /// Distinct design-run numbers seen so far, ascending.
    var runNumbers: [Int] { Array(Set(designPoints.map(\.run))).sorted() }

    /// `root` is the campaign directory: <out-root>/<run-name>.
    func start(root: URL, interval: TimeInterval = 2.0) {
        stop()
        self.root = root
        self.designPoints = []
        self.validationPoints = []
        self.seen = []
        self.designPredictor = recordedDesignPredictor(at: root) ?? "unknown"
        scan()
        timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.scan() }
        }
    }

    func stop() { timer?.invalidate(); timer = nil }
    func refresh() { scan() }

    /// Design points for a given run, ordered by cycle.
    func designPoints(forRun run: Int) -> [DesignPoint] {
        designPoints.filter { $0.run == run }.sorted { $0.cycle < $1.cycle }
    }

    private func scan() {
        guard let root else { return }
        let fm = FileManager.default
        guard let runDirs = try? fm.contentsOfDirectory(at: root, includingPropertiesForKeys: nil) else { return }
        var addedDesign = false, addedVal = false

        for runDir in runDirs where runDir.lastPathComponent.hasPrefix("run_") {
            let runNum = Int(runDir.lastPathComponent.replacingOccurrences(of: "run_", with: "")) ?? 0

            // --- design ---
            let csv = runDir.appendingPathComponent("metrics_per_cycle.csv")
            for row in CSVTable.rows(at: csv) {
                guard let iptm = Double(row["iptm"] ?? "") else { continue }
                let cycle = Int(row["cycle"] ?? "") ?? 0
                let confidencePath = row["confidence_json"] ?? ""
                let structurePath = resolvedPath(row["structure_path"] ?? "", root: root)
                if insert(.design, designPredictor, runNum, cycle) {
                    designPoints.append(DesignPoint(stage: .design, predictor: designPredictor, run: runNum, cycle: cycle,
                        iptm: iptm,
                        ipsaeMinimum: double(row["ipsae_min"]) ?? ipsaeMinimum(at: confidencePath, root: root),
                        plddt: Double(row["complex_plddt"] ?? "") ?? .nan,
                        sequence: row["binder_sequence"] ?? "", structurePath: structurePath))
                    addedDesign = true
                }
            }

            // --- validation (post-prediction) ---
            let postDirs = (try? fm.contentsOfDirectory(at: runDir, includingPropertiesForKeys: nil)) ?? []
            for postRoot in postDirs where postRoot.lastPathComponent.hasPrefix("post_") {
                let predictor = String(postRoot.lastPathComponent.dropFirst("post_".count))
                let cycleDirs = (try? fm.contentsOfDirectory(at: postRoot, includingPropertiesForKeys: nil)) ?? []
                for cycleDir in cycleDirs where cycleDir.lastPathComponent.hasPrefix("cycle_") {
                    let checkpoint = cycleDir.appendingPathComponent("post_metrics_row.csv")
                    for row in CSVTable.rows(at: checkpoint) {
                        guard let iptm = Double(row["iptm"] ?? "") else { continue }
                        let cycle = Int(row["cycle"] ?? "") ?? 0
                        let recordedPredictor = nonempty(row["predictor"]) ?? predictor
                        let confidencePath = row["confidence_json"] ?? ""
                        if insert(.validation, recordedPredictor, runNum, cycle) {
                            validationPoints.append(DesignPoint(
                                stage: .validation, predictor: recordedPredictor,
                                run: Int(row["run"] ?? "") ?? runNum, cycle: cycle,
                                iptm: iptm,
                                ipsaeMinimum: double(row["ipsae_min"])
                                    ?? ipsaeMinimum(at: confidencePath, root: root),
                                plddt: Double(row["complex_plddt"] ?? "") ?? .nan,
                                sequence: row["binder_sequence"] ?? "",
                                structurePath: resolvedPath(row["structure_path"] ?? "", root: root),
                                savedHitVerdict: boolean(row["is_hit"]),
                                failedFilters: splitFilters(row["failed_filters"])
                            ))
                            addedVal = true
                        }
                    }
                }
            }
        }
        if addedDesign { designPoints.sort { ($0.run, $0.cycle) < ($1.run, $1.cycle) } }
        if addedVal {
            validationPoints.sort { ($0.run, $0.cycle, $0.predictor) < ($1.run, $1.cycle, $1.predictor) }
        }
    }

    private func insert(_ stage: DesignStage, _ predictor: String, _ run: Int, _ cycle: Int) -> Bool {
        let key = "\(stage.rawValue)-\(predictor)-\(run)-\(cycle)"
        return seen.insert(key).inserted
    }

    private func double(_ text: String?) -> Double? {
        guard let text, let value = Double(text), value.isFinite else { return nil }
        return value
    }

    private func ipsaeMinimum(at path: String, root: URL) -> Double? {
        guard !path.isEmpty,
              let url = RunResultsLoader.resolvedURL(path, relativeTo: root),
              let data = FileManager.default.contents(atPath: url.path),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        if let number = object["ipsae_min"] as? NSNumber { return number.doubleValue }
        if let text = object["ipsae_min"] as? String { return Double(text) }
        return nil
    }

    private func resolvedPath(_ path: String, root: URL) -> String {
        RunResultsLoader.resolvedURL(path, relativeTo: root)?.path ?? path
    }

    private func nonempty(_ text: String?) -> String? {
        guard let text = text?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else { return nil }
        return text
    }

    private func boolean(_ text: String?) -> Bool? {
        guard let value = nonempty(text)?.lowercased() else { return nil }
        if ["true", "1", "yes"].contains(value) { return true }
        if ["false", "0", "no"].contains(value) { return false }
        return nil
    }

    private func splitFilters(_ text: String?) -> [String] {
        guard let text = nonempty(text) else { return [] }
        return text.split(separator: ";").map(String.init)
    }

    private func recordedDesignPredictor(at root: URL) -> String? {
        let url = root.appendingPathComponent("studio_run.json")
        guard let data = try? Data(contentsOf: url),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let arguments = object["arguments"] as? [String],
              let index = arguments.firstIndex(of: "--predictor"),
              arguments.indices.contains(index + 1) else { return nil }
        return arguments[index + 1]
    }
}

private func < (lhs: (Int, Int), rhs: (Int, Int)) -> Bool {
    lhs.0 != rhs.0 ? lhs.0 < rhs.0 : lhs.1 < rhs.1
}

private func < (lhs: (Int, Int, String), rhs: (Int, Int, String)) -> Bool {
    if lhs.0 != rhs.0 { return lhs.0 < rhs.0 }
    if lhs.1 != rhs.1 { return lhs.1 < rhs.1 }
    return lhs.2 < rhs.2
}
