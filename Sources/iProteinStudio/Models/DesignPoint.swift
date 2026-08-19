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
    let plddt: Double
    let sequence: String
    let structurePath: String

    var id: String { "\(stage.rawValue)-\(predictor)-\(run)-\(cycle)" }

    func isHit(threshold: Double) -> Bool { iptm >= threshold }

    var label: String {
        let base = String(format: "run %02d · cycle %02d", run, cycle)
        return predictor.isEmpty ? base : "\(base) · \(predictorLabel)"
    }
    var predictorLabel: String {
        switch predictor {
        case "boltz": return "Boltz-2"
        case "intellifold": return "IntelliFold"
        case "alphafold3": return "AlphaFold 3"
        case "openfold3", "openfold-3-mlx": return "OpenFold-3"
        default: return predictor
        }
    }
    var iptmText: String { String(format: "%.3f", iptm) }
    var plddtText: String {
        let conventional = plddt <= 1.000_001 ? plddt * 100 : plddt
        return String(format: "%.1f", conventional)
    }
}
