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
    /// If a line contains this marker, treat the run as complete even if the
    /// process hasn't exited (IntelliFold hangs on teardown after finishing).
    private var successMarker: String?
    private var resultDir: URL?
    private var resultStem: String?

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
        return PredictionStore.findModelCIF(in: dir)?.path
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

        let doc: String
        switch targetKind {
        case .protein:
            let seq = TemplateWriter.clean(sequence)
            guard seq.count >= 10 else { phase = .failed("Enter a target sequence first."); return }
            doc = "sequences:\n  - protein:\n      id: A\n      sequence: \(seq)\n      msa: empty\nversion: 1\n"
        case .ligand:
            let s = smiles.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !s.isEmpty else { phase = .failed("Enter a ligand SMILES first."); return }
            let q = s.replacingOccurrences(of: "'", with: "''")
            doc = "sequences:\n  - ligand:\n      id: A\n      smiles: '\(q)'\nversion: 1\n"
        }

        let workDir = PredictionStore.dir(for: cacheKey(targetKind: targetKind, sequence: sequence,
                                                        smiles: smiles, engine: engine, model: model))
        try? FileManager.default.createDirectory(at: workDir, withIntermediateDirectories: true)
        let yaml = workDir.appendingPathComponent("target.yaml")
        let outDir = workDir.appendingPathComponent(engine.rawValue)
        do { try doc.write(to: yaml, atomically: true, encoding: .utf8) }
        catch { phase = .failed("Could not write target YAML: \(error.localizedDescription)"); return }

        switch engine {
        case .boltz:       launchBoltz(yaml: yaml, outDir: outDir)
        case .intellifold: launchIntelliFold(yaml: yaml, outDir: outDir, model: model)
        }
    }

    func cancel() {
        done = true          // stop finish()/marker paths from overriding
        phase = .idle
        runner?.cancel()
    }

    // MARK: engines

    private func launchBoltz(yaml: URL, outDir: URL) {
        let boltz = AppPaths.support.appendingPathComponent("venvs/NanoHunter_boltz/bin/boltz")
        guard FileManager.default.isExecutableFile(atPath: boltz.path) else {
            phase = .failed("Boltz isn't installed yet. Finish setup first."); return
        }
        start()
        let args = ["predict", yaml.path, "--out_dir", outDir.path,
                    "--use_msa_server", "--msa_server_url", "https://api.colabfold.com",
                    "--accelerator", "gpu", "--devices", "1", "--override"]
        appendLog("$ boltz " + args.joined(separator: " "))
        run(executable: boltz, args: args, env: CommandBuilder.environment(), outDir: outDir, stem: nil)
    }

    private func launchIntelliFold(yaml: URL, outDir: URL, model: IntelliFoldModel) {
        let py = AppPaths.support.appendingPathComponent("venvs/NanoHunter_intellifold/bin/python")
        let runner = AppPaths.support.appendingPathComponent("src/IntelliFold/run_intellifold.py")
        guard FileManager.default.isExecutableFile(atPath: py.path) else {
            phase = .failed("IntelliFold isn't installed yet. Finish setup first."); return
        }
        guard FileManager.default.fileExists(atPath: runner.path) else {
            phase = .failed("IntelliFold runner not found. Re-run setup."); return
        }
        start()
        var env = CommandBuilder.environment()
        env["KMP_USE_SHM"] = "0"
        // Flags mirror the pipeline's IntelliFold call:
        //  --precision no      : disable bf16 (unsupported on MPS/CPU)
        //  --num_diffusion_samples 1 : one structure (much faster than the default 5)
        //  --override          : always regenerate
        let args = [runner.path, yaml.path, "--out_dir", outDir.path,
                    "--precision", "no", "--num_workers", "0", "--seed", "42",
                    "--num_diffusion_samples", "1", "--override", "--model", model.rawValue,
                    "--cache", AppPaths.intelliFoldCache.path]
        appendLog("$ intellifold run_intellifold.py \(yaml.lastPathComponent) --model \(model.rawValue)")
        // IntelliFold hangs on teardown after finishing; complete on this log line.
        successMarker = "Inference completed successfully"
        // Predictions land under <outDir>/<stem>/predictions/<stem>/
        run(executable: py, args: args, env: env, outDir: outDir, stem: yaml.deletingPathExtension().lastPathComponent)
    }

    // MARK: shared

    private func start() { log = []; phase = .running; done = false; successMarker = nil }

    private func run(executable: URL, args: [String], env: [String: String], outDir: URL, stem: String?) {
        resultDir = outDir; resultStem = stem
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
        let searchDir: URL = {
            if let stem = resultStem {
                let leaf = outDir.appendingPathComponent("\(stem)/predictions/\(stem)")
                return FileManager.default.fileExists(atPath: leaf.path) ? leaf : outDir
            }
            return outDir
        }()
        guard let cif = PredictionStore.findModelCIF(in: searchDir) else { return false }
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
