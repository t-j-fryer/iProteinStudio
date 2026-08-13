import Foundation

/// Central owner of on-disk locations and vendored resource access.
///
/// Managed data lives under Application Support so the app is fully
/// self-contained and never touches the user's home dir layout:
///
///   ~/Library/Application Support/iProteinStudio/     (== REPO_ROOT)
///     nanohunter_run.sh, scripts/, examples/   vendored pipeline (staged here)
///     venvs/, src/                              installed runtime
///     scaffold_msa_cache/                       persistent scaffold-MSA cache
///     projects/     one folder per design campaign (--out-root)
///     config.json   app state
///
/// Everything the runner references as ${REPO_ROOT}/… (scripts, examples, venvs,
/// src) lives directly under this dir, so the staged runner works unmodified.
enum AppPaths {
    static let fm = FileManager.default

    /// The managed runtime root.
    ///
    /// **Not** under Application Support, and that is not a style choice. A
    /// Python console script carries an absolute shebang, and the kernel splits
    /// a shebang on whitespace — so anything pip installs into a path containing
    /// "Application Support" fails at run time with
    /// `bad interpreter: /Users/…/Library/Application`. Every venv created there
    /// would be quietly broken. A space-free home is the only way a from-scratch
    /// install can work.
    static var support: URL {
        let dir = fm.homeDirectoryForCurrentUser.appendingPathComponent(".iproteinstudio",
                                                                        isDirectory: true)
        if !fm.fileExists(atPath: dir.path) { migrateLegacyRootIfPresent(to: dir) }
        try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    /// Move an installation made by an earlier build out of Application Support.
    /// A rename on the same volume, so it is effectively instant even at ~16 GB;
    /// the venvs still need their shebangs re-pointed afterwards, which
    /// `setup_pipeline.sh --materialise` does.
    private static func migrateLegacyRootIfPresent(to destination: URL) {
        let home = fm.homeDirectoryForCurrentUser
        // In order of age. Application Support came first and could never have
        // worked for a real install (a space in the path breaks every console
        // script); ~/.nanohunterstudio was the fix; this is the rename.
        let candidates = [
            home.appendingPathComponent(".nanohunterstudio", isDirectory: true),
            fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("iProteinStudio", isDirectory: true),
            fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("NanoHunterStudio", isDirectory: true),
        ]
        for legacy in candidates where fm.fileExists(atPath: legacy.path) {
            // A rename on the same volume, so instant even at ~16 GB. The venvs
            // then need their shebangs re-pointed, which the installer's
            // --repair-venvs step does and the app triggers on next launch.
            try? fm.moveItem(at: legacy, to: destination)
            return
        }
    }

    /// The pipeline REPO_ROOT — same as `support` so staged scripts/examples sit
    /// alongside the installed venvs/src the runner expects.
    static var pipeline: URL { support }

    /// Persistent scaffold-MSA cache (kept out of examples/, which is re-staged).
    static var scaffoldMSACache: URL {
        let dir = support.appendingPathComponent("scaffold_msa_cache", isDirectory: true)
        try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    /// Persistent JAX/XLA compilation cache. AlphaFold 3 and the IntelliFold JAX
    /// backend pay a compile cost per new token shape; without a cache that is
    /// paid again on every cycle of every campaign.
    static var jaxCompileCache: URL {
        let dir = support.appendingPathComponent("jax_compile_cache", isDirectory: true)
        try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    /// RFdiffusion3 checkout — either installed here or symlinked to an existing
    /// one by `setup_pipeline.sh --link-rfd3`.
    static var rfd3Root: URL { support.appendingPathComponent("rfd3", isDirectory: true) }

    static var projects: URL {
        let dir = support.appendingPathComponent("projects", isDirectory: true)
        try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    static var configFile: URL { support.appendingPathComponent("config.json") }

    /// Studio-authored RFdiffusion3 helpers, staged alongside the pipeline.
    static var rfd3ScriptsDir: URL {
        let dir = support.appendingPathComponent("rfd3_scripts", isDirectory: true)
        try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }
    static var rfd3PrepareScript: URL { rfd3ScriptsDir.appendingPathComponent("prepare_campaign.py") }
    static var rfd3ProteinScript: URL { rfd3ScriptsDir.appendingPathComponent("rfd3_protein_campaign.py") }
    static var rfd3InspectScript: URL { rfd3ScriptsDir.appendingPathComponent("inspect_target.py") }
    static var rfd3LigandScript: URL { rfd3ScriptsDir.appendingPathComponent("ligand_intelligence.py") }
    static var boltzLigandAtomsScript: URL { rfd3ScriptsDir.appendingPathComponent("boltz_ligand_atoms.py") }
    static var predictBatchScript: URL { rfd3ScriptsDir.appendingPathComponent("predict_batch.py") }
    static var parseSequencesScript: URL { rfd3ScriptsDir.appendingPathComponent("parse_sequences.py") }

    /// Worked examples, written out of the bundle on first launch.
    static var examplesDir: URL {
        let dir = support.appendingPathComponent("examples_data", isDirectory: true)
        try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    static var bundledExamples: URL? {
        Bundle.module.url(forResource: "examples", withExtension: nil)
    }

    /// Copy the examples out, and seed the alignment cache with the one they
    /// ship. Without that seeding a new user's first action queues behind a
    /// public MSA server, which often takes longer than the fold and sometimes
    /// simply fails — the worst possible first impression, and avoidable
    /// because the alignment is already in the bundle.
    static func stageExamples() {
        guard let src = bundledExamples,
              let items = try? fm.contentsOfDirectory(at: src, includingPropertiesForKeys: nil)
        else { return }
        for item in items {
            let dest = examplesDir.appendingPathComponent(item.lastPathComponent)
            if !fm.fileExists(atPath: dest.path) {
                try? fm.copyItem(at: item, to: dest)
            }
        }
        let alignment = examplesDir.appendingPathComponent("acbx/target_msa.a3m")
        let seeded = msaCache.appendingPathComponent("example_acbx.a3m")
        if fm.fileExists(atPath: alignment.path), !fm.fileExists(atPath: seeded.path) {
            try? fm.copyItem(at: alignment, to: seeded)
        }
    }

    /// Shared alignment cache. Everything the app generates lands here, and the
    /// design side's older alignments are indexed into it, so a target aligned
    /// once is never aligned again.
    static var msaCache: URL {
        let dir = support.appendingPathComponent("msa_cache", isDirectory: true)
        try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    static var runnerScript: URL { pipeline.appendingPathComponent("nanohunter_run.sh") }
    static var setupScript: URL { pipeline.appendingPathComponent("setup_pipeline.sh") }
    static var catalogTSV: URL {
        pipeline.appendingPathComponent("examples/nanobody_scaffolds/catalog.tsv")
    }

    static func projectDir(_ project: Project) -> URL {
        let dir = projects.appendingPathComponent(project.slug, isDirectory: true)
        try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    // MARK: Bundled resources

    /// Vendored pipeline assets shipped inside the app bundle.
    static var bundledPipeline: URL? {
        Bundle.module.url(forResource: "pipeline", withExtension: nil)
    }

    /// Offline 3Dmol.js viewer assets.
    static var webRoot: URL? {
        Bundle.module.url(forResource: "web", withExtension: nil)
    }

    /// Studio-authored RFdiffusion3 helpers shipped inside the app bundle.
    static var bundledRFD3Scripts: URL? {
        Bundle.module.url(forResource: "rfd3", withExtension: nil)
    }

    /// The RFdiffusion3 script layer — campaign orchestrators, ligand
    /// preparation, predictor adapters, length binning. None of it is upstream,
    /// so a checkout without this overlay cannot run anything Studio offers.
    static var bundledRFD3Overlay: URL? {
        Bundle.module.url(forResource: "rfd3_overlay", withExtension: nil)
    }

    /// True once the pipeline runtime has been installed (venvs present).
    static var isPipelineInstalled: Bool {
        let venvs = support.appendingPathComponent("venvs", isDirectory: true)
        let boltz = venvs.appendingPathComponent("NanoHunter_boltz/bin/python")
        return fm.fileExists(atPath: boltz.path)
    }

    /// True once the vendored scripts have been copied into the managed dir.
    static var isPipelineStaged: Bool {
        fm.fileExists(atPath: runnerScript.path)
    }

    /// Copy vendored scripts/examples into the managed pipeline dir (idempotent).
    static func stagePipelineAssets() throws {
        guard let src = bundledPipeline else {
            throw NHError.message("Bundled pipeline assets are missing from the app.")
        }
        let items = try fm.contentsOfDirectory(at: src, includingPropertiesForKeys: nil)
        for item in items {
            let dest = pipeline.appendingPathComponent(item.lastPathComponent)
            if fm.fileExists(atPath: dest.path) {
                try? fm.removeItem(at: dest)
            }
            try fm.copyItem(at: item, to: dest)
        }
        // Ensure scripts are executable.
        for name in ["nanohunter_run.sh", "setup_pipeline.sh"] {
            let p = pipeline.appendingPathComponent(name).path
            if fm.fileExists(atPath: p) {
                try? fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: p)
            }
        }
        stageRFD3Scripts()
        stageRFD3Overlay()
        stageExamples()
    }

    /// Apply the RFdiffusion3 overlay to the installed checkout.
    ///
    /// This is also how an existing installation gets updates. The venvs and the
    /// multi-gigabyte weights never change, but the scripts do; re-staging them
    /// on every launch means a fix shipped in a new build reaches a machine that
    /// installed months ago, without reinstalling anything. Version-stamped so
    /// the copy only happens when the bundle actually differs.
    @discardableResult
    static func stageRFD3Overlay(force: Bool = false) -> Bool {
        guard let src = bundledRFD3Overlay else { return false }
        // Also drop a copy beside the pipeline so setup_pipeline.sh can apply it
        // during a fresh install, before the app has an RFdiffusion3 to overlay.
        let staged = support.appendingPathComponent("rfd3_overlay", isDirectory: true)
        if !fm.fileExists(atPath: staged.appendingPathComponent("OVERLAY_VERSION").path)
            || force {
            try? fm.removeItem(at: staged)
            try? fm.copyItem(at: src, to: staged)
        }

        let root = rfd3Root
        // Nothing to overlay onto until RFdiffusion3 is installed or linked.
        guard fm.fileExists(atPath: root.path) else { return false }

        let stampFile = src.appendingPathComponent("OVERLAY_VERSION")
        let installedStamp = root.appendingPathComponent(".studio_overlay_version")
        let bundled = (try? String(contentsOf: stampFile, encoding: .utf8)) ?? ""
        let installed = (try? String(contentsOf: installedStamp, encoding: .utf8)) ?? ""
        guard force || bundled != installed else { return false }

        guard let items = try? fm.contentsOfDirectory(at: src, includingPropertiesForKeys: nil)
        else { return false }
        for item in items where item.lastPathComponent != "OVERLAY_VERSION" {
            let dest = root.appendingPathComponent(item.lastPathComponent)
            var isDir: ObjCBool = false
            fm.fileExists(atPath: item.path, isDirectory: &isDir)
            if isDir.boolValue {
                // Merge rather than replace: assets/ and scripts/ may hold files
                // a campaign produced that the overlay knows nothing about.
                mergeDirectory(from: item, into: dest)
            } else {
                try? fm.removeItem(at: dest)
                try? fm.copyItem(at: item, to: dest)
                try? fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: dest.path)
            }
        }
        try? bundled.write(to: installedStamp, atomically: true, encoding: .utf8)
        return true
    }

    private static func mergeDirectory(from src: URL, into dest: URL) {
        try? fm.createDirectory(at: dest, withIntermediateDirectories: true)
        guard let items = try? fm.contentsOfDirectory(at: src, includingPropertiesForKeys: nil)
        else { return }
        for item in items {
            let target = dest.appendingPathComponent(item.lastPathComponent)
            var isDir: ObjCBool = false
            fm.fileExists(atPath: item.path, isDirectory: &isDir)
            if isDir.boolValue {
                mergeDirectory(from: item, into: target)
            } else {
                try? fm.removeItem(at: target)
                try? fm.copyItem(at: item, to: target)
                if item.pathExtension == "py" || item.pathExtension == "sh" {
                    try? fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: target.path)
                }
            }
        }
    }

    /// Stage the RFdiffusion3 helpers. Kept separate from the pipeline assets
    /// because they are Studio's own code, not vendored from NanoHunter.
    static func stageRFD3Scripts() {
        guard let src = bundledRFD3Scripts,
              let items = try? fm.contentsOfDirectory(at: src, includingPropertiesForKeys: nil)
        else { return }
        for item in items {
            let dest = rfd3ScriptsDir.appendingPathComponent(item.lastPathComponent)
            try? fm.removeItem(at: dest)
            try? fm.copyItem(at: item, to: dest)
            try? fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: dest.path)
        }
    }
}

struct NHError: LocalizedError {
    let text: String
    var errorDescription: String? { text }
    static func message(_ s: String) -> NHError { NHError(text: s) }
}
