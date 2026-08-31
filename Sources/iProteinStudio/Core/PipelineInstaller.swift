import Foundation
import Combine

/// Drives setup: stages vendored assets, then runs `setup_pipeline.sh`, parsing
/// its `NHSTEP` / `NHSTATE` / `NHDONE` / `NHFAIL` markers into friendly progress
/// and a per-component availability map.
///
/// The availability map matters for more than cosmetics: it is what lets the
/// design form refuse to offer a predictor that cannot actually run, instead of
/// letting a novice start a campaign that fails twenty minutes in.
@MainActor
final class PipelineInstaller: ObservableObject {
    struct Step: Identifiable {
        let id = UUID()
        let key: String
        var message: String
    }

    /// What `setup_pipeline.sh` reported about one backend.
    struct ComponentState: Equatable {
        enum Availability: String {
            case ok, missing, skipped, incomplete, broken, update, busy
        }
        var availability: Availability
        /// Human-readable qualifier, e.g. "environment ready — place af3.bin at …".
        var detail: String

        var isUsable: Bool { availability == .ok }
    }

    @Published var isInstalling = false
    @Published var isRemoving = false
    @Published var progress: Double = 0          // 0...1
    @Published var currentMessage = "Ready to set up iProteinStudio."
    @Published var steps: [Step] = []
    @Published var finished = false
    @Published var failure: String?
    @Published var installed = AppPaths.isPipelineInstalled
    @Published var components: [InstallComponent: ComponentState] = [:]
    @Published var latestLogURL: URL?
    @Published private(set) var safeCacheBytes: Int64 = 0
    /// The practical default installation: the folding engine, nanobody
    /// designer, independent checker, Protenix v2/Mini, and unconditional MPNN
    /// family described by onboarding. Heavy alternatives and the experimental,
    /// design-only Protenix Constraint checkpoint remain explicit opt-ins.
    @Published var optionalSelection: Set<InstallComponent> = [
        .boltz, .antifold, .intellifold, .protenixV2, .protenixMini,
    ]
    /// An existing NanoHunter checkout found on this machine, if any.
    @Published var detectedNanoHunter: URL?
    @Published var detectedRFD3: URL?

    private var runner: ProcessRunner?
    private var cancelRequested = false

    init() {
        detectExistingCheckouts()
        repairRelocatedVenvsIfNeeded()
        refreshSafeCacheSize()
    }

    /// A venv moved from another path keeps absolute references to where it came
    /// from, in its console-script shebangs and its activate scripts. Left alone
    /// it silently runs the *old* environment, or fails outright once that is
    /// gone. Detect the mismatch cheaply and re-point in the background.
    private func repairRelocatedVenvsIfNeeded() {
        let venvs = AppPaths.support.appendingPathComponent("venvs", isDirectory: true)
        var entries = (try? AppPaths.fm.contentsOfDirectory(at: venvs,
                                                            includingPropertiesForKeys: nil)) ?? []
        let rfd3Venv = AppPaths.rfd3Root.appendingPathComponent(".venv", isDirectory: true)
        if AppPaths.fm.fileExists(atPath: rfd3Venv.path) { entries.append(rfd3Venv) }
        let needsRepair = entries.contains { venv in
            let activate = venv.appendingPathComponent("bin/activate")
            guard let text = try? String(contentsOf: activate, encoding: .utf8) else { return false }
            return !text.contains(venv.path)
        }
        guard needsRepair, AppPaths.isPipelineStaged else { return }

        let runner = ProcessRunner()
        self.runner = runner
        runner.launch(
            executable: URL(fileURLWithPath: "/bin/bash"),
            arguments: [AppPaths.setupScript.path, "--repair-venvs"],
            environment: CommandBuilder.environment(),
            workingDir: AppPaths.pipeline,
            onLine: { [weak self] line in self?.handle(line, quiet: true) },
            onExit: { [weak self] _ in self?.detectComponents() }
        )
    }

    func refreshInstalledState() {
        installed = AppPaths.isPipelineInstalled
        detectComponents()
    }

    func isUsable(_ component: InstallComponent) -> Bool {
        guard components[component]?.isUsable == true else { return false }
        return component.requires.allSatisfy { components[$0]?.isUsable == true }
    }

    func detail(_ component: InstallComponent) -> String {
        components[component]?.detail ?? ""
    }

    func hasManagedFiles(_ component: InstallComponent) -> Bool {
        removalTargets(for: component).contains(where: managedItemExists)
    }

