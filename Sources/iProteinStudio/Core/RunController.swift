import Foundation
import Combine

/// Owns the lifecycle of one design campaign: writes the template, builds the
/// command, spawns the runner, and tracks phase + a rolling log tail.
@MainActor
final class RunController: ObservableObject {
    @Published private(set) var phase: RunPhase = .idle
    @Published private(set) var log: [String] = []
    @Published private(set) var campaignRoot: URL?

    @Published private(set) var projectContext: Project?
    @Published private(set) var currentMessage = ""
    @Published private(set) var isStopping = false
    var projectID: UUID? { projectContext?.id }
    private(set) var hitThreshold = 0.7
    private let job = ManagedJobSession()
    private let maxLog = 500
    private var manifestURL: URL?
    private var persistentLogURL: URL?
    private var lastArguments: [String]?
    private var lastEnvironment: [String: String]?
    private var lastPipelineSnapshot: URL?
    private var engineBatchRoot: URL?

    var isRunning: Bool { if case .running = phase { return true } else { return false } }

    func start(project: Project) {
        guard !isRunning else { return }
        let request = project.request
        projectContext = project
        hitThreshold = request.hitThreshold
        guard request.isRunnable else {
            phase = .failed(request.validationIssues.first?.message ?? "Complete the design settings before starting.")
            return
        }

        let projectDir = AppPaths.projectDir(project)
        let engines = request.selectedDesignEngines
        let requests = request.campaignRequests
        let batch = requests.count > 1
            ? projectDir.appendingPathComponent("engine-batch-\(UUID().uuidString.lowercased())") : nil
        let mpnnSeed = Int.random(in: 1...900_000)
        var campaigns: [URL] = []
        do {
            // Save every engine's complete inputs before submitting any work.
            for entry in requests {
                var childProject = project
                childProject.request = entry.request
                let engine = entry.request.selectedDesignEngines[0]
                let child = childProject.request
                let scaffoldSuffix = child.designType == .nanobody ? "_\(child.scaffoldID)" : ""
                let base = batch == nil ? project.slug : "\(project.slug)_\(engine.rawValue)\(scaffoldSuffix)_\(batch!.lastPathComponent.suffix(8))"
                let runName = uniqueRunName(base: base, in: projectDir)
                let campaign = projectDir.appendingPathComponent(runName, isDirectory: true)
                try AppPaths.fm.createDirectory(at: campaign, withIntermediateDirectories: true)
                let snapshot = try AppPaths.createPipelineSnapshot(in: campaign)
                let inputs = campaign.appendingPathComponent("inputs", isDirectory: true)
                try AppPaths.fm.createDirectory(at: inputs, withIntermediateDirectories: true)
                let template = inputs.appendingPathComponent("design.yaml")
                try TemplateWriter.write(child, to: template)
                var targetTemplate: URL?
                if child.hasTargetTemplate {
                    let source = URL(fileURLWithPath: child.targetTemplatePath)
                    let destination = inputs.appendingPathComponent("target_template.\(source.pathExtension.lowercased())")
                    try AppPaths.fm.copyItem(at: source, to: destination)
                    targetTemplate = destination
                }
                let cdrRanges = child.designType == .nanobody
                    ? CDRDetector.ranges(forScaffold: child.scaffoldSequence) : nil
                let args = CommandBuilder.arguments(request: child, templateYAML: template,
                    outRoot: projectDir, runName: runName, cdrRanges: cdrRanges,
                    mpnnSeed: mpnnSeed, targetTemplate: targetTemplate)
                let manifest = StudioRunManifest(projectID: project.id, projectName: project.name,
                    runName: runName, arguments: args,
                    environmentOverrides: CommandBuilder.environmentOverrides(request: child),
                    requestedTrajectories: child.numDesigns, optimizationCycles: child.numCycles,
                    expectedOptimizedDesigns: child.expectedOptimizedDesigns,
                    pipelineSnapshot: snapshot.path, request: child, engineBatchRoot: batch?.path)
                try JSONEncoder().encode(manifest).write(to: campaign.appendingPathComponent("studio_run.json"), options: .atomic)
                campaigns.append(campaign)
            }
            if let batch {
                try AppPaths.fm.createDirectory(at: batch, withIntermediateDirectories: true)
                let multipleScaffolds = request.designType == .nanobody && request.allocatedScaffolds.count > 1
                let descriptor = EngineBatchManifest(version: multipleScaffolds ? 2 : 1,
                    campaigns: campaigns.map(\.path), engines: requests.map(\.label),
                    trajectoriesPerEngine: request.numDesigns,
                    campaignBudgets: multipleScaffolds ? requests.map { $0.request.numDesigns } : nil,
                    engineIDs: multipleScaffolds ? requests.map { $0.request.selectedDesignEngines[0].rawValue } : nil,
                    scaffoldIDs: multipleScaffolds ? requests.map { $0.request.scaffoldID } : nil)
                try JSONEncoder().encode(descriptor).write(to: batch.appendingPathComponent("studio_engine_batch.json"), options: .atomic)
            }
        } catch {
            phase = .failed("Could not prepare all selected engine and scaffold campaigns. No jobs were submitted. \(error.localizedDescription)")
            return
        }
        engineBatchRoot = batch
        log = []
        selectCampaign(campaigns[0])
        appendLog("Requested budget: \(engines.count) engine(s) × \(request.numDesigns) trajectories each × \(request.numCycles) optimized cycles = \(request.expectedOptimizedDesigns) designs; cycle 00 excluded")
        if request.designType == .nanobody { appendLog("Scaffold allocation per engine: " + request.allocatedScaffolds.map { "\($0.name): \($0.trajectories)" }.joined(separator: ", ")) }
        phase = .running
        launch(arguments: lastArguments ?? [], environment: CommandBuilder.environment(),
               pipelineSnapshot: lastPipelineSnapshot ?? AppPaths.pipeline)
    }

