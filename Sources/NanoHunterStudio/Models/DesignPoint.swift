import Foundation

/// Which stage produced a data point.
enum DesignStage: String, Hashable {
    case design       // first-round design predictor (Boltz)
    case validation   // secondary post-prediction (IntelliFold)

    var label: String { self == .design ? "Design" : "Validation" }
}

/// A single predicted design (one run + cycle) parsed live from pipeline output.
struct DesignPoint: Identifiable, Hashable {
    let stage: DesignStage
    let run: Int
    let cycle: Int
    let iptm: Double
    let plddt: Double
    let sequence: String
    let structurePath: String

    var id: String { "\(stage.rawValue)-\(run)-\(cycle)" }

    func isHit(threshold: Double) -> Bool { iptm >= threshold }

    var label: String { String(format: "run %02d · cycle %02d", run, cycle) }
    var iptmText: String { String(format: "%.3f", iptm) }
}
