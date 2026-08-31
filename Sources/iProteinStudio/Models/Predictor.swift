import Foundation

/// A backend component the setup wizard can install, keyed to the `NHSTATE|<key>`
/// markers emitted by `setup_pipeline.sh`.
enum InstallComponent: String, CaseIterable, Codable, Identifiable, Hashable {
    case boltz, mpnn, antifold, lasermpnn, intellifold, protenix, openfold3, alphafold3
    case protenixConstraint = "protenix_constraint"
    case intellifoldJAX = "intellifold_jax"
    case rfd3

    /// AlphaFold 3 and IntelliFold JAX remain decodable so old projects and
    /// run manifests still open, but they are not installable components.
    static var allCases: [InstallComponent] {
        [.boltz, .mpnn, .antifold, .lasermpnn, .intellifold, .protenix,
         .protenixConstraint, .openfold3, .rfd3]
    }

    var id: String { rawValue }

    var label: String {
        switch self {
        case .boltz:          return "Boltz-2"
        case .mpnn:           return "Sequence designers"
        case .antifold:       return "AntiFold"
        case .lasermpnn:      return "LASErMPNN"
        case .intellifold:    return "IntelliFold"
        case .protenix:       return "Protenix"
        case .protenixConstraint: return "Protenix Constraint v0.5"
        case .openfold3:      return "OpenFold-3"
        case .alphafold3:     return "AlphaFold 3 (retired)"
        case .intellifoldJAX: return "IntelliFold JAX (retired)"
        case .rfd3:           return "RFdiffusion3"
        }
    }

    /// Only the sequence designers are unconditional — they are small, and every
    /// design workflow needs one. Every prediction engine is a free choice,
    /// because they cost gigabytes and nobody needs all of them.
    var isCore: Bool { self == .mpnn }

    /// Flag that asks `setup_pipeline.sh` to install this component.
    var installFlag: String? {
        switch self {
        case .mpnn:           return nil          // always installed
        case .boltz:          return "--with-boltz"
        case .antifold:       return "--with-antifold"
        case .intellifold:    return "--with-intellifold"
        case .protenix:       return "--with-protenix"
        case .protenixConstraint: return "--with-protenix-constraint"
        case .openfold3:      return "--with-openfold3"
        case .alphafold3, .intellifoldJAX: return nil
        case .lasermpnn:      return "--with-lasermpnn"
        case .rfd3:           return "--with-rfd3"
        }
    }

    /// Roughly how much disk this costs, so the choice is informed.
    var approximateSize: String {
        switch self {
        case .mpnn:           return "~500 MB"
        case .boltz:          return "~8 GB"
        case .antifold:       return "~2 GB"
        case .intellifold:    return "~5 GB"
        case .protenix:       return "~5 GB"
        case .protenixConstraint: return "~3 GB"
        case .openfold3:      return "~4 GB"
        case .alphafold3, .intellifoldJAX: return "retired"
        case .lasermpnn:      return "~2 GB"
        case .rfd3:           return "~5 GB"
        }
    }

    /// Conservative installed footprint used only for setup consent and the
    /// free-space preflight. These are deliberately rounded product budgets,
    /// not benchmark measurements or promised transfer sizes.
    var estimatedInstalledBytes: Int64 {
        let gib: Int64 = 1_073_741_824
        switch self {
        case .mpnn:                return gib / 2
        case .boltz:               return 8 * gib
        case .antifold:            return 2 * gib
        case .intellifold:         return 5 * gib
        case .protenix:            return 5 * gib
        case .protenixConstraint:  return 3 * gib
        case .openfold3:           return 4 * gib
        case .lasermpnn:           return 2 * gib
        case .rfd3:                return 5 * gib
        case .alphafold3, .intellifoldJAX: return 0
        }
    }

