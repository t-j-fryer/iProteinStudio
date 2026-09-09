import Foundation

/// A design method includes its checkpoint. Predictor remains the shared backend
/// identity used by Predict, post-checking and the scientific command line.
enum DesignEngine: String, Codable, Hashable, Identifiable {
    case boltz, boltzPotentials
    case protenixV2 = "protenix_v2"
    case protenixMini = "protenix_mini"
    case protenixConstraint = "protenix_constraint_v0_5"
    case intellifoldFlash = "intellifold"
    case intellifoldFull = "intellifold_full"
    case openfold3
    // Preserve unavailable historical choices so they fail visibly.
    case alphafold3, intellifoldJAX

    init(predictor: Predictor, model: IntelliFoldModel? = .v2flash) {
        self = predictor == .intellifold && model == .v2
            ? .intellifoldFull : Self(rawValue: predictor.rawValue)!
    }
    var id: String { rawValue }
    var predictor: Predictor {
        self == .intellifoldFull ? .intellifold : Predictor(rawValue: rawValue)!
    }
    var model: IntelliFoldModel? {
        switch self {
        case .intellifoldFlash: return .v2flash
        case .intellifoldFull: return .v2
        default: return nil
        }
    }
    var label: String {
        switch self {
        case .intellifoldFlash: return "IntelliFold v2 Flash"
        case .intellifoldFull: return "IntelliFold v2 Full"
        default: return predictor.label
        }
    }
    var component: InstallComponent { self == .intellifoldFull ? .intellifoldFull : predictor.component }
    var independenceIdentity: String { predictor.independenceIdentity }
    var supportsEpitopePocket: Bool { predictor.supportsEpitopePocket }
    var caveat: String { self == .intellifoldFull ? "Requires the full-v2 checkpoint. Flash and Full are the same model family for independent checking." : predictor.caveat }
    var blurb: String { predictor.blurb }
    static var choices: [DesignEngine] {
        Predictor.designChoices.flatMap { predictor in
            predictor == .intellifold ? [.intellifoldFlash, .intellifoldFull] : [DesignEngine(predictor: predictor)]
        }
    }
}
