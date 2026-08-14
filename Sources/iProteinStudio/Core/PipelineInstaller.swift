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
    struct Step: Identifiable { let id = UUID(); let message: String }

    /// What `setup_pipeline.sh` reported about one backend.
    struct ComponentState: Equatable {
        enum Availability: String { case ok, missing, skipped }
        var availability: Availability
        /// Human-readable qualifier, e.g. "environment ready — place af3.bin at …".
        var detail: String

        var isUsable: Bool { availability == .ok }
    }

    @Published var isInstalling = false
    @Published var progress: Double = 0          // 0...1
    @Published var currentMessage = "Ready to set up iProteinStudio."
    @Published var steps: [Step] = []
    @Published var finished = false
    @Published var failure: String?
    @Published var installed = AppPaths.isPipelineInstalled
    @Published var components: [InstallComponent: ComponentState] = [:]
    /// The practical default installation: the folding engine, nanobody
    /// designer, independent checker, and unconditional MPNN family described
    /// by onboarding. Heavy alternative predictors remain opt-in.
    @Published var optionalSelection: Set<InstallComponent> = [.boltz, .antifold, .intellifold]
    /// An existing NanoHunter checkout found on this machine, if any.
    @Published var detectedNanoHunter: URL?
    @Published var detectedRFD3: URL?

    private var runner: ProcessRunner?

    init() {
        detectExistingCheckouts()
        repairRelocatedVenvsIfNeeded()
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

    /// AlphaFold 3's environment is present but its weights are not — the only
    /// component that cannot finish installing itself.
    var needsAlphaFoldWeights: Bool {
        guard let state = components[.alphafold3] else { return false }
        return state.availability == .missing && state.detail.contains("af3.bin")
    }

    func isUsable(_ component: InstallComponent) -> Bool {
        components[component]?.isUsable ?? false
    }

    func detail(_ component: InstallComponent) -> String {
        components[component]?.detail ?? ""
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
        var extra: [String] = []
        for component in optionalSelection.sorted(by: { $0.rawValue < $1.rawValue }) {
            if let flag = component.installFlag { extra.append(flag) }
        }
        launch(extraArguments: extra, startMessage: "Preparing…")
    }

    /// Ask the script what is already present, without installing anything.
    func detectComponents() {
        guard !isInstalling, AppPaths.isPipelineStaged else { return }
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
        guard !isInstalling else { return }
        isInstalling = true
        finished = false
        failure = nil
        progress = 0
        steps = []
        currentMessage = startMessage

        // Stage vendored scripts/examples into the managed pipeline dir.
        do { try AppPaths.stagePipelineAssets() }
        catch {
            fail(error.localizedDescription)
            return
        }

        let runner = ProcessRunner()
        self.runner = runner
        runner.launch(
            executable: URL(fileURLWithPath: "/bin/bash"),
            arguments: [AppPaths.setupScript.path] + extraArguments,
            environment: CommandBuilder.environment(),
            workingDir: AppPaths.pipeline,
            onLine: { [weak self] line in self?.handle(line) },
            onExit: { [weak self] code in self?.exit(code) }
        )
    }

    func cancel() {
        runner?.cancel()
        isInstalling = false
        currentMessage = "Setup cancelled."
    }

    /// Copy user-supplied AlphaFold 3 weights into place.
    ///
    /// Copied rather than referenced: the file is often chosen from a Downloads
    /// folder that later gets cleared, and a campaign failing three days in
    /// because the weights moved is a bad way to find out.
    func installAlphaFoldWeights(from source: URL) -> String {
        let modelDir = AppPaths.support.appendingPathComponent("models/alphafold3", isDirectory: true)
        let destination = modelDir.appendingPathComponent("af3.bin")
        do {
            try AppPaths.fm.createDirectory(at: modelDir, withIntermediateDirectories: true)
            let attributes = try AppPaths.fm.attributesOfItem(atPath: source.path)
            let size = (attributes[.size] as? Int64) ?? 0
            // The real file is around a gigabyte; anything tiny is the wrong file
            // and would fail much later, inside the model.
            guard size > 100_000_000 else {
                return "That file is only \(ByteCountFormatter.string(fromByteCount: size, countStyle: .file)). The AlphaFold 3 parameter file is around a gigabyte — this looks like the wrong file."
            }
            if AppPaths.fm.fileExists(atPath: destination.path) {
                try AppPaths.fm.removeItem(at: destination)
            }
            try AppPaths.fm.copyItem(at: source, to: destination)
            detectComponents()
            return "Weights installed. AlphaFold 3 is ready."
        } catch {
            return "Could not install the weights: \(error.localizedDescription)"
        }
    }

    // MARK: Output parsing

    private func handle(_ line: String, quiet: Bool = false) {
        let parts = line.components(separatedBy: "|")
        if line.hasPrefix("NHSTEP|"), parts.count >= 4 {
            guard !quiet else { return }
            progress = (Double(parts[2]) ?? 0) / 100.0
            currentMessage = parts[3]
            steps.append(Step(message: parts[3]))
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
}
