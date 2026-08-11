import Foundation

/// Central owner of on-disk locations and vendored resource access.
///
/// Managed data lives under Application Support so the app is fully
/// self-contained and never touches the user's home dir layout:
///
///   ~/Library/Application Support/NanoHunterStudio/     (== REPO_ROOT)
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
        let dir = fm.homeDirectoryForCurrentUser.appendingPathComponent(".nanohunterstudio",
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
        let legacy = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("NanoHunterStudio", isDirectory: true)
        guard fm.fileExists(atPath: legacy.path) else { return }
        try? fm.moveItem(at: legacy, to: destination)
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
