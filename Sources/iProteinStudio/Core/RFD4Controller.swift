import Foundation
import Combine
import CryptoKit

@MainActor
final class RFD4Controller: ObservableObject {
    @Published var phase: RunPhase = .idle
    @Published var currentMessage = ""
    @Published var log: [String] = []
    @Published var outputRoot: URL?
    private(set) var projectSlug = ""
    private let job = ManagedJobSession()
    var isRunning: Bool { if case .running = phase { return true }; return false }
    var canStartAnother: Bool { !isRunning || job.id != nil }
    var observedJobID: String? { job.id }

    @discardableResult
    func prepareNewRun() -> Bool {
        guard canStartAnother else { return false }
        job.detach()
        phase = .idle; outputRoot = nil; projectSlug = ""
        currentMessage = ""; log = []
        return true
    }

    func start(request: RFD4Request, project: Project, name: String = "") {
        guard canStartAnother, !isRunning || request.validationIssues.isEmpty else { return }
        guard prepareNewRun() else { return }
        guard request.validationIssues.isEmpty else { phase = .failed(request.validationIssues[0]); return }
        let directory = AppPaths.projectDir(project).appendingPathComponent("rfd4_runs/rfd4-\(UUID().uuidString)")
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try RunNaming.write(name, to: directory)
            _ = try AppPaths.createPipelineSnapshot(in: directory)
            var frozen = request
            let imports = directory.appendingPathComponent("imports")
            try FileManager.default.createDirectory(at: imports, withIntermediateDirectories: true)
            func copy(_ path: String) throws -> String {
                if path.isEmpty || path == "empty" || path == "auto" { return path }
                let source = URL(fileURLWithPath: path)
                let target = imports.appendingPathComponent(UUID().uuidString + "-" + source.lastPathComponent)
                try FileManager.default.copyItem(at: source, to: target)
                return target.path
            }
            if !request.source.isEmpty {
                let source = URL(fileURLWithPath: request.source)
                let target = imports.appendingPathComponent(UUID().uuidString + "-" + source.lastPathComponent)
                try TargetStructureSnapshot.copy(source: source, to: target,
                    predictionCache: AppPaths.support.appendingPathComponent("target_predictions"))
                frozen.source = target.path
            }
            frozen.target_msa = try copy(request.target_msa)
            frozen.scaffold_msa = try copy(request.scaffold_msa)
            frozen.starting_structures = try request.starting_structures.map(copy)
            let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(frozen).write(to: directory.appendingPathComponent("studio_rfd4_request.json"), options: .atomic)
            outputRoot = directory; projectSlug = project.slug
            phase = .running; log = []; currentMessage = "Checking inputs and engine provenance…"
            job.submit(project: project.slug, workflow: "rfd4", output: directory,
                       preparing: { [weak self] in self?.currentMessage = $0 },
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
            job.submit(project: projectSlug, workflow: "rfd4", output: root,
                       preparing: { [weak self] in self?.currentMessage = $0 },
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
