import Foundation

/// A backend component the setup wizard can install, keyed to the `NHSTATE|<key>`
/// markers emitted by `setup_pipeline.sh`.
enum InstallComponent: String, CaseIterable, Codable, Identifiable, Hashable {
    case boltz, mpnn, antifold, intellifold, openfold3, alphafold3, intellifoldJAX = "intellifold_jax", rfd3

    var id: String { rawValue }

    var label: String {
        switch self {
        case .boltz:          return "Boltz-2"
        case .mpnn:           return "Sequence designers"
        case .antifold:       return "AntiFold"
        case .intellifold:    return "IntelliFold"
        case .openfold3:      return "OpenFold-3"
        case .alphafold3:     return "AlphaFold 3"
        case .intellifoldJAX: return "IntelliFold (JAX)"
        case .rfd3:           return "RFdiffusion3"
        }
    }

    /// Core components are installed unconditionally; the rest are opt-in because
    /// they cost gigabytes, and AlphaFold 3 additionally needs user-supplied weights.
    var isCore: Bool {
        switch self {
        case .boltz, .mpnn, .antifold, .intellifold: return true
        default: return false
        }
    }

    /// Flag that asks `setup_pipeline.sh` to install this component.
    var installFlag: String? {
        switch self {
        case .openfold3:      return "--with-openfold3"
        case .alphafold3:     return "--with-alphafold3"
        case .intellifoldJAX: return "--with-intellifold-jax"
        case .rfd3:           return "--with-rfd3"
        default:              return nil
        }
    }

    var downloadNote: String? {
        switch self {
        case .openfold3:      return "Downloads a ~2 GB checkpoint."
        case .alphafold3:     return "Compiles from source (slow). Weights must be obtained from Google separately."
        case .intellifoldJAX: return "Needs the AlphaFold 3 environment. Converts an existing IntelliFold checkpoint."
        case .rfd3:           return "Downloads a ~1.3 GB checkpoint."
        default:              return nil
        }
    }
}

/// A structure-prediction backend, usable for design-time prediction, for
/// orthogonal post-prediction validation, or both.
///
/// Timings are **measured, not estimated** — 96-aa SUMO at each predictor's own
/// default recycle count, at the process count that was fastest for it, on an
/// M4 Max. See `lab_book/0002-inherited-speed-lessons.md` §1. They exist so the
/// UI can show a real cost rather than asking a novice to guess.
enum Predictor: String, CaseIterable, Codable, Identifiable, Hashable {
    case boltz
    case boltzPotentials
    case intellifold
    case alphafold3
    case openfold3

    var id: String { rawValue }

    var label: String {
        switch self {
        case .boltz:           return "Boltz-2"
        case .boltzPotentials: return "Boltz-2 + potentials"
        case .intellifold:     return "IntelliFold"
        case .alphafold3:      return "AlphaFold 3"
        case .openfold3:       return "OpenFold-3"
        }
    }

    /// Value understood by `nanohunter_run.sh --predictor/--post-predictor`.
    /// Boltz with steering potentials is the same backend plus a flag, not a
    /// separate predictor name.
    var runnerValue: String {
        switch self {
        case .boltz, .boltzPotentials: return "boltz"
        case .intellifold:             return "intellifold"
        case .alphafold3:              return "alphafold3"
        case .openfold3:               return "openfold-3-mlx"
        }
    }

    var usesSteeringPotentials: Bool { self == .boltzPotentials }

    var component: InstallComponent {
        switch self {
        case .boltz, .boltzPotentials: return .boltz
        case .intellifold:             return .intellifold
        case .alphafold3:              return .alphafold3
        case .openfold3:               return .openfold3
        }
    }

    /// Seconds per prediction, 96-aa SUMO, best measured process count, M4 Max.
    var measuredSecondsPerPrediction: Double {
        switch self {
        case .boltz:           return 10.9
        case .boltzPotentials: return 21.4
        case .alphafold3:      return 27.7
        case .openfold3:       return 27.5
        case .intellifold:     return 41.5
        }
    }

    /// Process count that was fastest for this predictor. The runner's
    /// `--max-parallel auto` and device profile pick this; it is surfaced only
    /// so the UI can explain why the machine behaves differently per predictor.
    var measuredBestProcesses: Int {
        switch self {
        case .boltz:                          return 1
        case .boltzPotentials, .alphafold3, .openfold3: return 2
        case .intellifold:                    return 4
        }
    }

    /// Cost relative to plain Boltz-2, for the "roughly Nx slower" hint.
    var relativeCost: Double { measuredSecondsPerPrediction / Predictor.boltz.measuredSecondsPerPrediction }

    /// Only Boltz has a binding-affinity head. AlphaFold 3 explicitly has none,
    /// so ranking schemes that use P(bind) fall back to ligand pLDDT under AF3.
    var hasAffinityHead: Bool {
        self == .boltz || self == .boltzPotentials
    }

    var blurb: String {
        switch self {
        case .boltz:
            return "Fastest, and the default. One process already saturates the GPU."
        case .boltzPotentials:
            return "Boltz-2 with steering potentials — physically cleaner poses, about twice the time."
        case .intellifold:
            return "An independent model. Useful as a second opinion rather than as the design driver."
        case .alphafold3:
            return "DeepMind's model, run on the Apple GPU. Strong orthogonal check; no binding-affinity head."
        case .openfold3:
            return "Open reimplementation with Apple MLX kernels. Orthogonal check."
        }
    }

    /// Honest one-line caveat shown next to the choice. Empty when there is none.
    var caveat: String {
        switch self {
        case .alphafold3:
            return "Needs af3.bin, which you must obtain from Google under their terms — it cannot be downloaded for you."
        case .openfold3:
            return "Its complex-pLDDT reporting has an unresolved scale problem, so Studio shows iPTM only for OpenFold-3."
        case .intellifold:
            return "Slowest of the four at its default ten recycles."
        default:
            return ""
        }
    }

    /// Sensible design-time choices. All five can post-predict.
    static var designChoices: [Predictor] { [.boltz, .boltzPotentials, .intellifold, .alphafold3, .openfold3] }
}

/// How the campaign is scheduled across the GPU.
///
/// Studio deliberately does **not** reimplement scheduling. NanoHunter's runner
/// already encodes the per-predictor and per-length optima and refuses to reuse a
/// device profile whose machine/package fingerprint does not match. These modes
/// select between its validated strategies.
enum SpeedMode: String, CaseIterable, Codable, Identifiable, Hashable {
    /// Independent complete designs, `--max-parallel auto`, device profile honoured.
    case standard
    /// Cycle-wave: every design advances one cycle at a time and predictor inputs
    /// are grouped into persistent native batches. This is where AlphaFold 3 and
    /// IntelliFold win most, because it amortises model load and shape compilation.
    case batched

    var id: String { rawValue }

    var label: String {
        switch self {
        case .standard: return "Standard"
        case .batched:  return "Batched"
        }
    }

    var blurb: String {
        switch self {
        case .standard:
            return "Each design runs start-to-finish independently. The validated default, and the safe choice for mixed workloads."
        case .batched:
            return "Advances all designs one cycle at a time and feeds them to the model in one batch, so it loads and compiles once. Biggest gains on AlphaFold 3 and IntelliFold."
        }
    }

    /// The batched scheduler has not been validated across ligand and potentials
    /// workloads upstream, so the UI must say so rather than quietly defaulting to it.
    var isExperimental: Bool { self == .batched }
}
