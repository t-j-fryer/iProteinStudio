import Foundation
import Combine

/// Drives an RFdiffusion3 campaign.
///
/// **Studio does not orchestrate RFdiffusion3.** The production pipeline lives in
/// the RFD3 repo and is validated end to end there; Studio prepares its inputs,
/// launches it with the repo's own detached launcher, and polls the repo's own
/// status script. That division matters for two reasons:
///
/// * A 1,000-backbone campaign runs for days. It must survive the app quitting,
///   so it is double-forked under `caffeinate -dims` with a PID file — the app
///   reattaches to a running campaign rather than owning it.
/// * The pipeline encodes fixes that are invisible from the outside, above all
///   the binder-length versus Foundry-total-length accounting. Reimplementing it
///   here would silently reintroduce those bugs.
@MainActor
final class RFD3Controller: ObservableObject {
    @Published var phase: RunPhase = .idle
    @Published var progress: Double = 0
    @Published var currentStage: String = ""
    @Published var currentMessage: String = ""
    @Published var log: [String] = []
    @Published var campaignRoot: URL?
    @Published var counts: [String: Int] = [:]
    @Published var completedStages: [String] = []
    @Published var isPreparing = false

    private var runner: ProcessRunner?
    private var pollTimer: Timer?
    private var configURL: URL?

    var isRunning: Bool { if case .running = phase { return true }; return false }

    // MARK: Availability

    /// The RFD3 checkout Studio drives — installed under the managed directory
    /// or symlinked to an existing one.
    static var rfd3Root: URL? {
        let root = AppPaths.rfd3Root
        let marker = root.appendingPathComponent("scripts/design_from_yaml.py")
        return AppPaths.fm.fileExists(atPath: marker.path) ? root : nil
    }

    static var isAvailable: Bool { unavailableReason == nil }

    /// Why RFD3 cannot run, phrased for the user. `nil` when it can.
    static var unavailableReason: String? {
        let root = AppPaths.rfd3Root
        guard AppPaths.fm.fileExists(atPath: root.path) else {
            return "RFdiffusion3 isn't set up yet. Add it from Setup, or link an existing RFD3 folder."
        }
        // design_from_yaml.py carries the binder-length fix and the atom
        // preflight. An older checkout would fail deep inside Foundry instead.
        guard AppPaths.fm.fileExists(atPath: root.appendingPathComponent("scripts/design_from_yaml.py").path) else {
            return "Your RFdiffusion3 checkout is missing scripts/design_from_yaml.py, so it predates the binder-length fix. Update it before running a campaign."
        }
        if !AppPaths.fm.fileExists(atPath: root.appendingPathComponent(".venv/bin/python").path) {
            return "The RFdiffusion3 Python environment is missing. Re-run setup with RFdiffusion3 selected."
        }
        if !AppPaths.fm.fileExists(atPath: root.appendingPathComponent("weights/rfd3_core.safetensors").path) {
            return "The RFdiffusion3 MLX weights haven't been exported yet. Re-run setup with RFdiffusion3 selected."
        }
        return nil
    }

    /// True when the NISE small-molecule pipeline is present.
    static var hasNISEPipeline: Bool {
        guard let root = rfd3Root else { return false }
        return AppPaths.fm.fileExists(atPath: root.appendingPathComponent("scripts/run_rfd3_nise_campaign.py").path)
    }

    // MARK: Launch

