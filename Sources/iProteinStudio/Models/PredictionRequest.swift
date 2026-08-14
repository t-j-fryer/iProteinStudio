import Foundation

/// How a batch of sequences is assembled into folds.
enum PairingMode: String, CaseIterable, Codable, Identifiable, Hashable {
    case monomer, shared, paired

    var id: String { rawValue }

    var label: String {
        switch self {
        case .monomer: return "On their own"
        case .shared:  return "All against one partner"
        case .paired:  return "Each with its own partner"
        }
    }

    var blurb: String {
        switch self {
        case .monomer:
            return "Fold each sequence by itself."
        case .shared:
            return "Fold every sequence against the same partner — a screen against one target."
        case .paired:
            return "Each row brings its own partner. Needs a CSV with a partner column; a FASTA has nowhere to put one."
        }
    }
}

/// What to do about a chain's multiple-sequence alignment.
enum MSAPolicy: String, CaseIterable, Codable, Identifiable, Hashable {
    /// Reuse a cached alignment, or generate one if this machine has never seen
    /// the sequence.
    case auto
    /// Fold from the single sequence.
    case empty

    var id: String { rawValue }

    var label: String {
        switch self {
        case .auto:  return "Use an alignment"
        case .empty: return "Single sequence"
        }
    }

    var blurb: String {
        switch self {
        case .auto:
            return "Reused from the cache when this machine has aligned the sequence before, generated once otherwise."
        case .empty:
            return "Right for anything designed rather than evolved — a de-novo binder has no homologues, so an alignment costs time and adds nothing."
        }
    }
}

/// One fold in a batch.
struct FoldJob: Codable, Hashable, Identifiable {
    struct Chain: Codable, Hashable, Identifiable {
        var id: String
        var kind: String          // "protein" | "ligand"
        var sequence: String = ""
        var smiles: String = ""
        var msa: String = "auto"
    }
    var name: String
    var chains: [Chain]
    var id: String { name }

    var summary: String {
        chains.map { chain in
            chain.kind == "ligand" ? "\(chain.id): ligand"
                                   : "\(chain.id): \(chain.sequence.count) aa"
        }.joined(separator: " · ")
    }

    var tokenEstimate: Int {
        chains.reduce(0) { $0 + ($1.kind == "ligand" ? 40 : $1.sequence.count) }
    }
}

/// Everything the prediction tab needs to run a batch.
struct PredictionRequest: Codable, Hashable {
    /// Sequences typed directly, one per line or as FASTA.
    var pastedSequences: String = ""
    /// A FASTA or CSV the user chose instead.
    var sequenceFile: String = ""

    var pairing: PairingMode = .monomer
    var partnerSequence: String = ""
    var partnerSmiles: String = ""

    var binderMSA: MSAPolicy = .auto
    var partnerMSA: MSAPolicy = .auto

    var predictors: [Predictor] = [.boltz]
    var intellifoldModel: IntelliFoldModel = .v2flash
    var useBoltzPotentials: Bool = false
    var runAffinityHead: Bool = false
    /// Never call the MSA server; fail instead if something isn't cached. Useful
    /// offline, and as a guard when a batch is expected to be fully cached.
    var offlineOnly: Bool = false

    /// 0 means "use the measured optimum for each predictor".
    var maxParallel: Int = 0
    var batchSize: Int = 0

    var jobs: [FoldJob] = []

    var isRunnable: Bool { !jobs.isEmpty && !predictors.isEmpty }

    /// Rough lower bound: predictions only, ignoring alignment generation.
    func estimatedSeconds(in mode: SpeedMode) -> Double {
        predictors.reduce(0.0) { total, predictor in
            total + Double(jobs.count) * predictor.measuredSeconds(in: mode)
        }
    }

    var validationIssues: [String] {
        var issues: [String] = []
        if pairing == .shared, partnerSequence.trimmingCharacters(in: .whitespaces).isEmpty,
           partnerSmiles.trimmingCharacters(in: .whitespaces).isEmpty {
            issues.append("Choose a partner sequence or SMILES to fold everything against.")
        }
        if runAffinityHead, !predictors.contains(where: { $0.hasAffinityHead }) {
            issues.append("Binding strength needs Boltz-2 — it is the only engine with an affinity head.")
        }
        if runAffinityHead, !jobs.contains(where: { $0.chains.contains { $0.kind == "ligand" } }) {
            issues.append("Binding strength only applies when there is a small molecule in the fold.")
        }
        return issues
    }

    private enum CodingKeys: String, CodingKey {
        case pastedSequences, sequenceFile, pairing, partnerSequence, partnerSmiles
        case binderMSA, partnerMSA, predictors, intellifoldModel, useBoltzPotentials, runAffinityHead
        case offlineOnly, maxParallel, batchSize, jobs
    }

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let d = PredictionRequest()
        pastedSequences   = try c.decodeIfPresent(String.self, forKey: .pastedSequences) ?? d.pastedSequences
        sequenceFile      = try c.decodeIfPresent(String.self, forKey: .sequenceFile) ?? d.sequenceFile
        pairing           = try c.decodeIfPresent(PairingMode.self, forKey: .pairing) ?? d.pairing
        partnerSequence   = try c.decodeIfPresent(String.self, forKey: .partnerSequence) ?? d.partnerSequence
        partnerSmiles     = try c.decodeIfPresent(String.self, forKey: .partnerSmiles) ?? d.partnerSmiles
        binderMSA         = try c.decodeIfPresent(MSAPolicy.self, forKey: .binderMSA) ?? d.binderMSA
        partnerMSA        = try c.decodeIfPresent(MSAPolicy.self, forKey: .partnerMSA) ?? d.partnerMSA
        predictors        = try c.decodeIfPresent([Predictor].self, forKey: .predictors) ?? d.predictors
        intellifoldModel   = try c.decodeIfPresent(IntelliFoldModel.self, forKey: .intellifoldModel) ?? d.intellifoldModel
        useBoltzPotentials = try c.decodeIfPresent(Bool.self, forKey: .useBoltzPotentials) ?? d.useBoltzPotentials
        runAffinityHead   = try c.decodeIfPresent(Bool.self, forKey: .runAffinityHead) ?? d.runAffinityHead
        offlineOnly       = try c.decodeIfPresent(Bool.self, forKey: .offlineOnly) ?? d.offlineOnly
        maxParallel       = try c.decodeIfPresent(Int.self, forKey: .maxParallel) ?? d.maxParallel
        batchSize         = try c.decodeIfPresent(Int.self, forKey: .batchSize) ?? d.batchSize
        jobs              = try c.decodeIfPresent([FoldJob].self, forKey: .jobs) ?? d.jobs
    }
}
