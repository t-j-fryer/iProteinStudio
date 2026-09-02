import Foundation
import Combine

/// Runs a batch of folds and reports progress.
///
/// Studio contributes the batching policy here rather than the folding: which
/// alignments already exist, how jobs group into shapes, and how many processes
/// each engine wants. The folding itself is the same backends the design tabs use.
@MainActor
final class PredictionController: ObservableObject {
    @Published var phase: RunPhase = .idle
    @Published var progress: Double = 0
    @Published var currentMessage = ""
    @Published var log: [String] = []
    @Published var outputRoot: URL?
    /// Set once the run reports it, so the UI can say how much network work was avoided.
    @Published var cacheHits: String?

    private var runner: ProcessRunner?
    private var configURL: URL?

    var isRunning: Bool { if case .running = phase { return true }; return false }

    // MARK: Parsing sequences

    /// Turn pasted text or a chosen file into jobs, without running anything.
    func buildJobs(request: PredictionRequest, workDir: URL,
                   completion: @escaping ([FoldJob], [String], String?) -> Void) {
        let python = URL(fileURLWithPath: "/usr/bin/python3")
        guard AppPaths.fm.fileExists(atPath: python.path) else {
            completion([], [], "The macOS Python runtime is unavailable. Re-run Setup so the command-line tools can be repaired.")
            return
        }
        AppPaths.stageRFD3Scripts()

        // Pasted text is written to a file so one parser handles both routes and
        // there is exactly one definition of what a valid input looks like.
        let source: URL
        if !request.sequenceFile.isEmpty {
            source = URL(fileURLWithPath: request.sequenceFile)
        } else {
            do {
                try AppPaths.fm.createDirectory(at: workDir, withIntermediateDirectories: true)
            } catch {
                completion([], [], "Could not create the prediction input folder: \(error.localizedDescription)")
                return
            }
            source = workDir.appendingPathComponent("pasted.fasta")
            do {
                try Self.asFASTA(request.pastedSequences).write(to: source, atomically: true, encoding: .utf8)
            } catch {
                completion([], [], "Could not save the pasted sequences: \(error.localizedDescription)")
                return
            }
        }

        var args = [AppPaths.parseSequencesScript.path, source.path,
                    "--mode", request.pairing.rawValue,
                    "--binder-msa", request.binderMSA.rawValue,
                    "--partner-msa", request.partnerMSA.rawValue]
        if request.pairing == .shared {
            if !request.partnerSmiles.trimmingCharacters(in: .whitespaces).isEmpty {
                args += ["--partner-smiles", request.partnerSmiles]
            } else {
                args += ["--partner", request.partnerSequence]
            }
        }

        var buffer: [String] = []
        let runner = ProcessRunner()
        self.runner = runner
        runner.launch(
            executable: python, arguments: args,
            environment: CommandBuilder.environment(),
            workingDir: AppPaths.support,
            onLine: { line in buffer.append(line) },
            onExit: { _ in
                Task { @MainActor in
                    for line in buffer.reversed() {
                        guard let data = line.data(using: .utf8),
                              let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                        else { continue }
                        if let message = payload["error"] as? String {
                            completion([], [], message); return
                        }
                        guard let rawJobs = payload["jobs"] as? [[String: Any]] else { continue }
                        let jobs = rawJobs.compactMap(Self.job(from:))
                        completion(jobs, payload["warnings"] as? [String] ?? [], nil)
                        return
                    }
                    completion([], [], "Those sequences could not be read.")
                }
            })
    }

    /// Accept bare sequences, one per line, as well as real FASTA.
    static func asFASTA(_ text: String) -> String {
        if text.contains(">") { return text }
        var out: [String] = []
        for (index, line) in text.split(whereSeparator: \.isNewline).enumerated() {
            let clean = line.trimmingCharacters(in: .whitespaces)
            guard !clean.isEmpty else { continue }
            out.append(">sequence_\(index + 1)")
            out.append(clean)
        }
        return out.joined(separator: "\n") + "\n"
    }