    func start(project: Project, request: RFD3Request) {
        guard !isRunning, !isPreparing else { return }
        guard let rfd3Root = Self.rfd3Root else {
            phase = .failed(Self.unavailableReason ?? "RFdiffusion3 is not available.")
            return
        }
        AppPaths.stageRFD3Scripts()

        let campaign = AppPaths.projectDir(project).appendingPathComponent("rfd3", isDirectory: true)
        try? AppPaths.fm.createDirectory(at: campaign.appendingPathComponent("config"),
                                         withIntermediateDirectories: true)
        campaignRoot = campaign

        // Preparation is fast and GPU-free: it builds the ligand component,
        // writes the design YAML, and runs the atom preflight. Doing it before
        // detaching means a bad atom name is reported in the UI in a second,
        // rather than turning up in a log file hours later.
        let requestURL = campaign.appendingPathComponent("config/studio_request.json")
        do {
            let payload = Self.studioRequest(project: project, request: request,
                                             campaign: campaign, rfd3Root: rfd3Root)
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(payload).write(to: requestURL)
        } catch {
            phase = .failed("Could not write the campaign settings: \(error.localizedDescription)")
            return
        }

        isPreparing = true
        phase = .running
        progress = 0
        log = []
        currentStage = "prepare"
        currentMessage = "Checking your design settings…"

        let prepare = ProcessRunner()
        self.runner = prepare
        var prepared: URL?
        prepare.launch(
            executable: rfd3Root.appendingPathComponent(".venv/bin/python"),
            arguments: [AppPaths.rfd3PrepareScript.path, requestURL.path],
            environment: CommandBuilder.environment(),
            workingDir: rfd3Root,
            onLine: { [weak self] line in
                guard let self else { return }
                if line.hasPrefix("PREPOK|") {
                    prepared = URL(fileURLWithPath: String(line.dropFirst("PREPOK|".count)))
                } else if line.hasPrefix("PREPFAIL|") {
                    self.phase = .failed(String(line.dropFirst("PREPFAIL|".count)))
                } else if !line.isEmpty {
                    self.log.append(line)
                }
            },
            onExit: { [weak self] code in
                guard let self else { return }
                self.isPreparing = false
                if case .failed = self.phase { return }
                guard code == 0, let config = prepared else {
                    self.phase = .failed("Your design settings were rejected. \(self.log.suffix(3).joined(separator: " "))")
                    return
                }
                self.launchCampaign(config: config, request: request, rfd3Root: rfd3Root)
            }
        )
    }

    /// Hand the prepared campaign to the RFD3 repo's own detached launcher.
    private func launchCampaign(config: URL, request: RFD3Request, rfd3Root: URL) {
        configURL = config
        currentStage = "validate"
        currentMessage = "Starting the campaign…"

        let isSmallMolecule = request.targetKind == .smallMolecule
        let launcher = isSmallMolecule
            ? rfd3Root.appendingPathComponent("scripts/launch_rfd3_nise_campaign.py").path
            : AppPaths.rfd3ProteinScript.path

        if isSmallMolecule && !Self.hasNISEPipeline {
            phase = .failed("Your RFdiffusion3 checkout has no scripts/run_rfd3_nise_campaign.py, so the small-molecule pipeline isn't available. Update it.")
            return
        }

        let runner = ProcessRunner()
        self.runner = runner
        // The small-molecule launcher double-forks and returns immediately, so
        // the campaign outlives this process and the app. The protein path is
        // shorter, so it is run in the foreground under caffeinate.
        let executable = isSmallMolecule
            ? rfd3Root.appendingPathComponent(".venv/bin/python")
            : URL(fileURLWithPath: "/usr/bin/caffeinate")
        let arguments = isSmallMolecule
            ? [launcher, "--config", config.path]
            : ["-dims", rfd3Root.appendingPathComponent(".venv/bin/python").path,
               launcher, "--config", config.path]

        runner.launch(
            executable: executable,
            arguments: arguments,
            environment: CommandBuilder.environment(),
            workingDir: rfd3Root,
            onLine: { [weak self] line in self?.handle(line) },
            onExit: { [weak self] code in self?.exit(code, detached: isSmallMolecule) }
        )
        if isSmallMolecule { startPolling() }
    }

    func cancel() {
        pollTimer?.invalidate(); pollTimer = nil
        // A detached campaign is not ours to kill from here; stop the PID it
        // recorded, then let polling notice.
        if let campaign = campaignRoot {
            let pidFile = campaign.appendingPathComponent("campaign.pid")
            if let text = try? String(contentsOf: pidFile, encoding: .utf8),
               let pid = Int32(text.trimmingCharacters(in: .whitespacesAndNewlines)) {
                kill(pid, SIGTERM)
            }
        }
        runner?.cancel()
        phase = .cancelled
        currentMessage = "Cancelled."
    }

    // MARK: Reattach + polling

    /// Look for a campaign already running for this project and reattach to it.
    /// A multi-day run must not appear to have vanished because the app restarted.
    func reattachIfRunning(project: Project) {
        let campaign = AppPaths.projectDir(project).appendingPathComponent("rfd3", isDirectory: true)
        let config = campaign.appendingPathComponent("config/campaign.json")
        guard AppPaths.fm.fileExists(atPath: config.path) else { return }
        campaignRoot = campaign
        configURL = config
        refreshStatus()
        if isRunning { startPolling() }
    }

