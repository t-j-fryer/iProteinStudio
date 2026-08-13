import Foundation

/// A backend component the setup wizard can install, keyed to the `NHSTATE|<key>`
/// markers emitted by `setup_pipeline.sh`.
enum InstallComponent: String, CaseIterable, Codable, Identifiable, Hashable {
    case boltz, mpnn, antifold, lasermpnn, intellifold, openfold3, alphafold3
    case intellifoldJAX = "intellifold_jax"
    case rfd3

    var id: String { rawValue }

    var label: String {
        switch self {
        case .boltz:          return "Boltz-2"
        case .mpnn:           return "Sequence designers"
        case .antifold:       return "AntiFold"
        case .lasermpnn:      return "LASErMPNN"
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
        case .lasermpnn:      return "Ligand-aware inverse folding. Runs on CPU — there is no Apple GPU build."
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
    /// IntelliFold's JAX/MPS backend. A separate engine rather than a setting,
    /// because it is a different implementation with different outputs, not a
    /// faster route to the same numbers.
    case intellifoldJAX

    var id: String { rawValue }

    var label: String {
        switch self {
        case .boltz:           return "Boltz-2"
        case .boltzPotentials: return "Boltz-2 + potentials"
        case .intellifold:     return "IntelliFold (PyTorch)"
        case .alphafold3:      return "AlphaFold 3"
        case .openfold3:       return "OpenFold-3"
        case .intellifoldJAX:  return "IntelliFold (JAX/MPS)"
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
        case .intellifoldJAX:          return "intellifold-jax"
        }
    }

    var usesSteeringPotentials: Bool { self == .boltzPotentials }

    var component: InstallComponent {
        switch self {
        case .boltz, .boltzPotentials: return .boltz
        case .intellifold:             return .intellifold
        case .alphafold3:              return .alphafold3
        case .openfold3:               return .openfold3
        case .intellifoldJAX:          return .intellifoldJAX
        }
    }

    /// Seconds per prediction at the best measured schedule, 96-aa SUMO with a
    /// cached MSA on an M4 Max. Used only for a rough "how long will this take"
    /// estimate, never shown as a precise per-engine figure.
    ///
    /// These are the compute-scaling benchmark's own numbers. IntelliFold has
    /// two, because native directory batching is the difference between it being
    /// the fastest engine and the slowest one, and only the batched scheduler
    /// uses it.
    func measuredSeconds(in mode: SpeedMode) -> Double {
        switch self {
        case .boltz:           return 10.9      // p1
        case .boltzPotentials: return 21.4      // p2
        case .alphafold3:      return mode == .batched ? 22.1 : 27.7   // p2 x b4 / p2
        case .openfold3:       return 27.5      // p2
        case .intellifold:     return mode == .batched ? 11.4 : 41.5   // p4 x dir16 / p4
        case .intellifoldJAX:  return mode == .batched ? 9.2 : 14.9     // p4 x dir16 / p1 x dir4
        }
    }

    /// How fast this engine is *relative to the others*, at the schedule the
    /// pipeline will actually use.
    ///
    /// Deliberately a band, not a multiplier. The underlying seconds move with
    /// scheduling mode, token count, recycles and machine, so a precise "3.8x"
    /// on screen would be false precision — it was also simply wrong, because it
    /// came from IntelliFold's unbatched configuration while the reference
    /// figure uses its batched one. The bands come from the compute-scaling
    /// benchmark (96-aa SUMO, cached MSA, each predictor's own default recycles,
    /// at its best measured schedule).
    func speed(in mode: SpeedMode) -> SpeedBand {
        switch self {
        case .boltz:
            return .fastest
        case .intellifold:
            // Native directory batching is what makes IntelliFold competitive:
            // ~11 s/prediction batched against ~41 s unbatched. Without the
            // batched scheduler it is the slowest of the four.
            return mode == .batched ? .fastest : .slowest
        case .boltzPotentials:
            return .moderate
        case .alphafold3, .openfold3:
            return .slow
        case .intellifoldJAX:
            return .fastest
        }
    }

    /// Only Boltz has a binding-affinity head.    /// Only Boltz has a binding-affinity head. AlphaFold 3 explicitly has none,
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
            return "The stock PyTorch build. An independent model and the natural second opinion to Boltz — fast when batched, slow when not."
        case .alphafold3:
            return "DeepMind's model, run on the Apple GPU. Strong orthogonal check; no binding-affinity head."
        case .openfold3:
            return "Open reimplementation with Apple MLX kernels. Orthogonal check."
        case .intellifoldJAX:
            return "The same IntelliFold weights on a JAX/Metal engine instead of PyTorch. About 1.24x faster, needs about twice the memory, and gives very slightly different numbers."
        }
    }

