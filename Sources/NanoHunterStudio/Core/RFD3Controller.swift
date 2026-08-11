import Foundation
import Combine

/// Drives an RFdiffusion3 campaign: writes the campaign JSON, launches the
/// vendored orchestrator, and parses its `RFSTAGE` / `RFINFO` / `RFDONE` /
/// `RFFAIL` markers into progress the dashboard can show.
@MainActor
final class RFD3Controller: ObservableObject {
    @Published var phase: RunPhase = .idle
    @Published var progress: Double = 0
    @Published var currentStage: String = ""
    @Published var currentMessage: String = ""
    @Published var log: [String] = []
    @Published var campaignRoot: URL?

    private var runner: ProcessRunner?

    var isRunning: Bool { if case .running = phase { return true }; return false }

    /// The RFD3 checkout Studio should drive — either installed under the app's
    /// managed directory or symlinked to an existing one.
    static var rfd3Root: URL? {
        let root = AppPaths.rfd3Root
        let marker = root.appendingPathComponent("scripts/generate_backbones.py")
        return AppPaths.fm.fileExists(atPath: marker.path) ? root : nil
    }

    static var isAvailable: Bool {
        guard let root = rfd3Root else { return false }
        return AppPaths.fm.fileExists(atPath: root.appendingPathComponent(".venv/bin/python").path)
    }

    /// Why RFD3 cannot run, phrased for the user. `nil` when it can.
    static var unavailableReason: String? {
        guard let root = rfd3Root else {
            return "RFdiffusion3 isn't set up yet. Add it from Setup, or link an existing RFD3 folder."
        }
        if !AppPaths.fm.fileExists(atPath: root.appendingPathComponent(".venv/bin/python").path) {
            return "The RFdiffusion3 Python environment is missing. Re-run setup with RFdiffusion3 selected."
        }
        if !AppPaths.fm.fileExists(atPath: root.appendingPathComponent("weights/rfd3_core.safetensors").path) {
            return "The RFdiffusion3 MLX weights haven't been exported yet. Re-run setup with RFdiffusion3 selected."
        }
        return nil
    }

    // MARK: Launch

    func start(project: Project, request: RFD3Request) {
        guard !isRunning else { return }
        guard let rfd3Root = Self.rfd3Root else {
            phase = .failed(Self.unavailableReason ?? "RFdiffusion3 is not available.")
            return
        }

        let campaign = AppPaths.projectDir(project).appendingPathComponent("rfd3", isDirectory: true)
        try? AppPaths.fm.createDirectory(at: campaign, withIntermediateDirectories: true)
        campaignRoot = campaign

        let configURL = campaign.appendingPathComponent("config").appendingPathComponent("campaign.json")
        do {
            try AppPaths.fm.createDirectory(at: configURL.deletingLastPathComponent(),
                                            withIntermediateDirectories: true)
            let config = Self.campaignConfig(project: project, request: request,
                                             campaign: campaign, rfd3Root: rfd3Root)
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(config).write(to: configURL)
        } catch {
            phase = .failed("Could not write the campaign settings: \(error.localizedDescription)")
            return
        }

        phase = .running
        progress = 0
        log = []
        currentStage = "target"
        currentMessage = "Starting…"

        let runner = ProcessRunner()
        self.runner = runner
        // caffeinate keeps a multi-hour campaign alive across idle sleep. Without
        // it a laptop that dozes mid-run loses the GPU work in flight.
        runner.launch(
            executable: URL(fileURLWithPath: "/usr/bin/caffeinate"),
            arguments: ["-dimsu",
                        rfd3Root.appendingPathComponent(".venv/bin/python").path,
                        AppPaths.rfd3CampaignScript.path,
                        "--config", configURL.path],
            environment: CommandBuilder.environment(),
            workingDir: rfd3Root,
            onLine: { [weak self] line in self?.handle(line) },
            onExit: { [weak self] code in self?.exit(code) }
        )
    }

    func cancel() {
        runner?.cancel()
        phase = .cancelled
        currentMessage = "Cancelled."
    }

    // MARK: Config

