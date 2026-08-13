import Foundation
import Combine

/// Owns the lifecycle of one design campaign: writes the template, builds the
/// command, spawns the runner, and tracks phase + a rolling log tail.
@MainActor
final class RunController: ObservableObject {
    @Published private(set) var phase: RunPhase = .idle
    @Published private(set) var log: [String] = []
    @Published private(set) var campaignRoot: URL?

    private var runner: ProcessRunner?
    private let maxLog = 500

    var isRunning: Bool { if case .running = phase { return true } else { return false } }

    func start(project: Project) {
        guard !isRunning else { return }
        let request = project.request
        guard request.isRunnable else {
            phase = .failed("Please provide a scaffold, a target sequence, and at least one CDR.")
            return
        }

        let projectDir = AppPaths.projectDir(project)
        let runName = uniqueRunName(project: project, in: projectDir)
        let campaign = projectDir.appendingPathComponent(runName, isDirectory: true)
        let templateURL = projectDir.appendingPathComponent("\(runName)_template.yaml")

        do {
            try TemplateWriter.write(request, to: templateURL)
        } catch {
            phase = .failed("Could not write template: \(error.localizedDescription)")
            return
        }

        // Resolve explicit CDR ranges for this scaffold so seed/calibration
        // never overflow a short framework (nanobody mode only).
        let cdrRanges = request.designType == .nanobody
            ? CDRDetector.ranges(forScaffold: request.scaffoldSequence)
            : nil
        // Fresh random base seed each launch → non-deterministic MPNN sampling
        // (re-running the same project explores new sequences).
        let mpnnSeed = Int.random(in: 1...900_000)
        let args = CommandBuilder.arguments(request: request, templateYAML: templateURL,
                                             outRoot: projectDir, runName: runName,
                                             cdrRanges: cdrRanges, mpnnSeed: mpnnSeed)
        log = []
        appendLog("$ nanohunter_run.sh " + args.joined(separator: " "))
        campaignRoot = campaign
        phase = .running

        let runner = ProcessRunner()
        self.runner = runner
        runner.launch(
            executable: AppPaths.runnerScript,
            arguments: args,
            environment: CommandBuilder.environment(request: request),
            workingDir: AppPaths.pipeline,
            onLine: { [weak self] line in self?.appendLog(line) },
            onExit: { [weak self] code in self?.finish(code: code) }
        )
    }

    func cancel() {
        runner?.cancel()
        phase = .cancelled
        appendLog("— cancelled by user —")
    }

    /// Return to the design form (does not delete outputs).
    func reset() {
        guard !isRunning else { return }
        phase = .idle
        campaignRoot = nil
        log = []
    }

    private func finish(code: Int32) {
        switch phase {
        case .cancelled: break
        default:
            phase = code == 0 ? .finished : .failed("Pipeline exited with code \(code).")
        }
        appendLog(code == 0 ? "✓ run finished" : "✗ run exited (\(code))")
    }

    private func appendLog(_ line: String) {
        log.append(line)
        if log.count > maxLog { log.removeFirst(log.count - maxLog) }
    }

    private func uniqueRunName(project: Project, in dir: URL) -> String {
        let base = project.slug
        var name = base
        var n = 1
        while AppPaths.fm.fileExists(atPath: dir.appendingPathComponent(name).path) {
            n += 1
            name = "\(base)_\(n)"
        }
        return name
    }
}