    /// What stops working without it, in the user's terms.
    var whatItGivesYou: String {
        switch self {
        case .mpnn:           return "Sequence design. Always installed — every design workflow needs it."
        case .boltz:          return "The default folding engine, and the only one that predicts binding strength. Also generates alignments for the others."
        case .antifold:       return "Nanobody CDR design."
        case .intellifold:    return "A second, independent folding engine."
        case .protenix:       return "Protenix v2 for accuracy and Protenix Mini for fast previews, both on the Apple GPU."
        case .protenixConstraint:
            return "Experimental iterative design against a selected protein epitope using Protenix's trained soft pocket guidance."
        case .intellifoldJAX: return "Retired after a same-input quality-control failure on Metal."
        case .openfold3:      return "Another independent folding engine, with Apple GPU kernels."
        case .alphafold3:     return "Retired after a same-input quality-control failure on Metal."
        case .lasermpnn:      return "Ligand-aware sequence design that also places side chains."
        case .rfd3:           return "The RFdiffusion3 tab — generating binder backbones from scratch."
        }
    }

    /// Components that must come with this one for it to work at all.
    var requires: [InstallComponent] {
        switch self {
        // RFdiffusion3 designs need sequences put on them and folds to check
        // them; Boltz is the engine its campaign scripts drive.
        case .rfd3:           return [.boltz]
        default:              return []
        }
    }

