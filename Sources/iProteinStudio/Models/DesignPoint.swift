import Foundation

/// Which stage produced a data point.
enum DesignStage: String, Hashable {
    case design       // selected iterative design predictor
    case validation   // independent post-prediction checker

    var label: String { self == .design ? "Design" : "Validation" }
}

/// A single predicted design (one run + cycle) parsed live from pipeline output.
struct DesignPoint: Identifiable, Hashable {
    let stage: DesignStage
    let predictor: String
    let run: Int
    let cycle: Int
    let iptm: Double
    let ipsaeMinimum: Double?
    let plddt: Double
    let sequence: String
    let structurePath: String
    /// Durable multi-metric verdict emitted by independent validation. Nil for
    /// design-stage rows that use the interactive iPTM threshold instead.
    let savedHitVerdict: Bool?
    let failedFilters: [String]

    init(stage: DesignStage, predictor: String, run: Int, cycle: Int,
         iptm: Double, ipsaeMinimum: Double?, plddt: Double, sequence: String,
         structurePath: String, savedHitVerdict: Bool? = nil,
         failedFilters: [String] = []) {
        self.stage = stage
        self.predictor = predictor
        self.run = run
        self.cycle = cycle
        self.iptm = iptm
        self.ipsaeMinimum = ipsaeMinimum
        self.plddt = plddt
        self.sequence = sequence
        self.structurePath = structurePath
        self.savedHitVerdict = savedHitVerdict
        self.failedFilters = failedFilters
    }

    var id: String { "\(stage.rawValue)-\(predictor)-\(run)-\(cycle)" }

    func isHit(threshold: Double) -> Bool { savedHitVerdict ?? (iptm >= threshold) }
    var isStartingStructure: Bool { stage == .design && cycle == 0 }
    var isOptimizedDesign: Bool { stage == .design && cycle > 0 }
    var stageLabel: String { isStartingStructure ? "Starting structure" : stage.label }

    var label: String {
        let base = isStartingStructure
            ? String(format: "run %02d · starting structure", run)
            : String(format: "run %02d · cycle %02d", run, cycle)
        return predictor.isEmpty ? base : "\(base) · \(predictorLabel)"
    }
    var predictorLabel: String {
        switch predictor {
        case "boltz": return "Boltz-2"
        case "intellifold": return "IntelliFold"
        case "protenix", "protenix-v2": return "Protenix v2"
        case "protenix-mini": return "Protenix Mini"
        case "protenix-constraint-v0.5": return "Protenix Constraint v0.5"
        case "alphafold3": return "AlphaFold 3 (retired)"
        case "openfold3", "openfold-3-mlx": return "OpenFold-3"
        case "unknown": return "Unknown engine"
        default: return predictor
        }
    }
    var iptmText: String { String(format: "%.3f", iptm) }
    var ipsaeText: String? {
        guard let ipsaeMinimum, ipsaeMinimum.isFinite else { return nil }
        return String(format: "%.3f", ipsaeMinimum)
    }
    var plddtText: String {
        let conventional = plddt <= 1.000_001 ? plddt * 100 : plddt
        return String(format: "%.1f", conventional)
    }
}
