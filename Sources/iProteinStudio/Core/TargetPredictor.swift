import Foundation
import Combine

/// Structure predictor used for Target Prep.
enum TargetEngine: String, CaseIterable, Identifiable, Hashable {
    case intellifold, boltz
    var id: String { rawValue }
    var label: String { self == .intellifold ? "IntelliFold" : "Boltz" }
}

/// IntelliFold model variants (run_intellifold.py --model choices).
enum IntelliFoldModel: String, CaseIterable, Codable, Identifiable, Hashable {
    case v2flash = "v2-flash"
    case v2 = "v2"
    var id: String { rawValue }
    var label: String {
        switch self {
        case .v2flash: return "v2-flash — smaller, validated default"
        case .v2: return "v2 — full model"
        }
    }
}

/// Predicts a monomer structure for a target sequence (Boltz or IntelliFold),
/// so the user can inspect it and pick epitope hotspots before designing.
@MainActor
final class TargetPredictor: ObservableObject {
    enum Phase: Equatable {
        case idle, running
        case done(String)     // cif path
        case failed(String)
    }

    @Published private(set) var phase: Phase = .idle
    @Published private(set) var log: [String] = []

    private var runner: ProcessRunner?
    private var done = false
    /// The shared runner emits this after every requested structure exists.
    private var successMarker: String?
    private var resultDir: URL?

    var cifPath: String? { if case .done(let p) = phase { return p } else { return nil } }
    var isRunning: Bool { phase == .running }

    /// The shared cache key for these params (matches the on-disk dir + index).
    func cacheKey(targetKind: TargetKind, sequence: String, smiles: String,
                  engine: TargetEngine, model: IntelliFoldModel) -> String {
        PredictionStore.key(targetKind: targetKind, sequence: sequence, smiles: smiles,
                            engine: engine, model: model)
    }

    /// Path to an already-computed structure for these exact params, if any.
    func cachedCIF(targetKind: TargetKind, sequence: String, smiles: String,
                   engine: TargetEngine, model: IntelliFoldModel = .v2flash) -> String? {
        let dir = PredictionStore.dir(for: cacheKey(targetKind: targetKind, sequence: sequence,
                                                    smiles: smiles, engine: engine, model: model))
        guard FileManager.default.fileExists(atPath: dir.path) else { return nil }
        return PredictionStore.findModelCIF(
            in: PredictionStore.currentResultDir(for: dir.lastPathComponent)
        )?.path
    }

    func predict(targetKind: TargetKind, sequence: String, smiles: String,
                 engine: TargetEngine, model: IntelliFoldModel = .v2flash, force: Bool = false) {
        guard !isRunning else { return }

        // Retrieve a cached result instead of recomputing, unless forced.
        if !force, let cached = cachedCIF(targetKind: targetKind, sequence: sequence,
                                          smiles: smiles, engine: engine, model: model) {
            done = true
            phase = .done(cached)
            appendLog("✓ retrieved existing \(engine.label) prediction")
            return
        }

        let proteinSequence: String?
        let ligandSMILES: String?
        switch targetKind {
        case .protein:
            let seq = TemplateWriter.clean(sequence)
            guard seq.count >= 10 else { phase = .failed("Enter a target sequence first."); return }
            proteinSequence = seq
            ligandSMILES = nil
        case .ligand:
            let s = smiles.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !s.isEmpty else { phase = .failed("Enter a ligand SMILES first."); return }
            proteinSequence = nil
            ligandSMILES = s
        }

        let id = cacheKey(targetKind: targetKind, sequence: sequence, smiles: smiles,
                          engine: engine, model: model)
        let workDir = PredictionStore.dir(for: id)
        let outDir = PredictionStore.currentResultDir(for: id)
        if force { try? FileManager.default.removeItem(at: outDir) }
        try? FileManager.default.createDirectory(at: workDir, withIntermediateDirectories: true)
        try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
        AppPaths.stageRFD3Scripts()

        var config = PredictionConfig()
        config.root = AppPaths.support.path
        config.output = outDir.path
        config.predictors = [engine == .boltz ? Predictor.boltz.runnerValue
                                              : Predictor.intellifold.runnerValue]
        config.intellifold_model = engine == .intellifold ? model.rawValue : nil
        config.max_parallel = 1
        config.batch_size = 1
        config.msa = PredictionController.sharedMSAConfig(allowServer: true)
        config.jobs = [PredictionConfig.Job(name: "target", chains: [
            PredictionConfig.Chain(id: "A", kind: targetKind == .protein ? "protein" : "ligand",
                                   sequence: proteinSequence, smiles: ligandSMILES,
                                   msa: targetKind == .protein ? MSAPolicy.auto.rawValue : nil)
        ])]

        let configURL = workDir.appendingPathComponent("target_prediction_config.json")
        do {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(config).write(to: configURL)
        } catch {
            phase = .failed("Could not write target prediction settings: \(error.localizedDescription)")
            return
        }

        let python = URL(fileURLWithPath: "/usr/bin/python3")
        guard FileManager.default.fileExists(atPath: python.path) else {
            phase = .failed("The macOS Python runtime is unavailable. Re-run Setup.")
            return
        }
        start()
        successMarker = "PBDONE|ok"
        appendLog("Using the shared MSA cache; a missing alignment will be generated once and saved.")
        run(executable: URL(fileURLWithPath: "/usr/bin/caffeinate"),
            args: ["-dimsu", python.path, AppPaths.predictBatchScript.path,
                   "--config", configURL.path],
            env: CommandBuilder.environment(), outDir: outDir)
    }

    func cancel() {
        done = true          // stop finish()/marker paths from overriding
        phase = .idle
        runner?.cancel()
    }

    // MARK: shared

    private func start() { log = []; phase = .running; done = false; successMarker = nil }

    private func run(executable: URL, args: [String], env: [String: String], outDir: URL) {
        resultDir = outDir
        let runner = ProcessRunner()
        self.runner = runner
        runner.launch(executable: executable, arguments: args, environment: env,
                      workingDir: outDir.deletingLastPathComponent(),
                      onLine: { [weak self] l in self?.handleLine(l) },
                      onExit: { [weak self] code in self?.finish(code: code) })
    }

    private func handleLine(_ line: String) {
        appendLog(line)
        if let marker = successMarker, !done, line.contains(marker) {
            // Structure is written by the time this logs; complete now and stop
            // the process (it may otherwise hang on teardown).
            if succeed() { runner?.cancel() }
        }
    }

    /// Try to complete from produced output. Returns true if a structure was found.
    @discardableResult
    private func succeed() -> Bool {
        guard !done, let outDir = resultDir else { return false }
        guard let cif = PredictionStore.findModelCIF(in: outDir) else { return false }
        done = true
        phase = .done(cif.path)
        appendLog("✓ predicted structure ready")
        return true
    }

    private func finish(code: Int32) {
        guard !done else { return }   // already completed via success marker
        if code == 0 {
            if !succeed() { phase = .failed("Prediction finished but no structure file was found.") }
        } else {
            // Non-zero exit: still salvage output if the marker-based path wrote one.
            if !succeed() { phase = .failed("Prediction exited with code \(code). See the log.") }
        }
    }


    private func appendLog(_ s: String) {
        log.append(s); if log.count > 300 { log.removeFirst(log.count - 300) }
    }
}