    private func startPolling() {
        pollTimer?.invalidate()
        // Campaign stages are minutes to hours long; polling faster would only
        // spawn processes for no new information.
        pollTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refreshStatus() }
        }
        refreshStatus()
    }

    /// Ask the RFD3 repo's status script where the campaign is.
    func refreshStatus() {
        guard let config = configURL, let rfd3Root = Self.rfd3Root else { return }
        let script = rfd3Root.appendingPathComponent("scripts/status_rfd3_nise_campaign.py")
        guard AppPaths.fm.fileExists(atPath: script.path) else { return }

        let process = Process()
        process.executableURL = rfd3Root.appendingPathComponent(".venv/bin/python")
        process.arguments = [script.path, "--config", config.path, "--tail", "0"]
        process.currentDirectoryURL = rfd3Root
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        do { try process.run() } catch { return }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()

        guard let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        completedStages = payload["completed_stages"] as? [String] ?? []
        if let stage = payload["current_stage"] as? String { currentStage = stage }
        counts = payload["counts"] as? [String: Int] ?? [:]

        let alive = payload["process_alive"] as? Bool ?? false
        if alive {
            phase = .running
            currentMessage = describe(stage: currentStage)
        } else if completedStages.contains("rmsd") {
            phase = .finished
            progress = 1.0
            currentMessage = "Campaign finished."
            pollTimer?.invalidate(); pollTimer = nil
        } else if case .running = phase {
            phase = .failed("The campaign stopped during \(currentStage.isEmpty ? "startup" : currentStage). Check campaign.stdout.log in the campaign folder.")
            pollTimer?.invalidate(); pollTimer = nil
        }
        progress = fractionComplete()
    }

    private func describe(stage: String) -> String {
        switch stage {
        case "validate":     return "Checking the target and building the chemical component…"
        case "fixtures":     return "Building one fixture per binder length…"
        case "backbones":    return "Generating backbones — \(counts["backbones"] ?? 0) so far"
        case "mpnn":         return "Designing sequences — \(counts["sequences"] ?? 0) so far"
        case "predict-holo": return "Folding designs with the target — \(counts["holo_predictions"] ?? 0) so far"
        case "score":        return "Ranking by ligand pLDDT and P(bind)…"
        case "predict-apo":  return "Folding the best designs on their own — \(counts["apo_predictions"] ?? 0) so far"
        case "rmsd":         return "Measuring binding-site preorganisation…"
        default:             return stage.isEmpty ? "Working…" : stage
        }
    }

    /// Weighted by where the time actually goes: the affinity-enabled folds
    /// dominate a campaign, so a stage-count progress bar would sit at "nearly
    /// done" for days.
    private func fractionComplete() -> Double {
        let weights: [(String, Double)] = [("validate", 0.01), ("fixtures", 0.03),
                                           ("backbones", 0.16), ("mpnn", 0.10),
                                           ("predict-holo", 0.55), ("score", 0.01),
                                           ("predict-apo", 0.12), ("rmsd", 0.02)]
        var total = 0.0
        for (stage, weight) in weights where completedStages.contains(stage) { total += weight }
        return min(1.0, total)
    }

    // MARK: Output parsing

    private func handle(_ line: String) {
        let parts = line.components(separatedBy: "|")
        if line.hasPrefix("RFSTAGE|"), parts.count >= 4 {
            currentStage = parts[1]
            progress = (Double(parts[2]) ?? 0) / 100.0
            currentMessage = parts[3]
            log.append(parts[3])
        } else if line.hasPrefix("RFINFO|"), parts.count >= 2 {
            log.append(parts[1])
        } else if line.hasPrefix("RFFAIL|"), parts.count >= 2 {
            phase = .failed(parts.dropFirst().joined(separator: "|"))
        } else if !line.isEmpty {
            log.append(line)
        }
        if log.count > 500 { log.removeFirst(log.count - 500) }
    }

    private func exit(_ code: Int32, detached: Bool) {
        if case .failed = phase { return }
        if case .cancelled = phase { return }
        if detached {
            // The launcher returning only means the campaign was handed off.
            // Polling decides whether it is actually alive.
            refreshStatus()
            return
        }
        if code == 0 {
            phase = .finished
            progress = 1.0
            currentMessage = "Finished."
        } else {
            phase = .failed("RFdiffusion3 exited with code \(code). See the log below.")
        }
    }

    // MARK: Request payload

    /// What `prepare_campaign.py` consumes. Written to
    /// `<project>/rfd3/config/studio_request.json` so a campaign can be rebuilt
    /// from disk without the app.
    static func studioRequest(project: Project, request: RFD3Request,
                              campaign: URL, rfd3Root: URL) -> RFD3StudioRequest {
        var payload = RFD3StudioRequest()
        payload.rfd3_root = rfd3Root.path
        payload.campaign_dir = campaign.path
        payload.design_name = project.slug
        payload.nanohunter_root = AppPaths.support.path
        payload.target_kind = request.targetKind == .smallMolecule ? "small_molecule" : "protein"

        payload.lengths = request.binLengths
        payload.num_backbones = max(1, request.numDesigns)
        payload.timesteps = request.timesteps
        payload.recycles = request.recycles
        payload.batch_size = request.batchSize
        payload.queues_per_bin = request.queuesPerBin
        payload.precision = request.precision
        payload.seed_base = request.seedBase
        payload.sequences_per_backbone = request.sequencesPerBackbone
        payload.sequence_model = request.sequenceModel.configValue
        payload.sequence_temperature = request.sequenceTemperature
        payload.first_shell_temperature = request.firstShellTemperature
        payload.top_n = request.verification.topN
        payload.use_potentials = request.verification.useBoltzPotentials
        // The affinity head is trained on small molecules; asking for it against
        // a protein target would produce a number that means nothing.
        payload.run_affinity = request.verification.runAffinityHead && request.targetKind == .smallMolecule
        payload.run_apo = request.verification.runApoCheck
        payload.extra_predictors = request.verification.extraPredictors.map(\.runnerValue)
        payload.is_non_loopy = request.preferStructured
        payload.infer_ori_strategy = request.originStrategy.specValue
        if request.originStrategy == .explicit { payload.ori_token = request.originXYZ }

        switch request.targetKind {
        case .smallMolecule:
            payload.component_id = request.componentCode.uppercased()
            payload.ligand_source = request.ligandSource == .smiles ? "smiles" : "structure_file"
            payload.smiles = request.smiles
            payload.ligand_structure = request.ligandStructurePath
            payload.ligand_residue = request.ligandResidueName
            payload.conformers = request.conformerPlan.map {
                ["path": AnyJSON($0.path), "weight": AnyJSON($0.weight), "label": AnyJSON($0.label)]
            }
        case .protein:
            payload.target_structure = request.targetStructurePath
            payload.target_sequence = request.targetSequence
            payload.target_chain = request.targetChain
            // Contig carries the binder range plus the fixed target motif.
            // design_from_yaml.py converts binder length to Foundry's total
            // component length per bin; writing `length` here would break that.
            let motif = request.targetContig.isEmpty
                ? "\(request.targetChain)1-1"
                : request.targetContig
            payload.contig = "\(request.minLength)-\(request.maxLength),/0,\(motif)"
        }

        payload.conditions = request.conditions.mapValues { $0.map(\.rawValue).sorted() }
        return payload
    }
}

