import Foundation

/// Translates a `DesignRequest` into a `nanohunter_run.sh` invocation.
///
/// **Design note.** Studio deliberately does not reimplement scheduling, token
/// bucketing, or memory calibration. The runner already encodes every measured
/// optimisation (see `lab_book/0002-inherited-speed-lessons.md`) and, critically,
/// rejects a device profile whose machine/package fingerprint does not match
/// rather than silently reusing stale settings. Duplicating that logic in Swift
/// would create a second source of truth that could drift.
///
/// What that means concretely: the flags we *don't* pass matter as much as the
/// ones we do. `--intellifold-buckets` is left at its `auto` default, which
/// resolves to the exact campaign token count — the single biggest measured
/// IntelliFold win available (2.28x).
/// Overriding them here would silently undo it.
enum CommandBuilder {
    /// Returns the argument vector (excluding the runner path itself).
    /// `cdrRanges` (e.g. "CDR1:26-33,CDR2:51-58,CDR3:98-108") is passed as
    /// explicit `--nanobody-cdr-ranges` so the pipeline never falls back to a
    /// length-unaware CDR guess.
    static func arguments(request: DesignRequest, templateYAML: URL, outRoot: URL,
                          runName: String, cdrRanges: String? = nil, mpnnSeed: Int? = nil) -> [String] {
        var args: [String] = [
            // Explicit workflow. The runner defaults to nanobody, and every
            // ligand-aware designer (LigandMPNN, LASErMPNN) is rejected outside
            // protein workflow -- so leaving this implicit silently constrains
            // which designers can run.
            "--workflow", request.workflow,
            "--predictor", request.designPredictor.runnerValue,
            "--sequence-designer", request.designer.rawValue,
            "--template-yaml", templateYAML.path,
            "--run-name", runName,
            "--out-root", outRoot.path,
            "--num-runs", String(max(1, request.numDesigns)),
            "--num-opt-cycles", String(max(1, request.numCycles)),
            "--iptm-threshold", String(format: "%.2f", request.hitThreshold),
        ]

        // IntelliFold architecture is meaningful only when IntelliFold is
        // actually used. Omitting it elsewhere keeps the recorded command an
        // honest description of the models that will run.
        if request.usesIntelliFold {
            args += ["--model", (request.intellifoldModel ?? .v2flash).rawValue]
        }

        // Steering potentials are a separate method, not a cosmetic Boltz option:
        // they roughly double wall time (10.9 -> 24.1 s on the SUMO benchmark).
        // Passed explicitly in both directions so the recorded command is
        // unambiguous rather than depending on the runner's `auto` heuristic.
        // A forced pocket constraint is only *steered* towards when potentials
        // are on. Writing `force: true` into the YAML and then running without
        // them would look like targeting while doing almost nothing, so the two
        // are tied together here.
        if request.usesBoltzDesignEngine {
            let needsPotentialsForPocket = request.targetKind == .ligand
                && !request.ligandContactAtoms.isEmpty
                && request.ligandContactForce
            let needsPotentialsForEpitope = request.hasEpitopeSteering
            if request.designPredictor.usesSteeringPotentials
                || needsPotentialsForPocket || needsPotentialsForEpitope {
                args += ["--boltz-use-potentials"]
            } else {
                args += ["--boltz-no-potentials"]
            }
        }

        // Orthogonal post-prediction. The design predictor's own iPTM is
        // self-scored, so this is the number that should drive selection.
        let postPredictors = request.effectivePostPredictors
        if postPredictors.isEmpty {
            args += ["--post-predictor", "none", "--post-mode", "none"]
        } else {
            let postMode: String
            switch (request.postCheckScope, request.postOnlyHits) {
            case (.finalCycle, true):  postMode = "final-iptm"
            case (.finalCycle, false): postMode = "final"
            case (.allCycles, true):   postMode = "iptm"
            case (.allCycles, false):  postMode = "all"
            }
            args += ["--post-predictor", postPredictors.map(\.runnerValue).joined(separator: ","),
                     "--post-mode", postMode]
            if request.postOnlyHits {
                args += ["--post-iptm-threshold", String(format: "%.2f", request.hitThreshold)]
            }
            args += [request.postRunBinderAlone ? "--post-binder-alone" : "--post-no-binder-alone"]
            func appendFilter(_ flag: String, _ value: Double?) {
                args += [flag, value.map { String(format: "%.3f", $0) } ?? "off"]
            }
            appendFilter("--filter-min-iptm", request.postFilters.minimumIPTM)
            appendFilter("--filter-min-ipsae", request.postFilters.minimumIPSAEMin)
            appendFilter("--filter-max-complex-rmsd", request.postFilters.maximumComplexRMSD)
            appendFilter("--filter-min-binder-plddt", request.postFilters.minimumBinderPLDDT)
            appendFilter("--filter-max-binder-rmsd", request.postFilters.maximumBinderRMSD)
        }

        // Fresh base seed so a new launch explores new sequences while its
        // durable manifest remains exactly reproducible. Route it to the flag
        // each designer actually consumes; the runner adds run/cycle offsets.
        if let mpnnSeed {
            switch request.designer {
            case .antifold: args += ["--antifold-seed", String(mpnnSeed)]
            case .lasermpnn: args += ["--lasermpnn-seed", String(mpnnSeed)]
            default: args += ["--mpnn-seed", String(mpnnSeed)]
            }
        }

        // Redesign temperature: hotter on the first cycle to explore, cooler
        // afterwards to refine. The runner aliases the AntiFold and MPNN
        // temperature flags onto this same pair, so one control covers every
        // designer except LASErMPNN, which is configured through the environment.
        args += ["--ligand-temp-cycle1", String(format: "%.2f", request.mpnnTempCycle1),
                 "--ligand-temp-other", String(format: "%.2f", request.mpnnTempLater)]

        // Target MSA: use the current native-per-predictor path and require a
        // real MSA. `--require-target-msa` is the important one — without it an
        // unreachable MSA server silently degrades the run to single-sequence
        // mode, which changes the science without changing the command.
        if request.targetKind == .protein {
            args += ["--target-msa-mode", "auto",
                     "--target-msa-generator", "auto",
                     "--require-target-msa"]
        }

        switch request.designType {
        case .nanobody:
            args += ["--nanobody-cdrs", request.cdrs.flagValue]
            if let cdrRanges, !cdrRanges.isEmpty { args += ["--nanobody-cdr-ranges", cdrRanges] }
        case .minibinder, .peptide:
            // De-novo binder against the target: runner generates chain A.
            args += ["--random-binder",
                     "--binder-min-len", String(max(1, request.binderMinLen)),
                     "--binder-max-len", String(max(request.binderMinLen, request.binderMaxLen))]
            // Cycle-0 length/composition must be reproducible from the durable
            // manifest, not drawn from process-global randomness.
            if let mpnnSeed { args += ["--binder-random-seed", String(mpnnSeed)] }
            // Helix suppression (de-novo only): bias the seed away from helices.
            if request.helixKill > 0.01 {
                args += ["--helix-kill",
                         "--negative-helix-constant", String(format: "%.2f", min(1.0, request.helixKill))]
            }
        }

        args += schedulingArguments(request: request)

        // Idempotent and safe on a fresh run name; reuses completed cycles,
        // inverse-folding steps, post-predictions and motif placements after an
        // interruption. A partially written cycle is recomputed, because the
        // check requires the normalised structure to exist.
        if request.resumeIfPossible { args += ["--resume"] }

        return args
    }

