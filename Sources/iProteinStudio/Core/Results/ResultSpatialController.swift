import Foundation
import Combine

/// Explicit CPU analysis, checkpointed outside immutable scientific run outputs.
@MainActor
final class ResultSpatialController: ObservableObject {
    @Published var rows: [String: ResultSpatialRow] = [:]
    @Published var busy = false
    @Published var samples: [ResultSpatialRow] = []
    @Published var failures: [String] = []
    private var buffered: [String: ResultSpatialRow] = [:]
    private var errors: [String] = []
    private var warnings: [String] = []
    private var flushTask: Task<Void, Never>?
    private var total = 0
    private var passedCount = 0
    private var pendingSamples: [ResultSpatialRow] = []
    @Published var message: String?
    @Published var inventory: String?
    private var runner: ProcessRunner?
    private var identity = UUID()
    private var completed = 0

    private func launch(_ arguments: [String], onLine: @escaping (String) -> Void, onExit: @escaping (Int32) -> Void) {
        guard let helper = AppPaths.bundledPipeline?.appendingPathComponent("scripts/results_spatial.py") else {
            message = "The bundled spatial analysis helper is missing."; busy = false; return
        }
        let python = AppPaths.support.appendingPathComponent("venvs/NanoHunter_boltz/bin/python")
        guard FileManager.default.isExecutableFile(atPath: python.path) else {
            message = "Install Boltz-2 in Setup to provide the Gemmi/RDKit analysis environment. This analysis does not run a predictor."; busy = false; return
        }
        let process = ProcessRunner(); runner = process
        var environment = CommandBuilder.environment()
        for key in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"] { environment[key] = "1" }
        process.launch(executable: python, arguments: ["-B", helper.path] + arguments,
                       environment: environment, workingDir: AppPaths.support, onLine: onLine, onExit: onExit)
    }

    func inspect(_ source: URL) {
        cancel(); identity = UUID(); let token = identity; busy = true; inventory = nil; message = nil
        launch(["inspect", source.path], onLine: { [weak self] line in
            guard let self, self.identity == token else { return }
            if let data = line.data(using: .utf8), let object = try? JSONSerialization.jsonObject(with: data),
               let pretty = try? JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys]) {
                self.inventory = String(decoding: pretty, as: UTF8.self)
            } else { self.message = line }
        }, onExit: { [weak self] code in
            guard let self, self.identity == token else { return }; self.busy = false
            if code != 0 && self.message == nil { self.message = "Could not inspect the exact assessed structure." }
        })
    }

    func run(candidates: [ResultCandidate], policy: ResultSpatialPolicy) {
        cancel(); identity = UUID(); let token = identity
        guard policy.validationMessage == nil else { message = policy.validationMessage; return }
        busy = true; rows = [:]; buffered = [:]; errors = []; warnings = []; failures = []; total = candidates.count; completed = 0; passedCount = 0; pendingSamples = []; samples = []; message = "Preparing \(candidates.count) candidates…"
        Task { [weak self] in
            do {
                let requestURL = try await Task.detached(priority: .utility) {
                    let directory = AppPaths.support.appendingPathComponent("analysis/results-spatial/v1")
                    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                    let units = candidates.map { candidate -> [String: String] in
                        let source = candidate.analysisSource
                        return ["id": candidate.id, "source_item_id": source?.id ?? "", "source": source?.structureURL.path ?? "", "source_stamp": source?.coordinateStamp ?? ""]
                    }
                    let object: [String: Any] = ["policy": try JSONSerialization.jsonObject(with: policy.json),
                        "policy_sha256": policy.digest, "cache": directory.path, "units": units]
                    let path = directory.appendingPathComponent("request-" + UUID().uuidString + ".json")
                    try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]).write(to: path, options: .atomic)
                    return path
                }.value
                guard let self, self.identity == token else { return }
                self.launch(["run", requestURL.path], onLine: { [weak self] line in
                    guard let self, self.identity == token else { return }
                    if let data = line.data(using: .utf8), let row = try? JSONDecoder().decode(ResultSpatialRow.self, from: data) {
                        self.buffered[row.id] = row; self.completed += 1
                        if row.passed { self.passedCount += 1 }
                        if self.pendingSamples.count < 25 { self.pendingSamples.append(row) }
                        if let error = row.error { self.errors.append(row.id + ": " + error) }
                        if let warning = row.geometry_warning { self.warnings.append(warning) }
                        if self.flushTask == nil {
                            self.flushTask = Task { [weak self] in
                                try? await Task.sleep(nanoseconds: 500_000_000)
                                guard let self, self.identity == token else { return }
                                self.flush()
                            }
                        }
                    } else { self.message = line }
                }, onExit: { [weak self] code in
                    guard let self, self.identity == token else { return }; self.flush(); self.busy = false
                    if code != 0 { self.message = "Spatial analysis stopped (exit \(code)). Completed units can be resumed. " + (self.message ?? "") }
                })
            } catch { if let self, self.identity == token { self.message = error.localizedDescription; self.busy = false } }
        }
    }

    private func flush() {
        flushTask?.cancel(); flushTask = nil
        rows = buffered; samples = pendingSamples; failures = Array((errors + Array(Set(warnings)).sorted()).prefix(5))
        message = "Reviewed \(completed) / \(total); \(passedCount) spatial passes; \(completed - passedCount - errors.count) criterion failures; \(errors.count) unavailable. Completed units are cached."
    }
    func cancel() {
        identity = UUID(); flushTask?.cancel(); flushTask = nil
        runner?.cancel(); runner = nil; busy = false
    }
}