    private static func job(from raw: [String: Any]) -> FoldJob? {
        guard let name = raw["name"] as? String,
              let chains = raw["chains"] as? [[String: Any]] else { return nil }
        return FoldJob(name: name, chains: chains.map { chain in
            FoldJob.Chain(id: chain["id"] as? String ?? "A",
                          kind: chain["kind"] as? String ?? "protein",
                          sequence: chain["sequence"] as? String ?? "",
                          smiles: chain["smiles"] as? String ?? "",
                          msa: chain["msa"] as? String ?? "auto")
        })
    }

    // MARK: Running

    func start(request: PredictionRequest, outputDir: URL) {
        guard !isRunning else { return }
        guard request.isRunnable else {
            phase = .failed(request.validationIssues.first
                            ?? "Read the current sequences and select at least one engine.")
            return
        }
        guard request.validationIssues.isEmpty else {
            phase = .failed(request.validationIssues[0]); return
        }
        let python = URL(fileURLWithPath: "/usr/bin/python3")
        guard AppPaths.fm.fileExists(atPath: python.path) else {
            phase = .failed("The macOS Python runtime is unavailable. Re-run Setup."); return
        }
        AppPaths.stageRFD3Scripts()
        try? AppPaths.fm.createDirectory(at: outputDir, withIntermediateDirectories: true)
        let runDir = uniqueRunDirectory(in: outputDir)
        try? AppPaths.fm.createDirectory(at: runDir, withIntermediateDirectories: true)
        outputRoot = runDir

        let config = Self.config(request: request, outputDir: runDir)
        let configURL = runDir.appendingPathComponent("prediction_config.json")
        do {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(config).write(to: configURL)
        } catch {
            phase = .failed("Could not write the settings: \(error.localizedDescription)"); return
        }

        phase = .running
        progress = 0
        log = []
        cacheHits = nil
        currentMessage = "Starting…"
        self.configURL = configURL
        launch(configURL)
    }

    func retry() {
        guard !isRunning, let configURL else { return }
        phase = .running
        progress = 0
        currentMessage = "Retrying failed work…"
        log.append("Retrying from the saved prediction settings; completed outputs are reused.")
        launch(configURL)
    }

    private func launch(_ configURL: URL) {
        let python = URL(fileURLWithPath: "/usr/bin/python3")
        let runner = ProcessRunner()
        self.runner = runner
        // caffeinate: a large batch is a long job, and a sleeping Mac loses it.
        runner.launch(
            executable: URL(fileURLWithPath: "/usr/bin/caffeinate"),
            arguments: ["-dimsu", python.path, AppPaths.predictBatchScript.path,
                        "--config", configURL.path],
            environment: CommandBuilder.environment(),
            workingDir: AppPaths.support,
            onLine: { [weak self] line in self?.handle(line) },
            onExit: { [weak self] code in self?.finish(code) })
    }

    private func uniqueRunDirectory(in root: URL) -> URL {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        let base = "prediction-\(formatter.string(from: Date()))"
        var candidate = root.appendingPathComponent(base, isDirectory: true)
        var suffix = 1
        while AppPaths.fm.fileExists(atPath: candidate.path) {
            suffix += 1
            candidate = root.appendingPathComponent("\(base)-\(suffix)", isDirectory: true)
        }
        return candidate
    }

    func cancel() {
        runner?.cancel()
        phase = .cancelled
        currentMessage = "Cancelled."
    }

