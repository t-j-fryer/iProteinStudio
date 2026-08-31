import Foundation

/// Central owner of on-disk locations and vendored resource access.
///
/// Managed data lives under one space-free, app-owned root so the app is fully
/// self-contained and never borrows engine caches elsewhere in the home dir:
///
///   ~/.iproteinstudio/                                (== REPO_ROOT)
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
    /// `setup_pipeline.sh --repair-venvs` does.
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

    /// Boltz's model and chemical-component cache. Keeping it under the managed
    /// root prevents a clean install from borrowing an existing ~/.boltz.
    static var boltzCache: URL {
        let dir = support.appendingPathComponent("models/boltz2", isDirectory: true)
        try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    /// Writable cache for Boltz's Numba kernels, separate from the venv so it
    /// survives upgrades and works when installed source is read-only.
    static var numbaCache: URL {
        let dir = support.appendingPathComponent("numba_cache", isDirectory: true)
        try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    /// IntelliFold checkpoints and chemical/template data. Upstream otherwise
    /// defaults to ~/.intellifold, which would hide a dependency on an older
    /// developer install.
    static var intelliFoldCache: URL {
        support.appendingPathComponent("models/intellifold", isDirectory: true)
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

    /// Durable setup logs. They are deliberately outside staged pipeline
    /// resources, so an application update cannot erase the evidence needed to
    /// diagnose a failed multi-gigabyte installation.
    static var installerLogs: URL {
        let dir = support.appendingPathComponent("logs/installer", isDirectory: true)
        try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    static var installerLock: URL {
        support.appendingPathComponent(".install.lock", isDirectory: true)
    }

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

    /// Seed every catalogued nanobody scaffold alignment into the persistent
    /// cache configured for design runs. Existing/generated copies win.
    static func stageScaffoldMSAs() {
        let src = pipeline.appendingPathComponent("examples/nanobody_scaffolds/msas",
                                                  isDirectory: true)
        guard let scaffolds = try? fm.contentsOfDirectory(at: src,
                                                          includingPropertiesForKeys: nil)
        else { return }
        for scaffold in scaffolds {
            let alignment = scaffold.appendingPathComponent("full_msa.a3m")
            guard fm.fileExists(atPath: alignment.path) else { continue }
            let destDir = scaffoldMSACache.appendingPathComponent(scaffold.lastPathComponent,
                                                                   isDirectory: true)
            try? fm.createDirectory(at: destDir, withIntermediateDirectories: true)
            let dest = destDir.appendingPathComponent("full_msa.a3m")
            if !fm.fileExists(atPath: dest.path) {
                try? fm.copyItem(at: alignment, to: dest)
            }
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

    /// Freeze the app-owned runner and helper scripts beside a campaign before
    /// launch. Engine environments and checkpoints remain shared under
    /// `support`; only the small executable policy layer is copied. A later app
    /// update therefore cannot change a detached or resumed campaign midway.
    static func createPipelineSnapshot(in campaign: URL) throws -> URL {
        let runtime = campaign.appendingPathComponent(".studio_runtime", isDirectory: true)
        let destination = runtime.appendingPathComponent("pipeline", isDirectory: true)
        let runner = destination.appendingPathComponent("nanohunter_run.sh")
        if fm.fileExists(atPath: runner.path) { return destination }
        guard let source = bundledPipeline else {
            throw NHError.message("Bundled pipeline assets are missing from the app.")
        }
        try fm.createDirectory(at: runtime, withIntermediateDirectories: true)
        let staged = runtime.appendingPathComponent(".pipeline-stage-\(UUID().uuidString)",
                                                     isDirectory: true)
        do {
            try fm.copyItem(at: source, to: staged)
            removeGeneratedCaches(from: staged)
            for name in ["nanohunter_run.sh", "setup_pipeline.sh"] {
                let path = staged.appendingPathComponent(name).path
                try? fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: path)
            }
            let metadata: [String: Any] = [
                "schema_version": 1,
                "created_at": ISO8601DateFormatter().string(from: Date()),
                "app_version": Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "development",
                "immutable_for_campaign": true,
            ]
            let data = try JSONSerialization.data(withJSONObject: metadata,
                                                  options: [.prettyPrinted, .sortedKeys])
            try data.write(to: staged.appendingPathComponent("snapshot.json"), options: .atomic)
            try fm.moveItem(at: staged, to: destination)
        } catch {
            try? fm.removeItem(at: staged)
            throw error
        }
        return destination
    }

    // MARK: Bundled resources

    /// Vendored pipeline assets shipped inside the app bundle.
    static var bundledPipeline: URL? {
        Bundle.module.url(forResource: "pipeline", withExtension: nil)
    }

    /// Offline molecular-viewer assets (py2Dmol plus the specialised legacy
    /// 3Dmol hydrophobic-surface mode and RDKit ligand depictions).
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
        // LigandMPNN is the unconditional core install. Boltz is selected by
        // default, but remains optional so a user can intentionally install a
        // different predictor without setup being reported as a failure.
        let mpnn = venvs.appendingPathComponent("NanoHunter_ligandmpnn/bin/python")
        let source = support.appendingPathComponent("src/LigandMPNN", isDirectory: true)
        let required = [
            source.appendingPathComponent("run.py"),
            source.appendingPathComponent("model_params/proteinmpnn_v_48_020.pt"),
            source.appendingPathComponent("model_params/solublempnn_v_48_020.pt"),
            source.appendingPathComponent("model_params/ligandmpnn_v_32_010_25.pt"),
            source.appendingPathComponent("model_params/abmpnn.pt"),
        ]
        return fm.isExecutableFile(atPath: mpnn.path)
            && required.allSatisfy { fm.fileExists(atPath: $0.path) }
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
            try stageBundledItem(item, at: dest)
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
        stageScaffoldMSAs()
    }

    /// Copy to a sibling first, then swap it into place. A quit, full disk or
    /// copy error therefore leaves the previous runnable resource intact rather
    /// than deleting it before its replacement exists.
    private static func stageBundledItem(_ source: URL, at destination: URL) throws {
        let token = UUID().uuidString
        let staged = support.appendingPathComponent(".stage-\(destination.lastPathComponent)-\(token)")
        let backup = destination.deletingLastPathComponent()
            .appendingPathComponent(".backup-\(destination.lastPathComponent)-\(token)")
        try? fm.removeItem(at: staged)
        do {
            try fm.copyItem(at: source, to: staged)
            removeGeneratedCaches(from: staged)
        } catch {
            try? fm.removeItem(at: staged)
            throw error
        }

        let destinationExists = fm.fileExists(atPath: destination.path)
            || (try? fm.destinationOfSymbolicLink(atPath: destination.path)) != nil
        guard destinationExists else {
            try fm.moveItem(at: staged, to: destination)
            return
        }
        do {
            _ = try fm.replaceItemAt(
                destination,
                withItemAt: staged,
                backupItemName: backup.lastPathComponent,
                options: []
            )
            try? fm.removeItem(at: backup)
        } catch {
            try? fm.removeItem(at: staged)
            throw error
        }
    }

    /// SwiftPM's `.copy` resource rule copies the filesystem tree rather than
    /// consulting Git ignore rules. Prune generated Python/Numba artifacts from
    /// every staged payload so a developer's local cache can never ship.
    private static func removeGeneratedCaches(from root: URL) {
        let generatedDirectories: Set<String> = ["__pycache__", "numba_cache"]
        guard let enumerator = fm.enumerator(
            at: root,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        ) else { return }
        for case let item as URL in enumerator {
            if generatedDirectories.contains(item.lastPathComponent) {
                enumerator.skipDescendants()
                try? fm.removeItem(at: item)
            } else if item.pathExtension == "pyc" || item.lastPathComponent == ".DS_Store" {
                try? fm.removeItem(at: item)
            }
        }
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
        let stampFile = src.appendingPathComponent("OVERLAY_VERSION")
        let bundled = (try? String(contentsOf: stampFile, encoding: .utf8)) ?? ""
        // Also drop a copy beside the pipeline so setup_pipeline.sh can apply it
        // during a fresh install, before the app has an RFdiffusion3 to overlay.
        let staged = support.appendingPathComponent("rfd3_overlay", isDirectory: true)
        let stagedStamp = staged.appendingPathComponent("OVERLAY_VERSION")
        let stagedVersion = (try? String(contentsOf: stagedStamp, encoding: .utf8)) ?? ""
        if force || stagedVersion != bundled {
            try? fm.removeItem(at: staged)
            try? fm.copyItem(at: src, to: staged)
        }

        let root = rfd3Root
        // Nothing to overlay onto until RFdiffusion3 is installed or linked.
        guard fm.fileExists(atPath: root.path) else { return false }

        let installedStamp = root.appendingPathComponent(".studio_overlay_version")
        let installed = (try? String(contentsOf: installedStamp, encoding: .utf8)) ?? ""
        let bundledDownloader = bundledPipeline?
            .appendingPathComponent("scripts/download_verified.py")
        let installedDownloader = root.appendingPathComponent("scripts/download_verified.py")
        let downloaderChanged: Bool = {
            guard let bundledDownloader,
                  let sourceData = try? Data(contentsOf: bundledDownloader)
            else { return false }
            return (try? Data(contentsOf: installedDownloader)) != sourceData
        }()

        // Directory overlays merge so upstream/generated files survive. These
        // two retired adapters are the exception: leaving them behind on an
        // upgraded installation would preserve a direct launch route that a
        // clean installation no longer has.
        var removedRetiredAdapter = false
        for relativePath in ["scripts/af3_predict_one.py",
                             "scripts/intellifold_jax_predict_one.py"] {
            let obsolete = root.appendingPathComponent(relativePath)
            if fm.fileExists(atPath: obsolete.path) {
                try? fm.removeItem(at: obsolete)
                removedRetiredAdapter = !fm.fileExists(atPath: obsolete.path)
                    || removedRetiredAdapter
            }
        }
        guard force || bundled != installed || downloaderChanged else {
            return removedRetiredAdapter
        }

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
        if let bundledDownloader, downloaderChanged || force {
            try? fm.createDirectory(at: installedDownloader.deletingLastPathComponent(),
                                    withIntermediateDirectories: true)
            try? fm.removeItem(at: installedDownloader)
            try? fm.copyItem(at: bundledDownloader, to: installedDownloader)
            try? fm.setAttributes([.posixPermissions: 0o755],
                                  ofItemAtPath: installedDownloader.path)
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
