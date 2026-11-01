import Foundation

/// Options are independent of installation status. Installation is checked at
/// submission, never by silently substituting a different checkpoint.
enum RFD4Predictor: String, CaseIterable, Identifiable {
    case full = "esmfold2-full-mlx", fast = "esmfold2-fast-mlx", small = "esmfold2-600-mlx"
    case boltz, intellifold, intellifoldFull = "intellifold-full"
    case protenixV2 = "protenix-v2", protenixMini = "protenix-mini", protenixConstraint = "protenix-constraint-v0.5"
    case openfold = "openfold-3-mlx"
    var id: String { rawValue }
    var family: String {
        switch self {
        case .full, .fast, .small: return "ESMFold2"
        case .boltz: return "Boltz"
        case .intellifold, .intellifoldFull: return "IntelliFold"
        case .protenixV2, .protenixMini, .protenixConstraint: return "Protenix"
        case .openfold: return "OpenFold"
        }
    }
    static let families = ["ESMFold2", "Boltz", "IntelliFold", "Protenix", "OpenFold"]
    var label: String {
        switch self {
        case .full: return "ESMFold2 Full"
        case .fast: return "ESMFold2 Fast"
        case .small: return "ESMFold2Fast-600M"
        case .boltz: return "Boltz-2"
        case .intellifold: return "IntelliFold Flash"
        case .intellifoldFull: return "IntelliFold Full"
        case .protenixV2: return "Protenix v2"
        case .protenixMini: return "Protenix Mini"
        case .protenixConstraint: return "Protenix Constraint"
        case .openfold: return "OpenFold-3"
        }
    }
    var component: InstallComponent {
        switch self {
        case .full: return .esmfold2Full
        case .fast: return .esmfold2Fast
        case .small: return .esmfold2_600
        case .boltz: return .boltz
        case .intellifold: return .intellifold
        case .intellifoldFull: return .intellifoldFull
        case .protenixV2: return .protenixV2
        case .protenixMini: return .protenixMini
        case .protenixConstraint: return .protenixConstraint
        case .openfold: return .openfold3
        }
    }
}