    private struct EngineBatchManifest: Codable {
        var version = 1
        var campaigns: [String]
        var engines: [String]
        var trajectoriesPerEngine: Int
        var campaignBudgets: [Int]? = nil
        var engineIDs: [String]? = nil
        var scaffoldIDs: [String]? = nil
    }

    private func selectCampaign(_ root: URL) {
        guard let data = try? Data(contentsOf: root.appendingPathComponent("studio_run.json")),
              let manifest = try? JSONDecoder().decode(StudioRunManifest.self, from: data) else { return }
        if let request = manifest.request { projectContext?.request = request }
        campaignRoot = root
        manifestURL = root.appendingPathComponent("studio_run.json")
        persistentLogURL = root.appendingPathComponent("studio.log")
        lastArguments = manifest.arguments
        lastEnvironment = manifest.environmentOverrides
        lastPipelineSnapshot = manifest.pipelineSnapshot.map { URL(fileURLWithPath: $0) }
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
        engineBatchRoot = manifest.engineBatchRoot.map { URL(fileURLWithPath: $0) }
        // Clicking Resume is an explicit request to reuse durable checkpoints,
        // even if the original form's optional auto-resume toggle was off.
        manifest.arguments = ResumeContract.arguments(from: manifest.arguments)
        manifest.state = .running
        manifest.updatedAt = Date()
        manifestURL = url
        campaignRoot = record.root
        persistentLogURL = record.root.appendingPathComponent("studio.log")
        lastArguments = manifest.arguments
        let pipelineSnapshot: URL
        if let recorded = manifest.pipelineSnapshot {
            pipelineSnapshot = URL(fileURLWithPath: recorded, isDirectory: true)
            guard AppPaths.fm.fileExists(atPath: pipelineSnapshot
                .appendingPathComponent("nanohunter_run.sh").path) else {
                phase = .failed("This run's recorded pipeline snapshot is missing. Studio will not silently resume it with different scientific code.")
                return
            }
        } else {
            // Compatibility for campaigns created before snapshots existed.
            pipelineSnapshot = AppPaths.pipeline
        }
        lastPipelineSnapshot = pipelineSnapshot
        do { try writeManifest(manifest) }
        catch { phase = .failed("Could not save the resume record: \(error.localizedDescription)"); return }
        var context = Project(name: manifest.projectName)
        context.id = manifest.projectID
        context.slug = record.root.deletingLastPathComponent().lastPathComponent
        context.request = manifest.request ?? context.request
        projectContext = context
        hitThreshold = RunResultsLoader.iterativeHitThreshold(root: record.root)
        log = []
        appendLog("— resuming from durable checkpoints —")
        appendLog("$ nanohunter_run.sh " + manifest.arguments.joined(separator: " "))
        phase = .running
        var environment = CommandBuilder.environment()
        environment.merge(manifest.environmentOverrides ?? [:]) { _, new in new }
        environment["IPROTEINSTUDIO_PIPELINE_SNAPSHOT"] = pipelineSnapshot.path
        lastEnvironment = environment
        launch(arguments: manifest.arguments, environment: environment,
               pipelineSnapshot: pipelineSnapshot)
    }