    var downloadNote: String? {
        switch self {
        case .lasermpnn:      return "Ligand-aware inverse folding. Runs on CPU — there is no Apple GPU build."
        case .openfold3:      return "Downloads a ~2 GB checkpoint."
        case .protenix:       return "Installs both v2 and Mini checkpoints. GPU-only: Apple Metal is required; CPU fallback is refused."
        case .protenixConstraint:
            return "Experimental, design-only checkpoint (~1.5 GB). Native Apple GPU, strict weights, no ESM download and no CPU fallback."
        case .alphafold3, .intellifoldJAX: return "No longer installable or runnable in Studio."
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
    case protenixV2 = "protenix_v2"
    case protenixMini = "protenix_mini"
    case protenixConstraint = "protenix_constraint_v0_5"
    case alphafold3
    case openfold3
    /// Historical identity for IntelliFold's retired JAX backend.
    case intellifoldJAX

    /// Retired cases remain decodable solely for historical projects/results.
    static var allCases: [Predictor] {
        [.boltz, .boltzPotentials, .protenixV2, .protenixMini,
         .protenixConstraint, .intellifold, .openfold3]
    }

    var isAvailable: Bool {
        self != .alphafold3 && self != .intellifoldJAX
    }

    var id: String { rawValue }

    var label: String {
        switch self {
        case .boltz:           return "Boltz-2"
        case .boltzPotentials: return "Boltz-2 + potentials"
        case .intellifold:     return "IntelliFold (PyTorch)"
        case .protenixV2:      return "Protenix v2"
        case .protenixMini:    return "Protenix Mini"
        case .protenixConstraint: return "Protenix Constraint v0.5 — Experimental"
        case .alphafold3:      return "AlphaFold 3 (retired)"
        case .openfold3:       return "OpenFold-3"
        case .intellifoldJAX:  return "IntelliFold JAX/Metal (retired)"
        }
    }

    /// Value understood by `nanohunter_run.sh --predictor/--post-predictor`.
    /// Boltz with steering potentials is the same backend plus a flag, not a
    /// separate predictor name.
    var runnerValue: String {
        switch self {
        case .boltz, .boltzPotentials: return "boltz"
        case .intellifold:             return "intellifold"
        case .protenixV2:              return "protenix-v2"
        case .protenixMini:            return "protenix-mini"
        case .protenixConstraint:      return "protenix-constraint-v0.5"
        case .alphafold3:              return "alphafold3"
        case .openfold3:               return "openfold-3-mlx"
        case .intellifoldJAX:          return "intellifold-jax"
        }
    }

    var usesSteeringPotentials: Bool { self == .boltzPotentials }

    var supportsEpitopePocket: Bool {
        self == .boltz || self == .boltzPotentials || self == .protenixConstraint
    }

    /// The constraint checkpoint generates guided design hypotheses. It is not
    /// exposed as an independent unconstrained checker.
    var canPostCheck: Bool { self != .protenixConstraint }

    /// Post-prediction never uses design-time steering restraints. Keep the
    /// backend identity, but collapse the design-only Boltz variant so it
    /// cannot appear as a second, misleading checker.
    var checkingVariant: Predictor {
        self == .boltzPotentials ? .boltz : self
    }

    /// Identity used when the UI promises an independent second opinion.
    /// Mini and v2 are different Protenix checkpoints, but one model family;
    /// comparing them is useful in Predict, not orthogonal validation.
    var independenceIdentity: String {
        switch checkingVariant {
        case .protenixV2, .protenixMini, .protenixConstraint: return "protenix-family"
        default: return checkingVariant.runnerValue
        }
    }

    var component: InstallComponent {
        switch self {
        case .boltz, .boltzPotentials: return .boltz
        case .intellifold:             return .intellifold
        case .protenixV2, .protenixMini: return .protenix
        case .protenixConstraint:       return .protenixConstraint
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
        case .alphafold3:      return 0        // compatibility identity; never scheduled
        case .openfold3:       return 27.5      // p2
        case .intellifold:     return mode == .batched ? 11.4 : 41.5   // p4 x dir16 / p4
        // 71-aa cobratoxin, cached 1,087-sequence A3M, five samples on the
        // same M4 Max. See Lab Book 0030; these are whole inference phases.
        case .protenixMini:    return 5.61
        case .protenixV2:      return 17.23
        // 80-aa binder + 74-aa target, one sample, 10 recycles and 200
        // diffusion steps in the validated M4 Max constraint study.
        case .protenixConstraint: return 50.98
        case .intellifoldJAX:  return 0        // compatibility identity; never scheduled
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
            // batched scheduler it is the slowest supported engine.
            return mode == .batched ? .fastest : .slowest
        case .boltzPotentials:
            return .moderate
        case .protenixMini:
            return .fastest
        case .protenixV2:
            return .moderate
        case .protenixConstraint:
            return .slowest
        case .openfold3:
            return .slow
        case .alphafold3, .intellifoldJAX:
            return .slowest
        }
    }

    /// Only Boltz has a binding-affinity head.
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
        case .protenixV2:
            return "Accuracy-first Protenix model. On cobratoxin it matched the reference better than Mini and the other tested open predictors."
        case .protenixMini:
            return "Fast preview model using the same alignment and output contract as v2."
        case .protenixConstraint:
            return "Experimental native-MPS checkpoint that conditions iterative interface proposals on a selected target pocket."
        case .alphafold3:
            return "Retired: its experimental Metal backend failed a same-input quality control."
        case .openfold3:
            return "Open reimplementation with Apple MLX kernels. Orthogonal check."
        case .intellifoldJAX:
            return "Retired: its JAX/Metal backend failed a same-input quality control."
        }
    }