/// The Studio-side request. Deliberately flat and JSON-native so
/// `prepare_campaign.py` owns the translation into RFD3's own file formats.
struct RFD3StudioRequest: Codable {
    var rfd3_root: String = ""
    var campaign_dir: String = ""
    var design_name: String = "design"
    var nanohunter_root: String = ""
    var target_kind: String = "small_molecule"

    var component_id: String?
    var ligand_source: String?
    var smiles: String?
    var ligand_structure: String?
    var ligand_residue: String?

    var target_structure: String?
    var target_sequence: String?
    var target_chain: String?
    var contig: String?

    var conditions: [String: [String]] = [:]
    var is_non_loopy: Bool = true
    var infer_ori_strategy: String?
    var ori_token: [Double]?

    var lengths: [Int] = [65]
    var num_backbones: Int = 100
    var timesteps: Int = 200
    var recycles: Int = 2
    var batch_size: Int = 4
    var queues_per_bin: Int = 2
    var precision: String = "bf16"
    var seed_base: Int = 0
    var sequences_per_backbone: Int = 4
    var sequence_model: String = "lasermpnn"
    var sequence_temperature: Double = 0.10
    var first_shell_temperature: Double = 1.00
    var top_n: Int = 100
    var use_potentials: Bool = true
    var run_affinity: Bool = true
    var run_apo: Bool = true
    var extra_predictors: [String] = []
    var conformers: [[String: AnyJSON]] = []
    var mpnn_max_parallel: Int = 6
    var boltz_chunk_size: Int = 50
    var boltz_calibrate_n: Int = 12
}

/// A JSON scalar: string or number. Enough for the conformer plan, whose shape
/// is fixed by `design_from_yaml.py --conformers` rather than by Studio.
enum AnyJSON: Codable, Hashable {
    case string(String)
    case number(Double)

    init(_ value: String) { self = .string(value) }
    init(_ value: Double) { self = .number(value) }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let s): try container.encode(s)
        case .number(let d): try container.encode(d)
        }
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let d = try? container.decode(Double.self) { self = .number(d); return }
        self = .string(try container.decode(String.self))
    }
}
