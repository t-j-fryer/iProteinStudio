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
        print("PASS native Apple tools prerequisite, request/failure/retry, selection retention and lease release")
    }
}
