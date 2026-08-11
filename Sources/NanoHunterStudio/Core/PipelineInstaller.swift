import Foundation
import Combine

/// Drives first-run setup: stages vendored assets, then runs setup_pipeline.sh,
/// parsing NHSTEP/NHDONE/NHFAIL markers into friendly progress.
@MainActor
final class PipelineInstaller: ObservableObject {
    struct Step: Identifiable { let id = UUID(); let message: String }

    @Published var isInstalling = false
    @Published var progress: Double = 0          // 0...1
    @Published var currentMessage = "Ready to set up NanoHunter."
    @Published var steps: [Step] = []
    @Published var finished = false
    @Published var failure: String?
    @Published var installed = AppPaths.isPipelineInstalled

    private var runner: ProcessRunner?

    func refreshInstalledState() { installed = AppPaths.isPipelineInstalled }

    func install() {
        guard !isInstalling else { return }
        isInstalling = true
        finished = false
        failure = nil
        progress = 0
        steps = []
        currentMessage = "Preparing…"

        // Stage vendored scripts/examples into the managed pipeline dir.
        do { try AppPaths.stagePipelineAssets() }
        catch {
            fail(error.localizedDescription)
            return
        }

        let runner = ProcessRunner()
        self.runner = runner
        let env = CommandBuilder.environment()
        runner.launch(
            executable: URL(fileURLWithPath: "/bin/bash"),
            arguments: [AppPaths.setupScript.path],
            environment: env,
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

    private func handle(_ line: String) {
        if line.hasPrefix("NHSTEP|") {
            let parts = line.components(separatedBy: "|")
            if parts.count >= 4 {
                progress = (Double(parts[2]) ?? 0) / 100.0
                currentMessage = parts[3]
                steps.append(Step(message: parts[3]))
            }
        } else if line.hasPrefix("NHDONE|") {
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
            currentMessage = "NanoHunter is ready."
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