    func uninstallDescription(_ component: InstallComponent) -> String {
        var message: String
        if component == .rfd3 {
            message = "Deletes Studio's RFdiffusion3 environment and model weights. The checkout is kept to protect any legacy campaigns stored inside it."
        } else if [.boltzAffinity, .intellifoldFull, .protenixV2, .protenixMini]
            .contains(component) {
            message = "Deletes only the optional \(component.label). Its shared engine environment and other checkpoints remain installed."
        } else {
            message = "Deletes Studio's \(component.label) environment, managed source (if any), model weights and engine caches."
        }
        message += " Prediction and design results, workspaces, and saved MSAs are kept."
        let dependents = InstallComponent.allCases.filter {
            $0.requires.contains(component) && hasManagedFiles($0)
        }
        if !dependents.isEmpty {
            message += " \(dependents.map(\.label).joined(separator: ", ")) will stop working until \(component.label) is reinstalled."
        }
        message += " If this engine is linked to another installation, only Studio's link is removed; the original is untouched."
        return message
    }

    /// Remove only the selected engine's managed environment/source/models.
    /// Project results and both MSA caches are deliberately outside every plan.
    func uninstall(_ component: InstallComponent) {
        guard !isInstalling, !isRemoving, !component.isCore else { return }
        guard !AppPaths.fm.fileExists(atPath: AppPaths.installerLock.path) else {
            failure = "An installation or repair is already changing the managed runtime. Wait for it to finish before removing an engine."
            currentMessage = "The managed runtime is busy."
            return
        }
        guard !engineAppearsBusy(component) else {
            failure = "\(component.label) appears to be in use. Stop its active prediction or design run before uninstalling it."
            currentMessage = "Could not remove an engine that is running."
            return
        }
        let root = AppPaths.support.standardizedFileURL
        let targets = removalTargets(for: component).filter {
            $0.standardizedFileURL.path.hasPrefix(root.path + "/") && managedItemExists($0)
        }
        guard !targets.isEmpty else {
            components[component] = ComponentState(availability: .missing, detail: "")
            return
        }
        isRemoving = true
        failure = nil
        currentMessage = "Removing \(component.label)…"
        Task.detached(priority: .utility) {
            var failures: [String] = []
            for target in targets {
                do { try FileManager.default.removeItem(at: target) }
                catch { failures.append("\(target.lastPathComponent): \(error.localizedDescription)") }
            }
            let removalFailures = failures
            await MainActor.run {
                self.isRemoving = false
                if removalFailures.isEmpty {
                    self.components[component] = ComponentState(availability: .missing, detail: "removed")
                    self.currentMessage = "\(component.label) removed. Workspaces and alignments were kept."
                } else {
                    self.failure = "Could not completely remove \(component.label): " + removalFailures.joined(separator: "; ")
                    self.currentMessage = "Removal incomplete."
                }
                self.detectComponents()
            }
        }
    }

    private func removalTargets(for component: InstallComponent) -> [URL] {
        var relative: [String]
        switch component {
        case .boltz:
            relative = ["venvs/NanoHunter_boltz", "models/boltz2", "numba_cache",
                        "components/boltz", "receipts/boltz.json", "receipts/boltz_affinity.json"]
        case .boltzAffinity:
            relative = ["models/boltz2/boltz2_aff.ckpt", "receipts/boltz_affinity.json"]
        case .mpnn:
            relative = ["venvs/NanoHunter_ligandmpnn", "src/LigandMPNN",
                        "components/mpnn", "receipts/mpnn.json"]
        case .antifold:
            relative = ["venvs/NanoHunter_antifold", "src/AntiFold",
                        "components/antifold", "receipts/antifold.json"]
        case .lasermpnn:
            relative = ["venvs/NanoHunter_lasermpnn", "src/LASErMPNN",
                        "components/lasermpnn", "receipts/lasermpnn.json"]
        case .intellifold:
            relative = ["venvs/NanoHunter_intellifold", "src/IntelliFold", "models/intellifold",
                        "components/intellifold", "receipts/intellifold.json",
                        "receipts/intellifold_full.json"]
        case .intellifoldFull:
            relative = ["models/intellifold/intellifold_v2.pt", "receipts/intellifold_full.json"]
        case .protenix:
            relative = ["venvs/NanoHunter_protenix", "src/Protenix", "models/protenix/common",
                        "components/protenix", "receipts/protenix.json"]
            if !managedItemExists(AppPaths.support
                .appendingPathComponent("venvs/NanoHunter_protenix_constraint")) {
                relative.append("shared/protenix-common")
            }
        case .protenixV2:
            relative = ["models/protenix/checkpoint/protenix-v2.pt", "receipts/protenix_v2.json"]
        case .protenixMini:
            relative = ["models/protenix/checkpoint/protenix_mini_default_v0.5.0.pt",
                        "receipts/protenix_mini.json"]
        case .protenixConstraint:
            relative = ["venvs/NanoHunter_protenix_constraint", "src/ProtenixConstraint",
                        "models/protenix_constraint", "components/protenix_constraint",
                        "receipts/protenix_constraint.json"]
            if !managedItemExists(AppPaths.support
                .appendingPathComponent("venvs/NanoHunter_protenix")) {
                relative.append("shared/protenix-common")
            }
        case .openfold3:
            relative = ["venvs/NanoHunter_openfold3_mlx", "src/openfold-3-mlx", "models/openfold3",
                        "components/openfold3", "receipts/openfold3.json"]
        case .alphafold3:
            relative = ["venvs/NanoHunter_alphafold3", "src/alphafold3", "models/alphafold3"]
        case .intellifoldJAX:
            relative = ["models/intellifold_jax_flash", "models/intellifold_jax_v2"]
        case .rfd3:
            let rfd3 = AppPaths.rfd3Root
            if (try? AppPaths.fm.destinationOfSymbolicLink(atPath: rfd3.path)) != nil { return [rfd3] }
            relative = ["rfd3/.venv", "rfd3/checkpoints", "rfd3/weights", "receipts/rfd3.json"]
        }
        return relative.map { AppPaths.support.appendingPathComponent($0) }
    }

