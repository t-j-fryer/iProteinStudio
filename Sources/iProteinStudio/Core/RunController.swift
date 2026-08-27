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
    private var manifestURL: URL?
    private var persistentLogURL: URL?
    private var lastArguments: [String]?
    private var lastEnvironment: [String: String]?

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
            try AppPaths.fm.createDirectory(at: campaign, withIntermediateDirectories: true)
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
        campaignRoot = campaign
        manifestURL = campaign.appendingPathComponent("studio_run.json")
        persistentLogURL = campaign.appendingPathComponent("studio.log")
        lastArguments = args
        let environment = CommandBuilder.environment(request: request)
        lastEnvironment = environment
        writeManifest(StudioRunManifest(projectID: project.id, projectName: project.name,
                                        runName: runName, arguments: args,
                                        environmentOverrides: CommandBuilder.environmentOverrides(request: request)))
        try? "".write(to: persistentLogURL!, atomically: true, encoding: .utf8)
        appendLog("$ nanohunter_run.sh " + args.joined(separator: " "))
        phase = .running
        launch(arguments: args, environment: environment)
    }

    /// Continue an interrupted campaign using the exact recorded command. The
    /// runner's --resume checkpoints completed cycles and predictions, so the
    /// app never reconstructs scientific settings from today's form values.
    func resume(_ record: StudioRunRecord) {
        guard !isRunning else { return }
        guard let url = record.manifestURL,
              let data = try? Data(contentsOf: url),
              var manifest = try? JSONDecoder().decode(StudioRunManifest.self, from: data) else {
            phase = .failed("This run cannot be resumed because its recorded launch manifest is missing or unreadable.")
            return
        }
        // Clicking Resume is an explicit request to reuse durable checkpoints,
        // even if the original form's optional auto-resume toggle was off.
        manifest.arguments = ResumeContract.arguments(from: manifest.arguments)
        manifest.state = .running
        manifest.updatedAt = Date()
        manifestURL = url
        campaignRoot = record.root
        persistentLogURL = record.root.appendingPathComponent("studio.log")
        lastArguments = manifest.arguments
        writeManifest(manifest)
        log = []
        appendLog("— resuming from durable checkpoints —")
        appendLog("$ nanohunter_run.sh " + manifest.arguments.joined(separator: " "))
        phase = .running
        var environment = CommandBuilder.environment()
        environment.merge(manifest.environmentOverrides ?? [:]) { _, new in new }
        lastEnvironment = environment
        launch(arguments: manifest.arguments, environment: environment)
    }

    func retry() {
        guard !isRunning, let recorded = lastArguments else { return }
        let args = ResumeContract.arguments(from: recorded)
        lastArguments = args
        updateManifestArguments(args)
        phase = .running
        appendLog("— retrying from durable checkpoints with the recorded settings —")
        launch(arguments: args, environment: lastEnvironment ?? CommandBuilder.environment())
    }

    func cancel() {
        runner?.cancel()
        phase = .cancelled
        updateManifest(state: .stopped)
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
        case .cancelled:
            appendLog("— stopped process exited (\(code)) —")
            return
        default:
            phase = code == 0 ? .finished : .failed("Pipeline exited with code \(code).")
            updateManifest(state: code == 0 ? .completed : .failed)
        }
        appendLog(code == 0 ? "✓ run finished" : "✗ run exited (\(code))")
    }

    private func appendLog(_ line: String) {
        log.append(line)
        if log.count > maxLog { log.removeFirst(log.count - maxLog) }
        guard let url = persistentLogURL,
              let data = (line + "\n").data(using: .utf8),
              let handle = try? FileHandle(forWritingTo: url) else { return }
        do {
            try handle.seekToEnd()
            try handle.write(contentsOf: data)
            try handle.close()
        } catch { try? handle.close() }
    }

    private func launch(arguments: [String], environment: [String: String]) {
        let runner = ProcessRunner()
        self.runner = runner
        runner.launch(executable: URL(fileURLWithPath: "/usr/bin/caffeinate"),
                      arguments: ["-dimsu", AppPaths.runnerScript.path] + arguments,
                      environment: environment, workingDir: AppPaths.pipeline,
                      onLine: { [weak self] line in self?.appendLog(line) },
                      onExit: { [weak self] code in self?.finish(code: code) })
    }

    private func writeManifest(_ manifest: StudioRunManifest) {
        guard let url = manifestURL, let data = try? JSONEncoder().encode(manifest) else { return }
        try? data.write(to: url, options: .atomic)
    }

    private func updateManifest(state: StudioRunState) {
        guard let url = manifestURL, let data = try? Data(contentsOf: url),
              var manifest = try? JSONDecoder().decode(StudioRunManifest.self, from: data)
        else { return }
        manifest.state = state
        manifest.updatedAt = Date()
        writeManifest(manifest)
    }

    private func updateManifestArguments(_ arguments: [String]) {
        guard let url = manifestURL, let data = try? Data(contentsOf: url),
              var manifest = try? JSONDecoder().decode(StudioRunManifest.self, from: data)
        else { return }
        manifest.arguments = arguments
        manifest.state = .running
        manifest.updatedAt = Date()
        writeManifest(manifest)
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