    /// Parallelism, native batching and the device throughput profile.
    private static func schedulingArguments(request: DesignRequest) -> [String] {
        var args: [String] = []

        // Memory budget tuned for a personal Mac: small system reserve, use most
        // of the free memory. Always passed so calibration + auto reflect it
        // (the runner ignores these in a fixed manual run).
        args += ["--mps-memory-reserve-gb", "2", "--mps-mem-fraction", "0.8"]

        // Prefer a measured per-machine schedule when one exists. `auto` finds
        // the newest *compatible* profile; a machine, package, model-file or
        // runner fingerprint mismatch rejects it rather than reusing another
        // Mac's settings. It can never raise concurrency above the live one-run
        // memory calibration.
        args += ["--throughput-profile", "auto"]

        // The complete 12-trajectory × 5-cycle SUMO campaign established one
        // resident worker as the fastest measured policy for every iterative
        // design engine except full Protenix v2. Full v2 slows under sustained
        // MPS work, so it reloads once per cycle instead. This is product policy,
        // not a form preference: old saved Compatibility values are ignored and
        // direct CLI users can still request the historical scheduler explicitly.
        // Resident workers are intentionally one-process owners of the GPU.
        args += ["--max-parallel", "1"]
        if request.designPredictor == .protenixV2 {
            args += ["--design-scheduler", "cycle-wave"]
        } else {
            args += ["--design-scheduler", "resident", "--wave-batch-size", "all"]
        }
        return args
    }

    /// Environment for a specific run. Adds the settings the runner only exposes
    /// as environment variables.
    static func environment(request: DesignRequest) -> [String: String] {
        var env = environment()
        env.merge(environmentOverrides(request: request)) { _, new in new }
        return env
    }

    /// Scientific environment settings that are not represented by arguments.
    /// This deliberately excludes the user's ambient process environment so a
    /// durable run manifest never captures unrelated credentials or tokens.
    static func environmentOverrides(request: DesignRequest) -> [String: String] {
        guard request.designer == .lasermpnn else { return [:] }
        return [
            "LASERMPNN_SEQ_TEMP": String(format: "%.2f", request.lasermpnnSeqTemp),
            "LASERMPNN_FS_TEMP": String(format: "%.2f", request.lasermpnnFirstShellTemp),
        ]
    }

    /// Environment forcing the managed pipeline root and venv prefix.
    static func environment() -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        env["NANOHUNTER_ROOT"] = AppPaths.support.path
        env["NANOHUNTER_VENV_PREFIX"] = "NanoHunter"
        // Target alignments are shared by plain prediction, target preparation,
        // RFdiffusion3 verification, and iterative design. The runner still
        // validates the query sequence and requires depth >= 2 before reuse.
        env["NANOHUNTER_TARGET_MSA_CACHE_DIR_DEFAULT"] = AppPaths.msaCache.path
        // Persistent scaffold-MSA cache, outside examples/ (which is re-staged).
        env["NANOHUNTER_SCAFFOLD_MSA_CACHE_DIR_DEFAULT"] = AppPaths.scaffoldMSACache.path
        env["BOLTZ_CACHE"] = AppPaths.boltzCache.path
        env["NUMBA_CACHE_DIR"] = AppPaths.numbaCache.path
        env["INTELLIFOLD_CACHE"] = AppPaths.intelliFoldCache.path
        // Ensure user-local tools (uv, gh) are reachable.
        let localBin = AppPaths.fm.homeDirectoryForCurrentUser.appendingPathComponent(".local/bin").path
        env["PATH"] = "\(localBin):/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + (env["PATH"] ?? "")
        return env
    }

    /// Human-readable preview of the command for the UI.
    static func preview(request: DesignRequest, runName: String) -> String {
        let a = arguments(request: request,
                          templateYAML: URL(fileURLWithPath: "<template>.yaml"),
                          outRoot: URL(fileURLWithPath: "<project>"),
                          runName: runName)
        return "nanohunter_run.sh " + a.joined(separator: " ")
    }
}
