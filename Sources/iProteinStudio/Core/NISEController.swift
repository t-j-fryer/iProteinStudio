import Foundation
import Combine

@MainActor
final class NISEController: ObservableObject {
    @Published var phase: RunPhase = .idle
    @Published var currentMessage = ""
    @Published var log: [String] = []
    @Published var outputRoot: URL?
    private(set) var projectSlug = ""
    private let job = ManagedJobSession()
    var isRunning: Bool { if case .running = phase { return true }; return false }

    func start(request: NISERequest, project: Project) {
        guard !isRunning else { return }
        guard request.validationIssues.isEmpty else { phase = .failed(request.validationIssues[0]); return }
        let directory = AppPaths.projectDir(project).appendingPathComponent("nise_runs/nise-\(UUID().uuidString)")
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            _ = try AppPaths.createPipelineSnapshot(in: directory)
            struct Config: Encodable { let output: String; let request: NISERequest }
            let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(Config(output: directory.path, request: request))
                .write(to: directory.appendingPathComponent("nise_config.json"), options: .atomic)
            outputRoot = directory; projectSlug = project.slug
            phase = .running; log = []; currentMessage = "Checking inputs and engine provenance…"
            job.submit(project: project.slug, workflow: "nise", output: directory,
                       update: receive, failure: { [weak self] in self?.phase = .failed($0) })
        } catch { phase = .failed(error.localizedDescription) }
    }

    func reattach(root: URL, jobID: String, resume: Bool = false) {
        guard !isRunning else { return }
        outputRoot = root
        projectSlug = root.deletingLastPathComponent().deletingLastPathComponent().lastPathComponent
        phase = .running
        job.attach(id: jobID, resume: resume, update: receive, failure: { [weak self] in self?.phase = .failed($0) })
    }

    func retry() {
        guard let root = outputRoot, !isRunning else { return }
        if let id = BrokerClient.savedJobID(at: root) { reattach(root: root, jobID: id, resume: true) }
        else {
            phase = .running
            job.submit(project: projectSlug, workflow: "nise", output: root,
                       update: receive, failure: { [weak self] in self?.phase = .failed($0) })
        }
    }

    func cancel() { currentMessage = "Stopping; preserving completed work…"; job.cancel() }

    private func receive(_ state: ManagedJob) {
        currentMessage = state.message ?? state.status
        log = state.pipeline_log_tail ?? log
        if state.isActive { phase = .running }
        else if state.status == "completed" { phase = .finished }
        else if state.status == "cancelled" { phase = .cancelled }
        else { phase = .failed(currentMessage) }
    }
}
