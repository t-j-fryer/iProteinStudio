import Foundation
import Combine

/// Structure predictor used for Target Prep.
enum TargetEngine: String, CaseIterable, Identifiable, Hashable {
    case intellifold, boltz
    case protenixV2 = "protenix_v2"
    case protenixMini = "protenix_mini"
    var id: String { rawValue }
    var label: String {
        switch self {
        case .intellifold: return "IntelliFold"
        case .boltz: return "Boltz"
        case .protenixV2: return "Protenix v2"
        case .protenixMini: return "Protenix Mini"
        }
    }

    var component: InstallComponent {
        switch self {
        case .intellifold: return .intellifold
        case .boltz: return .boltz
        case .protenixV2: return .protenixV2
        case .protenixMini: return .protenixMini
        }
    }
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

/// Predicts a target structure (one chain or a multimer) so the user can inspect
/// it and pick epitope hotspots before designing. Chain A is reserved for the
/// future binder; target chains are always B, C, D… across every backend.
@MainActor
final class TargetPredictor: ObservableObject {
    enum Phase: Equatable {
        case idle, running
        case done(String)     // cif path
        case failed(String)
    }

    @Published private(set) var phase: Phase = .idle
    @Published private(set) var log: [String] = []

    private let job = ManagedJobSession()
    private var cacheDirectory: URL?
    private var done = false
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

        let proteinChains: [ProteinChainInput]
        let ligandSMILES: String?
        switch targetKind {
        case .protein:
            guard case .success(let chains) = ProteinSequenceInput.parse(
                sequence, startingAt: 1, minimumLength: 5
            ) else {
                phase = .failed("Enter valid target chains separated by a colon."); return
            }
            proteinChains = chains
            ligandSMILES = nil
        case .ligand:
            let s = smiles.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !s.isEmpty else { phase = .failed("Enter a ligand SMILES first."); return }
            proteinChains = []
            ligandSMILES = s
        }

        let id = cacheKey(targetKind: targetKind, sequence: sequence, smiles: smiles,
                          engine: engine, model: model)
        let workDir = PredictionStore.dir(for: id)
        let outDir = workDir.appendingPathComponent("prediction-\(UUID().uuidString)")
        do { try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true) }
        catch { phase = .failed("Could not create the prediction folder: \(error.localizedDescription)"); return }
        cacheDirectory = workDir
        AppPaths.stageRFD3Scripts()

        var config = PredictionConfig()
        config.root = AppPaths.support.path
        config.output = outDir.path
        switch engine {
        case .boltz: config.predictors = [Predictor.boltz.runnerValue]
        case .intellifold: config.predictors = [Predictor.intellifold.runnerValue]
        case .protenixV2: config.predictors = [Predictor.protenixV2.runnerValue]
        case .protenixMini: config.predictors = [Predictor.protenixMini.runnerValue]
        }
        config.intellifold_model = engine == .intellifold ? model.rawValue : nil
        config.max_parallel = 1
        config.batch_size = 1
        config.msa = PredictionController.sharedMSAConfig(allowServer: true)
        let chains: [PredictionConfig.Chain]
        if targetKind == .protein {
            chains = proteinChains.map {
                PredictionConfig.Chain(id: $0.id, kind: "protein", sequence: $0.sequence,
                                       smiles: nil, msa: MSAPolicy.auto.rawValue)
            }
        } else {
            chains = [PredictionConfig.Chain(id: "B", kind: "ligand", sequence: nil,
                                             smiles: ligandSMILES, msa: nil)]
        }
        config.jobs = [PredictionConfig.Job(name: "target", chains: chains)]

        let configURL = outDir.appendingPathComponent("prediction_config.json")
        do {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(config).write(to: configURL, options: .atomic)
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
        appendLog("Using the shared MSA cache; a missing alignment will be generated once and saved.")
        resultDir = outDir
        job.submit(project: "target-library", workflow: "target_prepare", output: outDir,
                   update: { [weak self] state in
            guard let self else { return }
            self.log = state.pipeline_log_tail ?? self.log
            if state.isActive { self.phase = .running }
            else if state.status == "completed" {
                if !self.succeed(), self.phase == .running { self.phase = .failed("The job finished without a target structure.") }
            } else if state.status == "cancelled" { self.phase = .idle }
            else { self.phase = .failed(state.message ?? "The target prediction failed. Previous cached structures were kept.") }
        }, failure: { [weak self] in self?.phase = .failed($0) })
    }

    func cancel() {
        guard isRunning else { return }
        appendLog("Stopping; waiting for worker processes to exit…")
        job.cancel()
    }

    private func start() { log = []; phase = .running; done = false }

    /// Try to complete from produced output. Returns true if a structure was found.
    @discardableResult
    private func succeed() -> Bool {
        guard !done, let outDir = resultDir else { return false }
        guard let cif = PredictionStore.findModelCIF(in: outDir) else { return false }
        if let cacheDirectory {
            do {
                try JSONEncoder().encode(["directory": outDir.lastPathComponent])
                    .write(to: cacheDirectory.appendingPathComponent("current-result.json"), options: .atomic)
            } catch { phase = .failed("The structure finished but its library record could not be saved: \(error.localizedDescription)"); return false }
        }
        done = true
        phase = .done(cif.path)
        appendLog("✓ predicted structure ready")
        return true
    }

    private func appendLog(_ s: String) {
        log.append(s); if log.count > 300 { log.removeFirst(log.count - 300) }
    }
}
