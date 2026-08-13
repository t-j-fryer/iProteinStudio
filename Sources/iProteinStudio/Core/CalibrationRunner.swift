import Foundation
import Combine

/// Runs the pipeline's memory calibration only (one heaviest-case Boltz
/// prediction at the longest binder + the target), then reports the resulting
/// calibration_memory_metrics.csv and the suggested parallelism.
@MainActor
final class CalibrationRunner: ObservableObject {
    struct Metric: Identifiable { let id = UUID(); let label: String; let value: String }

    enum Phase: Equatable { case idle, running, done, failed(String) }

    @Published private(set) var phase: Phase = .idle
    @Published private(set) var metrics: [Metric] = []
    @Published private(set) var suggestedParallel: Int?
    @Published private(set) var log: [String] = []

    private var runner: ProcessRunner?
    private var csvURL: URL?
    var isRunning: Bool { phase == .running }

    func run(request: DesignRequest, projectDir: URL) {
        guard !isRunning else { return }
        guard request.isRunnable else {
            phase = .failed("Fill in the target and design settings first."); return
        }

        let dir = projectDir.appendingPathComponent("_calibration_run", isDirectory: true)
        try? FileManager.default.removeItem(at: dir)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let runName = "calibration"
        let templateURL = dir.appendingPathComponent("calibration_template.yaml")
        do { try TemplateWriter.write(request, to: templateURL) }
        catch { phase = .failed("Could not write template: \(error.localizedDescription)"); return }

        let cdrRanges = request.designType == .nanobody
            ? CDRDetector.ranges(forScaffold: request.scaffoldSequence) : nil
        var args = CommandBuilder.arguments(request: request, templateYAML: templateURL,
                                            outRoot: dir, runName: runName, cdrRanges: cdrRanges)
        args += ["--calibrate-only"]
        csvURL = dir.appendingPathComponent("\(runName)/calibration_memory_metrics.csv")

        phase = .running; metrics = []; suggestedParallel = nil; log = []
        appendLog("Calibrating at max: longest binder + target, Boltz (heaviest model)…")

        let runner = ProcessRunner()
        self.runner = runner
        runner.launch(executable: AppPaths.runnerScript, arguments: args,
                      environment: CommandBuilder.environment(), workingDir: AppPaths.pipeline,
                      onLine: { [weak self] line in self?.handle(line) },
                      onExit: { [weak self] code in self?.finish(code) })
    }

    func cancel() { runner?.cancel(); phase = .idle }

    private func handle(_ line: String) {
        appendLog(line)
        if line.contains("suggested_max_parallel=") ,
           let range = line.range(of: "suggested_max_parallel=") {
            let tail = line[range.upperBound...].prefix { $0.isNumber }
            suggestedParallel = Int(tail)
        }
    }

    private func finish(_ code: Int32) {
        guard let csv = csvURL, let text = try? String(contentsOf: csv, encoding: .utf8) else {
            phase = .failed("Calibration finished but no metrics file was produced (exit \(code)).")
            return
        }
        metrics = parse(text)
        phase = metrics.isEmpty ? .failed("Calibration produced an empty metrics file.") : .done
    }

    /// Parse the `metric,mb` CSV into friendly, ordered rows.
    private func parse(_ text: String) -> [Metric] {
        let labels: [String: String] = [
            "peak_effective_mb": "Peak memory per prediction",
            "peak_rss_mb": "Peak RSS",
            "peak_physical_footprint_mb": "Peak physical footprint",
            "peak_system_delta_mb": "Peak system-memory delta",
            "system_available_mb": "System memory available (at calibration)",
            "configured_safe_mb": "Configured safe budget",
            "mps_live_budget_mb": "Live memory budget",
            "mps_memory_reserve_gb": "Reserved for system",
        ]
        let order = ["peak_effective_mb", "peak_rss_mb", "peak_physical_footprint_mb",
                     "peak_system_delta_mb", "system_available_mb", "configured_safe_mb",
                     "mps_live_budget_mb", "mps_memory_reserve_gb"]
        var raw: [String: Double] = [:]
        for line in text.split(separator: "\n").dropFirst() {
            let c = line.split(separator: ",")
            if c.count == 2, let v = Double(c[1]) { raw[String(c[0])] = v }
        }
        return order.compactMap { key in
            guard let v = raw[key] else { return nil }
            let unit = key.hasSuffix("_gb") ? "GB" : "MB"
            let value = key.hasSuffix("_gb") ? String(format: "%.0f %@", v, unit)
                                             : String(format: "%.0f %@ (%.1f GB)", v, unit, v / 1024.0)
            return Metric(label: labels[key] ?? key, value: value)
        }
    }

    private func appendLog(_ s: String) { log.append(s); if log.count > 300 { log.removeFirst(log.count - 300) } }
}
