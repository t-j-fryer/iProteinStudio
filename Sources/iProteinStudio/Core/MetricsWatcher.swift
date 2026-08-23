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

    /// Distinct design-run numbers seen so far, ascending.
    var runNumbers: [Int] { Array(Set(designPoints.map(\.run))).sorted() }

    /// `root` is the campaign directory: <out-root>/<run-name>.
    func start(root: URL, interval: TimeInterval = 2.0) {
        stop()
        self.root = root
        self.designPoints = []
        self.validationPoints = []
        self.seen = []
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
            if let text = try? String(contentsOf: csv, encoding: .utf8) {
                for line in dataLines(text) {
                    let c = line.components(separatedBy: ",")
                    guard c.count >= 6, let iptm = Double(c[1]) else { continue }
                    let cycle = Int(c[0]) ?? 0
                    if insert(.design, "", runNum, cycle) {
                        designPoints.append(DesignPoint(stage: .design, predictor: "", run: runNum, cycle: cycle,
                            iptm: iptm, ipsaeMinimum: ipsaeMinimum(at: c[3]),
                            plddt: Double(c[2]) ?? .nan, sequence: c[5], structurePath: c[4]))
                        addedDesign = true
                    }
                }
            }

            // --- validation (post-prediction) ---
            let postDirs = (try? fm.contentsOfDirectory(at: runDir, includingPropertiesForKeys: nil)) ?? []
            for postRoot in postDirs where postRoot.lastPathComponent.hasPrefix("post_") {
                let predictor = String(postRoot.lastPathComponent.dropFirst("post_".count))
                let cycleDirs = (try? fm.contentsOfDirectory(at: postRoot, includingPropertiesForKeys: nil)) ?? []
                for cycleDir in cycleDirs where cycleDir.lastPathComponent.hasPrefix("cycle_") {
                    let row = cycleDir.appendingPathComponent("post_metrics_row.csv")
                    guard let text = try? String(contentsOf: row, encoding: .utf8) else { continue }
                    for line in dataLines(text) {
                        let c = line.components(separatedBy: ",")
                        // run,cycle,iptm,complex_plddt,binder_sequence,structure_path,confidence_json
                        guard c.count >= 6, let iptm = Double(c[2]) else { continue }
                        let cycle = Int(c[1]) ?? 0
                        if insert(.validation, predictor, runNum, cycle) {
                            validationPoints.append(DesignPoint(stage: .validation, predictor: predictor, run: runNum, cycle: cycle,
                                iptm: iptm, ipsaeMinimum: c.count > 6 ? ipsaeMinimum(at: c[6]) : nil,
                                plddt: Double(c[3]) ?? .nan, sequence: c[4], structurePath: c[5]))
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

    private func dataLines(_ text: String) -> [String] {
        var lines = text.split(separator: "\n", omittingEmptySubsequences: true).map(String.init)
        if !lines.isEmpty { lines.removeFirst() } // header
        return lines
    }

    private func ipsaeMinimum(at path: String) -> Double? {
        guard !path.isEmpty,
              let data = FileManager.default.contents(atPath: path),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        if let number = object["ipsae_min"] as? NSNumber { return number.doubleValue }
        if let text = object["ipsae_min"] as? String { return Double(text) }
        return nil
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