    /// Honest one-line caveat shown next to the choice. Empty when there is none.
    var caveat: String {
        switch self {
        case .alphafold3:
            return "No longer installable or runnable in Studio."
        case .intellifold:
            return "Slow when used one fold at a time; Studio batches it when possible."
        case .intellifoldJAX:
            return "No longer installable or runnable in Studio; use IntelliFold PyTorch."
        case .protenixMini:
            return "A preview model: use Protenix v2 or another independent engine before trusting a final design."
        case .protenixConstraint:
            return "Pocket conditioning was technically valid but did not robustly move the alternate epitope in the initial paired test. Treat it as a proposal prior and independently refold final sequences without the constraint."
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
            return ["selected v2-flash or full-v2 model; fp32 on MPS",
                    "10 recycles (its default)",
                    "OMP_NUM_THREADS=1 and VECLIB_MAXIMUM_THREADS=1 — ~1.3x, IntelliFold only",
                    "token buckets: auto, i.e. the exact campaign token count",
                    "CUDA-only cleanup paths patched out for MPS (bit-identical outputs)",
                    "PyTorch backend — retained after its same-input quality control passed"]
        case .alphafold3:
            return ["Retired after a same-input Metal quality-control failure"]
        case .intellifoldJAX:
            return ["Retired after a same-input Metal quality-control failure"]
        case .openfold3:
            return ["MLX attention/triangle/activation kernels enabled",
                    "3 recycles, 1 diffusion sample, 1 model seed (its defaults)",
                    "two processes — measured optimum",
                    "high memory footprint; concurrency is limited by that"]
        case .protenixV2:
            return ["native Apple MPS, fp32; CPU fallback is refused",
                    "10 recycles and 200 diffusion steps (upstream v2 defaults)",
                    "5 diffusion samples, seed 42 (upstream defaults used in validation)",
                    "uses Studio's exact cached A3M; no genetic databases"]
        case .protenixMini:
            return ["native Apple MPS, fp32; CPU fallback is refused",
                    "4 recycles and 5 diffusion steps (upstream Mini defaults)",
                    "5 diffusion samples, seed 42 (upstream defaults used in validation)",
                    "uses Studio's exact cached A3M; no genetic databases"]
        case .protenixConstraint:
            return ["native Apple MPS, fp32; CPU fallback is refused",
                    "official protenix_base_constraint_v0.5.0 checkpoint; strict loading",
                    "10 recycles, 200 diffusion steps and one sample",
                    "8 Å token-centre target-pocket prior (upstream example and validated default; not a heavy-atom cutoff)",
                    "ESM disabled: this checkpoint has no trained ESM projection",
                    "serial execution with at least 8 GiB measured MPS headroom"]
        }
    }

    /// Engines that can drive a design loop.
    ///
    /// OpenFold-3 is deliberately absent. It is a useful independent check, but
    /// it was the weakest driver in the design-campaign comparison and its
    /// per-design cost is high, so offering it here would mostly be a way to
    /// spend hours getting a worse result. It remains available as a checker.
    static var designChoices: [Predictor] {
        [.boltz, .boltzPotentials, .protenixConstraint,
         .protenixV2, .protenixMini, .intellifold]
    }

    /// Engines that can independently re-fold finished designs. Steering
    /// potentials are deliberately absent: checks remove design restraints.
    static var checkChoices: [Predictor] {
        [.boltz, .protenixV2, .protenixMini, .intellifold, .openfold3]
    }

    /// Everything the prediction tab offers, in the order it shows them.
    /// Written out rather than derived, so an engine cannot quietly disappear
    /// from the list because of a filter somewhere else.
    static var predictionChoices: [Predictor] {
        [.boltz, .protenixV2, .protenixMini, .intellifold, .openfold3]
    }

    /// Engines the iterative pipeline can use for independent checks.
    static var iterativeCheckChoices: [Predictor] {
        [.boltz, .protenixV2, .protenixMini, .intellifold, .openfold3]
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
    /// Historical per-trajectory execution, retained for old manifests and
    /// troubleshooting comparisons.
    case standard
    /// The measured engine-specific policy: campaign residency except for full
    /// Protenix v2, whose sustained MPS slowdown makes cycle waves faster.
    /// The raw value remains `batched` so existing saved projects migrate
    /// without a decoding break.
    case batched

    var id: String { rawValue }

    var label: String {
        switch self {
        case .standard: return "Compatibility"
        case .batched:  return "Optimized"
        }
    }

    var blurb: String {
        switch self {
        case .standard:
            return "Reloads the predictor for each trajectory and cycle. Use only to reproduce an older campaign or diagnose an optimized run."
        case .batched:
            return "Keeps the selected predictor loaded across the campaign. Full Protenix v2 automatically uses one directory wave per cycle because that was faster on Apple MPS."
        }
    }

    var isExperimental: Bool { false }
}