    /// Honest one-line caveat shown next to the choice. Empty when there is none.
    var caveat: String {
        switch self {
        case .alphafold3:
            return "Needs af3.bin, which you must obtain from Google under their terms — it cannot be downloaded for you."
        case .intellifold:
            return "Slowest of the four at its default ten recycles."
        case .intellifoldJAX:
            return "Needs ~27 GiB at four concurrent processes, against ~14 for the PyTorch backend. Its outputs are close to, but not identical to, that backend's."
        default:
            return ""
        }
    }

    /// Exactly what this engine will be run with, so the claim that Studio uses
    /// the optimised settings can be checked rather than taken on trust.
    /// Every line here was verified against `nanohunter_run.sh` on 2026-08-11.
    var settingsSummary: [String] {
        switch self {
        case .boltz, .boltzPotentials:
            return ["GPU accelerator, 1 device, 0 dataloader workers",
                    "3 recycles (its default)",
                    "one process — measured optimum; more processes cost 3x the memory for no gain",
                    "no PYTORCH_MPS_PREFER_METAL / FAST_MATH — both measured useless",
                    "host thread limits deliberately NOT applied — they made Boltz slower",
                    usesSteeringPotentials ? "steering potentials on" : "steering potentials off"]
        case .intellifold:
            return ["v2-flash model, fp32 (Accelerate rejects fp16/bf16 on this path)",
                    "10 recycles (its default)",
                    "OMP_NUM_THREADS=1 and VECLIB_MAXIMUM_THREADS=1 — ~1.3x, IntelliFold only",
                    "token buckets: auto, i.e. the exact campaign token count",
                    "CUDA-only cleanup paths patched out for MPS (bit-identical outputs)",
                    "PyTorch backend — the JAX backend is ~1.24x faster but has no route through the runner yet"]
        case .alphafold3:
            return ["jax_backend=mps with the portable XLA attention implementation",
                    "10 recycles, 1 diffusion sample (its defaults)",
                    "token buckets: auto, i.e. the exact campaign token count (~1.6x)",
                    "persistent JAX compilation cache, so a shape compiles once per campaign",
                    "async dispatch off — measured neutral here, negative elsewhere",
                    "native batching only in Batched scheduling (~1.4x)"]
        case .intellifoldJAX:
            return ["IntelliFold v2-flash weights on AlphaFold 3's JAX/MPS engine",
                    "portable XLA attention, async dispatch off (measured negative here)",
                    "token buckets chosen from the actual token count",
                    "persistent JAX compilation cache",
                    "~1.24x the PyTorch backend, at roughly twice the memory"]
        case .openfold3:
            return ["MLX attention/triangle/activation kernels enabled",
                    "3 recycles, 1 diffusion sample, 1 model seed (its defaults)",
                    "two processes — measured optimum",
                    "highest memory footprint of the four; concurrency is limited by that"]
        }
    }

    /// Engines that can drive a design loop.
    ///
    /// OpenFold-3 is deliberately absent. It is a useful independent check, but
    /// it was the weakest driver in the design-campaign comparison and its
    /// per-design cost is high, so offering it here would mostly be a way to
    /// spend hours getting a worse result. It remains available as a checker.
    static var designChoices: [Predictor] { [.boltz, .boltzPotentials, .intellifold, .alphafold3] }

    /// Engines that can independently re-fold finished designs. All of them.
    static var checkChoices: [Predictor] {
        [.boltz, .boltzPotentials, .intellifold, .intellifoldJAX, .alphafold3, .openfold3]
    }

    /// Everything the prediction tab offers, in the order it shows them.
    /// Written out rather than derived, so an engine cannot quietly disappear
    /// from the list because of a filter somewhere else.
    static var predictionChoices: [Predictor] {
        [.boltz, .intellifold, .intellifoldJAX, .alphafold3, .openfold3]
    }

    /// Engines the iterative pipeline can drive. The JAX backend is absent
    /// because `nanohunter_run.sh` hard-assigns IntelliFold's environment and
    /// runner; it is reachable from the RFdiffusion3 checker, which calls its
    /// adapter directly.
    static var iterativeChoices: [Predictor] {
        [.boltz, .boltzPotentials, .intellifold, .alphafold3, .openfold3]
    }
}

/// Relative speed, as a band rather than a number.
enum SpeedBand: Int, Comparable {
    case fastest = 0
    case moderate = 1
    case slow = 2
    case slowest = 3

    static func < (a: SpeedBand, b: SpeedBand) -> Bool { a.rawValue < b.rawValue }

    var label: String {
        switch self {
        case .fastest:  return "fastest"
        case .moderate: return "about twice the time"
        case .slow:     return "roughly 2–3x the time"
        case .slowest:  return "much slower unbatched"
        }
    }

    /// Filled bars, for a glanceable comparison that does not pretend to be a
    /// measurement of the user's own machine.
    var bars: Int {
        switch self {
        case .fastest:  return 1
        case .moderate: return 2
        case .slow:     return 3
        case .slowest:  return 4
        }
    }
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