    func retry() {
        guard !isRunning, let recorded = lastArguments else { return }
        let args = ResumeContract.arguments(from: recorded)
        lastArguments = args
        do { try updateManifestArguments(args) }
        catch { phase = .failed("Could not save the retry record: \(error.localizedDescription)"); return }
        phase = .running
        appendLog("— retrying from durable checkpoints with the recorded settings —")
        launch(arguments: args, environment: lastEnvironment ?? CommandBuilder.environment(),
               pipelineSnapshot: lastPipelineSnapshot ?? AppPaths.pipeline)
    }

    func cancel() {
        guard isRunning else { return }
        isStopping = true
        currentMessage = "Stopping; waiting for worker processes to exit…"
        job.cancel()
    }

    /// Return to the design form (does not delete outputs).
    func reset() {
        guard !isRunning else { return }
        phase = .idle
        campaignRoot = nil
        engineBatchRoot = nil
        projectContext = nil
        log = []
    }

    private func appendLog(_ line: String) {
        log.append(line)
        if log.count > maxLog { log.removeFirst(log.count - maxLog) }
    }

    private func launch(arguments: [String], environment: [String: String], pipelineSnapshot: URL) {
        guard let campaignRoot, let project = projectContext else {
            phase = .failed("The saved workspace context is missing."); return
        }
        currentMessage = "Submitting saved settings…"
        isStopping = false
        let submissionRoot = engineBatchRoot ?? campaignRoot
        if let id = BrokerClient.savedJobID(at: submissionRoot) {
            job.attach(id: id, resume: true, update: receive, failure: failedSubmission)
        } else {
            job.submit(project: project.slug, workflow: engineBatchRoot == nil ? "iterative" : "iterative_batch", output: submissionRoot,
                       update: receive, failure: failedSubmission)
        }
    }

    func reattach(project: Project, root: URL, jobID: String) {
        guard !isRunning else { return }
        projectContext = project
        engineBatchRoot = nil
        if let data = try? Data(contentsOf: root.appendingPathComponent("studio_engine_batch.json")),
           let batch = try? JSONDecoder().decode(EngineBatchManifest.self, from: data),
           let first = batch.campaigns.first {
            engineBatchRoot = root
            selectCampaign(URL(fileURLWithPath: first))
            phase = .running
            job.attach(id: jobID, update: receive, failure: failedSubmission)
            return
        }
        campaignRoot = root
        manifestURL = root.appendingPathComponent("studio_run.json")
        if let manifestURL, let data = try? Data(contentsOf: manifestURL),
           let manifest = try? JSONDecoder().decode(StudioRunManifest.self, from: data) {
            projectContext?.name = manifest.projectName
            if let request = manifest.request { projectContext?.request = request }
            lastArguments = manifest.arguments
            lastPipelineSnapshot = manifest.pipelineSnapshot.map { URL(fileURLWithPath: $0) }
        }
        hitThreshold = RunResultsLoader.iterativeHitThreshold(root: root)
        phase = .running
        job.attach(id: jobID, update: receive, failure: failedSubmission)
    }

    private func receive(_ state: ManagedJob) {
        if let active = state.active_output, campaignRoot?.path != active {
            selectCampaign(URL(fileURLWithPath: active))
        }
        let prefix = state.engine_label.map { "\($0) (\(state.engine_index ?? 1)/\(state.engine_count ?? 1)) · " } ?? ""
        currentMessage = prefix + (state.message ?? state.status)
        isStopping = state.status == "stopping"
        if let lines = state.pipeline_log_tail { log = lines }
        if state.isActive { phase = .running }
        else if state.status == "completed" { phase = .finished }
        else if state.status == "cancelled" { phase = .cancelled }
        else { phase = .failed(currentMessage + " Completed checkpoints were kept. Retry uses the saved settings.") }
    }

    private func failedSubmission(_ message: String) {
        phase = .failed(message)
    }

    private func writeManifest(_ manifest: StudioRunManifest) throws {
        guard let url = manifestURL else { throw NHError.message("No launch record destination was selected.") }
        try JSONEncoder().encode(manifest).write(to: url, options: .atomic)
    }

    private func updateManifestArguments(_ arguments: [String]) throws {
        guard let url = manifestURL else { throw NHError.message("The launch record is missing.") }
        var manifest = try JSONDecoder().decode(StudioRunManifest.self, from: Data(contentsOf: url))
        manifest.arguments = arguments
        manifest.state = .running
        manifest.updatedAt = Date()
        try writeManifest(manifest)
    }

    private func uniqueRunName(base: String, in dir: URL) -> String {
        var name = base
        var n = 1
        while AppPaths.fm.fileExists(atPath: dir.appendingPathComponent(name).path) {
            n += 1
            name = "\(base)_\(n)"
        }
        return name
    }
}