    /// Mirrors the JSON shape `rfd3_campaign.py` expects. Encoded through
    /// `AnyCodable` rather than a struct-per-field so the ligand spec — whose
    /// shape is owned by `prepare_ligand_target.py` — stays in one place.
    static func campaignConfig(project: Project, request: RFD3Request,
                               campaign: URL, rfd3Root: URL) -> RFD3CampaignConfig {
        var config = RFD3CampaignConfig()
        config.rfd3_root = rfd3Root.path
        config.campaign_dir = campaign.path
        config.design_name = project.slug
        config.nanohunter_root = AppPaths.support.path
        config.target_kind = request.targetKind == .smallMolecule ? "small_molecule" : "protein"

        config.min_length = request.minLength
        config.max_length = request.maxLength
        config.num_bins = max(1, request.numBins)
        config.num_designs = max(1, request.numDesigns)
        config.timesteps = request.timesteps
        config.recycles = request.recycles
        config.batch_size = request.batchSize
        config.queues_per_bin = request.queuesPerBin
        config.precision = request.precision
        config.seed_base = request.seedBase

        // Spelled is_non_loopy. The user-facing name is "prefer structured".
        config.is_non_loopy = request.preferStructured
        config.infer_ori_strategy = request.originStrategy.specValue
        if request.originStrategy == .explicit { config.ori_token = request.originXYZ }

        switch request.targetKind {
        case .smallMolecule:
            config.component_id = request.componentCode.uppercased()
            var spec: [String: AnyCodable] = ["smiles": AnyCodable(request.smiles)]
            for condition in AtomCondition.allCases {
                let sites = request.sites(with: condition)
                guard !sites.isEmpty else { continue }
                spec[condition.specKey] = AnyCodable(["LIGAND": sites.joined(separator: ",")])
            }
            config.ligand_spec = spec
        case .protein:
            config.target_structure = request.targetStructurePath
            config.contig = request.targetContig
            config.hotspots = request.sites(with: .hotspot)
        }

        config.predictors = request.verification.predictors.map(\.runnerValue)
        config.use_potentials = request.verification.useBoltzPotentials
        config.run_affinity = request.verification.runAffinityHead
        config.run_apo = request.verification.runApoCheck
        config.top_n = request.verification.topN
        return config
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
        } else if line.hasPrefix("RFDONE|") {
            progress = 1.0
        } else if !line.isEmpty {
            log.append(line)
        }
        if log.count > 500 { log.removeFirst(log.count - 500) }
    }

    private func exit(_ code: Int32) {
        if case .failed = phase { return }
        if case .cancelled = phase { return }
        if code == 0 {
            phase = .finished
            progress = 1.0
            currentMessage = "Campaign finished."
        } else {
            phase = .failed("RFdiffusion3 exited with code \(code). See the log below.")
        }
    }
}

/// The on-disk campaign settings. Written verbatim to
/// `<project>/rfd3/config/campaign.json` so a run is reproducible from the file
/// alone — the same campaign can be re-run from a terminal without the app.
struct RFD3CampaignConfig: Codable {
    var rfd3_root: String = ""
    var campaign_dir: String = ""
    var design_name: String = "design"
    var nanohunter_root: String = ""
    var target_kind: String = "small_molecule"

    // Small molecule
    var component_id: String?
    var ligand_spec: [String: AnyCodable]?

    // Protein
    var target_structure: String?
    var contig: String?
    var hotspots: [String]?

    // Conditioning
    var is_non_loopy: Bool = true
    var infer_ori_strategy: String?
    var ori_token: [Double]?

    // Shape and sampling
    var min_length: Int = 65
    var max_length: Int = 150
    var num_bins: Int = 10
    var num_designs: Int = 100
    var timesteps: Int = 200
    var recycles: Int = 2
    var batch_size: Int = 8
    var queues_per_bin: Int = 2
    var precision: String = "bf16"
    var seed_base: Int = 0

    // Verification
    var predictors: [String] = ["boltz"]
    var use_potentials: Bool = true
    var run_affinity: Bool = true
    var run_apo: Bool = true
    var top_n: Int = 100
    var predict_max_parallel: Int = 4
    var boltz_chunk_size: Int = 50
    var boltz_calibrate_n: Int = 12
}

/// Minimal type-erased JSON value, enough for the ligand spec whose shape is
/// owned by `prepare_ligand_target.py` rather than by Studio.
struct AnyCodable: Codable, Hashable {
    private enum Value: Codable, Hashable {
        case string(String)
        case dictionary([String: String])
    }
    private let value: Value

    init(_ string: String) { value = .string(string) }
    init(_ dictionary: [String: String]) { value = .dictionary(dictionary) }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch value {
        case .string(let s):     try container.encode(s)
        case .dictionary(let d): try container.encode(d)
        }
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let s = try? container.decode(String.self) { value = .string(s); return }
        value = .dictionary(try container.decode([String: String].self))
    }
}
