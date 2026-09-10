import Foundation
import Combine
import Darwin

struct ManagedJob: Decodable, Identifiable {
    let id: String
    let project: String
    let kind: String
    let status: String
    let message: String?
    let stage: String?
    let output_root: String?
    let active_output: String?
    let child_outputs: [String]?
    let engine_label: String?
    let engine_index: Int?
    let engine_count: Int?
    let pipeline_log_tail: [String]?
    let exit_code: Int32?
    let created_at: String?
    var isActive: Bool { ["queued", "running", "stopping"].contains(status) }
    var output: URL? { output_root.map { URL(fileURLWithPath: $0) } }
    var workflowLabel: String {
        if kind.contains("iterative") { return "Protein Hunter" }
        if kind.contains("nise") { return "NISE" }
        if kind.contains("rfd3") || kind.contains("rfdiffusion3") { return "RFdiffusion3" }
        if kind.contains("prediction") || kind == "desktop_target_prepare" { return "Predict" }
        return kind
    }
    var displayStatus: String {
        switch status {
        case "queued": return "Waiting"
        case "running": return "Running"
        case "stopping": return "Stopping"
        default: return status.capitalized
        }
    }
}

/// All clients talk to the same durable registry. The CLI is bundled with the
/// app; executing it does not restage scripts beneath an active campaign.
enum BrokerClient {
    static func call<T: Decodable>(_ arguments: [String], as: T.Type) async throws -> T {
        guard let pipeline = AppPaths.bundledPipeline else {
            throw NHError.message("The job service is missing. Reinstall Studio.")
        }
        let script = pipeline.appendingPathComponent("mcp/studioctl.py")
        let environment = CommandBuilder.environment()
        return try await Task.detached(priority: .utility) {
            let process = Process()
            let pipe = Pipe()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
            process.arguments = [script.path] + arguments
            process.environment = environment
            process.standardOutput = pipe
            process.standardError = pipe
            try process.run()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            guard process.terminationStatus == 0 else {
                let error = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
                throw NHError.message(error?["error"] as? String ?? "The job service could not complete this request. Saved results were kept.")
            }
            return try JSONDecoder().decode(T.self, from: data)
        }.value
    }

    static func savedJobID(at root: URL) -> String? {
        guard let data = try? Data(contentsOf: root.appendingPathComponent("studio_job.json")),
              let value = try? JSONDecoder().decode([String: String].self, from: data) else { return nil }
        return value["id"]
    }
}

@MainActor
final class JobCenter: ObservableObject {
    static let shared = JobCenter()
    @Published private(set) var jobs: [ManagedJob] = []
    @Published private(set) var error: String?
    @Published private(set) var operationError: String?
    func reportOperationError(_ message: String) { operationError = message }
    private var polling: Task<Void, Never>?
    var active: [ManagedJob] { jobs.filter(\.isActive) }
    var waiting: [ManagedJob] { active.filter { $0.status == "queued" } }
    func start() {
        guard polling == nil else { return }
        polling = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                try? await Task.sleep(nanoseconds: 3_000_000_000)
            }
        }
    }
    func refresh() async {
        struct Response: Decodable { let jobs: [ManagedJob] }
        do {
            jobs = try await BrokerClient.call(["jobs"], as: Response.self).jobs
            error = nil
        } catch { self.error = error.localizedDescription }
    }
    func cancel(_ job: ManagedJob) {
        Task {
            do { _ = try await BrokerClient.call(["cancel", job.id], as: ManagedJob.self); await refresh() }
            catch { self.error = error.localizedDescription }
        }
    }
    func resume(_ job: ManagedJob) {
        Task {
            do { _ = try await BrokerClient.call(["resume", job.id], as: ManagedJob.self); await refresh() }
            catch { self.error = error.localizedDescription }
        }
    }

    /// Synchronous check used only while holding registry.lock for filesystem
    /// changes. Queued jobs reserve their workspace before they acquire the GPU.
    static func workspaceHasJobs(_ slug: String) throws -> Bool {
        let directory = AppPaths.support.appendingPathComponent("agent/jobs")
        guard FileManager.default.fileExists(atPath: directory.path) else { return false }
        for child in try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil) {
            let state = child.appendingPathComponent("state.json")
            guard FileManager.default.fileExists(atPath: state.path) else { continue }
            let job = try JSONDecoder().decode(ManagedJob.self, from: Data(contentsOf: state))
            if job.project == slug && job.isActive { return true }
        }
        return false
    }
}

/// Observes durable work; cancelling observation or quitting the app does not
/// cancel the worker. Only the explicit Stop action requests cancellation.
@MainActor
final class ManagedJobSession {
    private(set) var id: String?
    private var task: Task<Void, Never>?
    private var update: ((ManagedJob) -> Void)?
    private var failure: ((String) -> Void)?
    private var cancellationRequested = false
    private(set) var hasSession = false

    /// Stop observing only. The broker continues owning the saved job and GPU
    /// lease; navigating to a new form must never send a cancellation request.
    func detach() {
        task?.cancel()
        task = nil
        update = nil
        failure = nil
        id = nil
        hasSession = false
        cancellationRequested = false
    }

    func submit(project: String, workflow: String, output: URL,
                update: @escaping (ManagedJob) -> Void, failure: @escaping (String) -> Void) {
        self.update = update; self.failure = failure
        id = nil; cancellationRequested = false; hasSession = true
        task?.cancel()
        task = Task {
            do {
                let request = output.appendingPathComponent("studio_submission.json")
                try JSONEncoder().encode(["project": project, "workflow": workflow, "output": output.path])
                    .write(to: request, options: .atomic)
                let job = try await BrokerClient.call(["_desktop-submit", request.path], as: ManagedJob.self)
                guard !Task.isCancelled else { return }
                id = job.id
                if cancellationRequested { cancel() }
                await observe(job)
            } catch { if !Task.isCancelled { failure(error.localizedDescription) } }
        }
    }

    func attach(id: String, resume: Bool = false,
                update: @escaping (ManagedJob) -> Void, failure: @escaping (String) -> Void) {
        self.id = id; self.update = update; self.failure = failure
        cancellationRequested = false; hasSession = true
        task?.cancel()
        task = Task {
            do {
                let state = try await BrokerClient.call([resume ? "resume" : "job-status", id], as: ManagedJob.self)
                await observe(state)
            } catch { if !Task.isCancelled { failure(error.localizedDescription) } }
        }
    }

    private func observe(_ initial: ManagedJob) async {
        var state = initial
        while !Task.isCancelled {
            update?(state)
            if !state.isActive { await JobCenter.shared.refresh(); return }
            try? await Task.sleep(nanoseconds: 1_000_000_000)
            guard !Task.isCancelled else { return }
            do { state = try await BrokerClient.call(["job-status", state.id], as: ManagedJob.self) }
            catch {
                // An observation error does not prove the worker stopped. Keep
                // its last active state and retry, retaining Start/Stop guards.
                await JobCenter.shared.refresh()
            }
        }
    }

    func cancel() {
        cancellationRequested = true
        guard let id else { return }
        Task {
            do { _ = try await BrokerClient.call(["cancel", id], as: ManagedJob.self) }
            catch { JobCenter.shared.reportOperationError(error.localizedDescription) }
        }
    }
}