    private func managedItemExists(_ url: URL) -> Bool {
        AppPaths.fm.fileExists(atPath: url.path)
            || (try? AppPaths.fm.destinationOfSymbolicLink(atPath: url.path)) != nil
    }

    private func engineAppearsBusy(_ component: InstallComponent) -> Bool {
        for target in removalTargets(for: component) {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
            process.arguments = ["-f", target.path]
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice
            do {
                try process.run()
                process.waitUntilExit()
                if process.terminationStatus == 0 { return true }
            } catch { return false }
        }
        return false
    }

    // MARK: Reuse of an existing local install

    /// Look for an already-installed NanoHunter / RFD3 next to the user's home
    /// directory. Reusing one avoids duplicating tens of gigabytes of venvs and
    /// model weights on a machine that already has them.
    private func detectExistingCheckouts() {
        let home = AppPaths.fm.homeDirectoryForCurrentUser
        for name in ["NanoHunter", "iProteinHunter"] {
            let candidate = home.appendingPathComponent(name)
            let marker = candidate.appendingPathComponent("venvs/NanoHunter_boltz/bin/python")
            if AppPaths.fm.fileExists(atPath: marker.path) { detectedNanoHunter = candidate; break }
        }
        for name in ["RFD3", "rfd3"] {
            let candidate = home.appendingPathComponent(name)
            if AppPaths.fm.fileExists(atPath: candidate.appendingPathComponent("install_rfd3.sh").path) {
                detectedRFD3 = candidate; break
            }
        }
    }

    /// Point the app at an existing installation via symlink instead of
    /// reinstalling. The app keeps its own vendored runner and examples, so the
    /// pinned pipeline version still applies — only the heavy environments are
    /// shared.
    func linkExisting(nanoHunter: URL?, rfd3: URL?) {
        var extra: [String] = []
        if let nanoHunter { extra += ["--link-existing", nanoHunter.path] }
        if let rfd3 { extra += ["--link-rfd3", rfd3.path] }
        guard !extra.isEmpty else { return }
        launch(extraArguments: extra, startMessage: "Linking to your existing installation…")
    }

    // MARK: Install

    func install() {
        var requested = expandedSelection(optionalSelection)
        requested.insert(.mpnn)
        let requiredBytes = requested
            .filter { !isUsable($0) }
            .reduce(Int64(0)) { total, component in
                total + max(0, component.estimatedInstalledBytes - managedAllocatedBytes(for: component))
            }
        guard preflightFreeSpace(requiredBytes: requiredBytes) else { return }
        var extra: [String] = []
        for component in requested.sorted(by: { $0.rawValue < $1.rawValue }) {
            if let flag = component.installFlag { extra.append(flag) }
        }
        launch(extraArguments: extra, startMessage: "Preparing…")
    }

    private func expandedSelection(_ selection: Set<InstallComponent>) -> Set<InstallComponent> {
        var result = selection
        var changed = true
        while changed {
            changed = false
            for component in result {
                for dependency in component.requires where !result.contains(dependency) {
                    result.insert(dependency)
                    changed = true
                }
            }
        }
        return result
    }

