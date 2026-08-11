import Foundation

/// Translates a `DesignRequest` into a `nanohunter_run.sh` invocation.
enum CommandBuilder {
    /// Returns the argument vector (excluding the runner path itself).
    /// `cdrRanges` (e.g. "CDR1:26-33,CDR2:51-58,CDR3:98-108") is passed as
    /// explicit `--nanobody-cdr-ranges` so the pipeline never falls back to a
    /// length-unaware CDR guess.
    static func arguments(request: DesignRequest, templateYAML: URL, outRoot: URL,
                          runName: String, cdrRanges: String? = nil, mpnnSeed: Int? = nil) -> [String] {
        var args: [String] = [
            "--predictor", "boltz",
            "--post-predictor", "intellifold",
            "--post-mode", "iptm",
            "--sequence-designer", request.designer.rawValue,
            "--template-yaml", templateYAML.path,
            "--run-name", runName,
            "--out-root", outRoot.path,
            "--num-runs", String(max(1, request.numDesigns)),
            "--num-opt-cycles", String(max(1, request.numCycles)),
            "--post-iptm-threshold", String(format: "%.2f", request.hitThreshold),
        ]
        // Random base MPNN seed so re-running a project samples NEW sequences
        // (the runner adds per-run/per-cycle offsets on top). Only matters for
        // the MPNN designers (AbMPNN/ProteinMPNN/SolubleMPNN/LigandMPNN); AntiFold
        // ignores it. Passed always so it's recorded in the command.
        if let mpnnSeed { args += ["--mpnn-seed", String(mpnnSeed)] }
        // Target MSA: use the current native-per-predictor path and require a
        // real MSA (no silent single-sequence fallback). Only for protein targets.
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
            // Helix suppression (de-novo only): bias the seed away from helices.
            if request.helixKill > 0.01 {
                args += ["--helix-kill",
                         "--negative-helix-constant", String(format: "%.2f", min(1.0, request.helixKill))]
            }
        }
        // Memory budget tuned for a personal Mac: small system reserve, use most
        // of the free memory. Always passed so calibration + auto reflect it
        // (the runner ignores these in a fixed manual run).
        args += ["--mps-memory-reserve-gb", "2", "--mps-mem-fraction", "0.8"]
        switch request.parallelMode {
        case .auto:
            args += ["--max-parallel", "auto"]
        case .performance:
            // Budget from total physical RAM (capped by the safe budget), letting
            // design use more memory and other apps swap/compress.
            args += ["--max-parallel", "auto", "--mem-basis", "total"]
        case .manual:
            args += ["--max-parallel", String(max(1, request.manualParallel))]
        }
        return args
    }

    /// Environment forcing the managed pipeline root and venv prefix.
    static func environment() -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        env["NANOHUNTER_ROOT"] = AppPaths.support.path
        env["NANOHUNTER_VENV_PREFIX"] = "NanoHunter"
        // Persistent scaffold-MSA cache, outside examples/ (which is re-staged).
        env["NANOHUNTER_SCAFFOLD_MSA_CACHE_DIR_DEFAULT"] = AppPaths.scaffoldMSACache.path
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