    static func config(request: PredictionRequest, outputDir: URL) -> PredictionConfig {
        var config = PredictionConfig()
        let boltzSelected = request.includesBoltz
        config.root = AppPaths.support.path
        config.output = outputDir.path
        config.predictors = request.effectivePredictors.map(\.runnerValue)
        config.intellifold_model = request.usesIntelliFold ? request.intellifoldModel.rawValue : nil
        // Defense in depth: old project files may contain switches selected
        // before the UI made their Boltz-only scope explicit.
        config.use_potentials = boltzSelected && request.useBoltzPotentials
        config.affinity = boltzSelected && request.containsLigand && request.runAffinityHead
        config.num_seeds = request.numberOfSeeds
        config.diffusion_samples = request.diffusionSamples
        config.max_parallel = request.maxParallel
        config.batch_size = request.batchSize
        config.msa = sharedMSAConfig(allowServer: !request.offlineOnly)
        config.jobs = request.jobs.map { job in
            PredictionConfig.Job(name: job.name, chains: job.chains.map {
                PredictionConfig.Chain(id: $0.id, kind: $0.kind,
                                       sequence: $0.sequence.isEmpty ? nil : $0.sequence,
                                       smiles: $0.smiles.isEmpty ? nil : $0.smiles,
                                       msa: $0.kind == "ligand" ? nil : $0.msa)
            })
        }
        return config
    }

    /// The one alignment search policy used by Predict and Target Prep.
    /// Keeping this here prevents a convenience fold in another tab from
    /// silently becoming a single-sequence prediction.
    static func sharedMSAConfig(allowServer: Bool) -> PredictionConfig.MSA {
        PredictionConfig.MSA(
            cache_dir: AppPaths.msaCache.path,
            // Everywhere an alignment might already exist: this app's own cache,
            // its projects, and any NanoHunter checkout on the machine. Indexing
            // is one record per file, so breadth costs almost nothing.
            index_roots: [
                AppPaths.msaCache.path,
                AppPaths.objectStore.appendingPathComponent("sha256", isDirectory: true).path,
                AppPaths.scaffoldMSACache.path,
                AppPaths.projects.path,
                AppPaths.fm.homeDirectoryForCurrentUser.appendingPathComponent("NanoHunter/output").path,
            ],
            allow_server: allowServer)
    }

    private func handle(_ line: String) {
        let parts = line.components(separatedBy: "|")
        if line.hasPrefix("PBSTAGE|"), parts.count >= 4 {
            progress = (Double(parts[2]) ?? 0) / 100.0
            currentMessage = parts[3]
            log.append(parts[3])
        } else if line.hasPrefix("PBINFO|"), parts.count >= 2 {
            let message = parts.dropFirst().joined(separator: "|")
            if message.contains("came from the cache") { cacheHits = message }
            log.append(message)
        } else if line.hasPrefix("PBFAIL|"), parts.count >= 2 {
            phase = .failed(parts.dropFirst().joined(separator: "|"))
        } else if !line.isEmpty {
            log.append(line)
        }
        if log.count > 400 { log.removeFirst(log.count - 400) }
    }

    private func finish(_ code: Int32) {
        if case .failed = phase { return }
        if case .cancelled = phase { return }
        if code == 0 {
            phase = .finished; progress = 1.0
            if currentMessage.isEmpty { currentMessage = "Finished." }
        } else {
            phase = .failed("Prediction exited with code \(code). See the log below.")
        }
    }
}

/// The on-disk settings `predict_batch.py` reads. Written next to the results so
/// a batch can be re-run from a terminal without the app.
struct PredictionConfig: Codable {
    struct Chain: Codable {
        var id: String
        var kind: String
        var sequence: String?
        var smiles: String?
        var msa: String?
    }
    struct Job: Codable { var name: String; var chains: [Chain] }
    struct MSA: Codable {
        var cache_dir: String = ""
        var index_roots: [String] = []
        var allow_server: Bool = true
    }

    var root: String = ""
    var output: String = ""
    var predictors: [String] = ["boltz"]
    var intellifold_model: String?
    var use_potentials: Bool = false
    var affinity: Bool = false
    var seed: Int = 42
    var num_seeds: Int = 1
    /// 0 preserves established per-engine defaults: five samples for Protenix
    /// v2/Mini and one for Boltz, IntelliFold, Constraint and OpenFold-3.
    var diffusion_samples: Int = 0
    var max_parallel: Int = 0
    var batch_size: Int = 0
    var msa = MSA()
    var jobs: [Job] = []
}
