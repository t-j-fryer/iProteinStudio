import Foundation
import StudioCore

enum IntelliFoldModel: String, Codable, Hashable { case v2flash = "v2-flash", v2 }

enum AppPaths {
    static let fm = FileManager.default
    static let support = fm.temporaryDirectory.appendingPathComponent("studio-apple-tools-\(UUID().uuidString)")
    static let pipeline = support.appendingPathComponent("pipeline")
    static let rfd3Root = support.appendingPathComponent("rfd3")
    static let setupScript = pipeline.appendingPathComponent("setup_pipeline.sh")
    static let installerLock = support.appendingPathComponent(".install.lock")
    static let installerLogs = support.appendingPathComponent("logs")
    static var isPipelineInstalled = false
    static let isPipelineStaged = true
    static var stages = 0
    static func stagePipelineAssets(leaseHeld: Bool) throws {
        precondition(leaseHeld)
        stages += 1
    }
}
enum CommandBuilder {
    static func environment() -> [String: String] { [:] }
}

/// Exercise the real controller; intercept only external process execution.
@MainActor final class ProcessRunner {
    struct Call {
        var executable: URL
        var arguments: [String]
        var line: (String) -> Void
        var exit: (Int32) -> Void
    }
    static var calls: [Call] = []
    func launch(executable: URL, arguments: [String], environment: [String: String],
                workingDir: URL? = nil, logURL: URL? = nil, preventsSleep: Bool = false,
                onLine: @escaping (String) -> Void, onExit: @escaping (Int32) -> Void) {
        Self.calls.append(.init(executable: executable, arguments: arguments, line: onLine, exit: onExit))
    }
    func cancel() {}
}

@main struct AppleBuildToolsInstallerHarness {
    @MainActor static func main() throws {
        try AppPaths.fm.createDirectory(at: AppPaths.support, withIntermediateDirectories: true)
        defer { try? AppPaths.fm.removeItem(at: AppPaths.support) }
        let installer = PipelineInstaller()
        for component in InstallComponent.allCases {
            installer.components[component] = .init(availability: .ok, detail: "fixture")
        }
        installer.optionalSelection = [.boltz]
        installer.install()
        precondition(installer.isInstalling)
        let original = ProcessRunner.calls.last!
        precondition(original.arguments.contains("--with-boltz"))
        original.line("NHREQUIRES|apple-build-tools")
        original.line("NHFAIL|Apple tools need installation")
        original.exit(1)
        precondition(installer.needsAppleBuildTools && !installer.isInstalling)
        // Setup must release its lease while Apple's independent installer runs.
        do { let lease = try ExecutionLease(directory: AppPaths.support.appendingPathComponent("agent")); withExtendedLifetime(lease) {} }

        installer.requestAppleBuildTools()
        let apple = ProcessRunner.calls.last!
        precondition(apple.executable.path == "/usr/bin/xcode-select")
        precondition(apple.arguments == ["--install"])
        precondition(installer.isRequestingAppleBuildTools)
        let before = ProcessRunner.calls.count
        installer.requestAppleBuildTools()
        installer.retryAfterAppleBuildTools()
        precondition(ProcessRunner.calls.count == before)
        apple.exit(0)
        precondition(!installer.isRequestingAppleBuildTools && installer.needsAppleBuildTools)
        precondition(!installer.finished && !installer.isInstalling)

        // Changing today's form must not change the previously reviewed retry.
        installer.optionalSelection = [.nesso]
        installer.retryAfterAppleBuildTools()
        precondition(ProcessRunner.calls.last!.arguments == original.arguments)
        precondition(AppPaths.stages == 2 && installer.isInstalling)
        ProcessRunner.calls.last!.line("NHREQUIRES|apple-build-tools")
        ProcessRunner.calls.last!.exit(1)
        installer.requestAppleBuildTools()
        ProcessRunner.calls.last!.exit(1)
        precondition(installer.needsAppleBuildTools && !installer.isRequestingAppleBuildTools)
        precondition(installer.appleBuildToolsMessage!.contains("Software Update"))
        installer.retryAfterAppleBuildTools()
        AppPaths.isPipelineInstalled = true
        ProcessRunner.calls.last!.line("NHDONE|ok")
        ProcessRunner.calls.last!.exit(0)
        precondition(installer.finished && !installer.needsAppleBuildTools)
        installer.optionalSelection = [.boltz, .abmpnn]
        installer.install()
        let partial = ProcessRunner.calls.last!
        partial.line("NHSTATE|mpnn|ok|Core ready")
        partial.line("NHCOMPONENTFAIL|abmpnn|Both approved hosts unavailable")
        partial.line("NHCOMPONENTFAIL|abmpnn|Generic incomplete message")
        partial.line("NHSTATE|boltz|ok|Boltz ready")
        partial.line("NHSTATE|intellifold|skipped|not requested")
        precondition(installer.isUsable(.intellifold))
        partial.line("NHDONE|partial|abmpnn")
        partial.exit(2)
        precondition(installer.completedWithIssues && installer.installed && !installer.finished)
        precondition(installer.failure == nil && installer.isUsable(.boltz) && installer.isUsable(.mpnn))
        precondition(!installer.isUsable(.abmpnn))
        precondition(installer.failedComponents[.abmpnn] == "Both approved hosts unavailable")
        installer.retryIncompleteComponents()
        let retry = ProcessRunner.calls.last!
        precondition(retry.arguments.suffix(2) == ["--retry-components", "abmpnn"])
        precondition(!installer.completedWithIssues && installer.failedComponents.isEmpty)
        retry.line("NHSTATE|abmpnn|ok|Verified")
        retry.line("NHDONE|ok")
        retry.exit(0)
        precondition(installer.finished && installer.isUsable(.abmpnn))
        let external = AppPaths.support.deletingLastPathComponent().appendingPathComponent("external-abmpnn-\(UUID().uuidString)")
        try AppPaths.fm.createDirectory(at: external.appendingPathComponent("model_params"), withIntermediateDirectories: true)
        defer { try? AppPaths.fm.removeItem(at: external) }
        try Data("fixture".utf8).write(to: external.appendingPathComponent("model_params/abmpnn.pt"))
        try AppPaths.fm.createDirectory(at: AppPaths.support.appendingPathComponent("src"), withIntermediateDirectories: true)
        try AppPaths.fm.createSymbolicLink(at: AppPaths.support.appendingPathComponent("src/LigandMPNN"), withDestinationURL: external)
        precondition(!installer.hasManagedFiles(.abmpnn)) // never delete through a shared source directory
        print("PASS linked original AbMPNN weights are excluded from removal")
        print("PASS partial installation reporting, unavailable failed engine, narrow retry and recovery")
        print("PASS native Apple tools prerequisite, request/failure/retry, selection retention and lease release")
    }
}