    /// Only caches created inside Studio's managed root are eligible. User-wide
    /// uv/pip caches may serve unrelated projects and are never touched.
    var safeCacheSize: String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        return formatter.string(fromByteCount: safeCacheBytes)
    }

    func clearSafeCaches() {
        guard !isInstalling, !isRemoving,
              !AppPaths.fm.fileExists(atPath: AppPaths.installerLock.path) else {
            failure = "Wait for installation and active engine maintenance to finish before clearing caches."
            return
        }
        let targets = [
            AppPaths.support.appendingPathComponent("cache/uv", isDirectory: true),
            AppPaths.support.appendingPathComponent("cache/pip", isDirectory: true),
            AppPaths.support.appendingPathComponent("numba_cache", isDirectory: true),
        ]
        isRemoving = true
        currentMessage = "Clearing Studio-owned caches…"
        Task.detached(priority: .utility) {
            var errors: [String] = []
            for target in targets where FileManager.default.fileExists(atPath: target.path) {
                do { try FileManager.default.removeItem(at: target) }
                catch { errors.append("\(target.lastPathComponent): \(error.localizedDescription)") }
            }
            let removalErrors = errors
            await MainActor.run {
                self.isRemoving = false
                if removalErrors.isEmpty {
                    self.currentMessage = "Studio-owned caches cleared. Engines, checkpoints and results were kept."
                } else {
                    self.failure = "Some caches could not be cleared: " + removalErrors.joined(separator: "; ")
                }
                self.refreshSafeCacheSize()
            }
        }
    }

    /// Cache traversal can touch thousands of files. Keep it off SwiftUI's
    /// render path so opening Engines remains responsive even after large
    /// installs.
    func refreshSafeCacheSize() {
        Task.detached(priority: .utility) {
            let bytes = Self.safeCacheAllocatedBytes()
            await MainActor.run { self.safeCacheBytes = bytes }
        }
    }

    nonisolated private static func safeCacheAllocatedBytes() -> Int64 {
        let roots = [
            AppPaths.support.appendingPathComponent("cache/uv", isDirectory: true),
            AppPaths.support.appendingPathComponent("cache/pip", isDirectory: true),
            AppPaths.support.appendingPathComponent("numba_cache", isDirectory: true),
        ]
        let keys: Set<URLResourceKey> = [.isRegularFileKey, .fileAllocatedSizeKey,
                                         .totalFileAllocatedSizeKey]
        var total: Int64 = 0
        for root in roots {
            guard let enumerator = AppPaths.fm.enumerator(
                at: root, includingPropertiesForKeys: Array(keys), options: [.skipsHiddenFiles]
            ) else { continue }
            for case let item as URL in enumerator {
                let values = try? item.resourceValues(forKeys: keys)
                guard values?.isRegularFile == true else { continue }
                total += Int64(values?.totalFileAllocatedSize ?? values?.fileAllocatedSize ?? 0)
            }
        }
        return total
    }

    /// Ask the script what is already present, without installing anything.
    func detectComponents() {
        guard !isInstalling, !isRemoving, AppPaths.isPipelineStaged else { return }
        let runner = ProcessRunner()
        self.runner = runner
        runner.launch(
            executable: URL(fileURLWithPath: "/bin/bash"),
            arguments: [AppPaths.setupScript.path, "--detect"],
            environment: CommandBuilder.environment(),
            workingDir: AppPaths.pipeline,
            onLine: { [weak self] line in self?.handle(line, quiet: true) },
            onExit: { _ in }
        )
    }

    private func launch(extraArguments: [String], startMessage: String) {
        guard !isInstalling, !isRemoving else { return }
        isInstalling = true
        finished = false
        failure = nil
        progress = 0
        steps = []
        currentMessage = startMessage
        cancelRequested = false

        // Stage vendored scripts/examples into the managed pipeline dir.
        do { try AppPaths.stagePipelineAssets() }
        catch {
            fail(error.localizedDescription)
            return
        }

        let runner = ProcessRunner()
        self.runner = runner
        let log = AppPaths.installerLogs.appendingPathComponent(
            "setup-\(Int(Date().timeIntervalSince1970))-\(UUID().uuidString.prefix(8)).log"
        )
        latestLogURL = log
        var environment = CommandBuilder.environment()
        environment["IPROTEINSTUDIO_INSTALL_LOG"] = log.path
        environment["IPROTEINSTUDIO_SETUP_CAFFEINATED"] = "1"
        runner.launch(
            executable: URL(fileURLWithPath: "/bin/bash"),
            arguments: [AppPaths.setupScript.path] + extraArguments,
            environment: environment,
            workingDir: AppPaths.pipeline,
            logURL: log,
            preventsSleep: true,
            onLine: { [weak self] line in self?.handle(line) },
            onExit: { [weak self] code in self?.exit(code) }
        )
    }

    func cancel() {
        cancelRequested = true
        runner?.cancel()
        currentMessage = "Cancelling setup safely…"
    }

    // MARK: Output parsing

    private func handle(_ line: String, quiet: Bool = false) {
        let parts = line.split(separator: "|", maxSplits: 3,
                               omittingEmptySubsequences: false).map(String.init)
        if line.hasPrefix("NHSTEP|"), parts.count >= 4 {
            guard !quiet else { return }
            progress = (Double(parts[2]) ?? 0) / 100.0
            currentMessage = parts[3]
            if steps.last?.key == parts[1] {
                steps[steps.count - 1].message = parts[3]
            } else {
                steps.append(Step(key: parts[1], message: parts[3]))
            }
        } else if line.hasPrefix("NHSTATE|"), parts.count >= 3 {
            guard let component = InstallComponent(rawValue: parts[1]),
                  let availability = ComponentState.Availability(rawValue: parts[2]) else { return }
            components[component] = ComponentState(
                availability: availability,
                detail: parts.count >= 4 ? parts[3] : ""
            )
        } else if line.hasPrefix("NHDONE|") {
            guard !quiet else { return }
            progress = 1.0
            currentMessage = "Setup complete."
        } else if line.hasPrefix("NHFAIL|") {
            failure = line.replacingOccurrences(of: "NHFAIL|", with: "")
        }
    }

    private func exit(_ code: Int32) {
        isInstalling = false
        installed = AppPaths.isPipelineInstalled
        if cancelRequested {
            cancelRequested = false
            currentMessage = "Setup cancelled. Partial downloads were kept so retry can resume."
            detectComponents()
            return
        }
        if code == 0 && installed {
            finished = true
            progress = 1.0
            currentMessage = "iProteinStudio is ready."
        } else {
            fail(failure ?? "Setup exited with code \(code). See the log for details.")
        }
    }

    private func fail(_ msg: String) {
        isInstalling = false
        failure = msg
        currentMessage = "Setup failed."
    }

    /// Keep a safety reserve for the operating system and temporary installer
    /// files. This is intentionally conservative: failing before a download is
    /// much kinder than producing a half-created Python environment.
    private func preflightFreeSpace(requiredBytes: Int64) -> Bool {
        guard requiredBytes > 0 else { return true }
        let reserve: Int64 = 3 * 1_073_741_824
        let values = try? AppPaths.support.resourceValues(
            forKeys: [.volumeAvailableCapacityForImportantUsageKey]
        )
        guard let available = values?.volumeAvailableCapacityForImportantUsage else {
            failure = "Studio could not determine available disk space. Setup was not started."
            currentMessage = "Could not verify free disk space."
            return false
        }
        guard available >= requiredBytes + reserve else {
            let formatter = ByteCountFormatter()
            formatter.countStyle = .file
            failure = "This setup needs approximately \(formatter.string(fromByteCount: requiredBytes)) plus a 3 GB safety reserve, but only \(formatter.string(fromByteCount: available)) is available. Remove files or choose fewer engines."
            currentMessage = "Not enough free disk space."
            return false
        }
        return true
    }

    /// Credit bytes already retained by an interrupted install so a retry is
    /// not refused as though it must download and unpack the whole component a
    /// second time. Symlinked external installations consume no managed space.
    private func managedAllocatedBytes(for component: InstallComponent) -> Int64 {
        let keys: Set<URLResourceKey> = [.isRegularFileKey, .fileAllocatedSizeKey,
                                         .totalFileAllocatedSizeKey]
        var total: Int64 = 0
        for root in removalTargets(for: component) {
            if (try? AppPaths.fm.destinationOfSymbolicLink(atPath: root.path)) != nil { continue }
            guard AppPaths.fm.fileExists(atPath: root.path) else { continue }
            var isDirectory: ObjCBool = false
            AppPaths.fm.fileExists(atPath: root.path, isDirectory: &isDirectory)
            if !isDirectory.boolValue {
                let values = try? root.resourceValues(forKeys: keys)
                total += Int64(values?.totalFileAllocatedSize ?? values?.fileAllocatedSize ?? 0)
                continue
            }
            guard let enumerator = AppPaths.fm.enumerator(
                at: root, includingPropertiesForKeys: Array(keys),
                options: [.skipsHiddenFiles]
            ) else { continue }
            for case let item as URL in enumerator {
                let values = try? item.resourceValues(forKeys: keys)
                guard values?.isRegularFile == true else { continue }
                total += Int64(values?.totalFileAllocatedSize ?? values?.fileAllocatedSize ?? 0)
            }
        }
        return total
    }
}
