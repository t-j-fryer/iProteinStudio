import Foundation
import Combine

/// Uses the same CPU-only Python contract as saved plans and worker dispatch.
@MainActor
final class MemoryAdmissionPreview: ObservableObject {
    struct Result: Decodable {
        let status: String
        let message: String
    }
    @Published private(set) var result: Result?
    @Published private(set) var checking = false
    private var generation = UUID()

    func check(_ data: Data) async {
        let current = UUID()
        generation = current
        result = nil
        checking = true
        let python = ControlPython.executable(root: AppPaths.support)
        let script = AppPaths.bundledPipeline?.appendingPathComponent("scripts/memory_admission.py")
        let response = await Task.detached(priority: .utility) { () -> Result in
            let temporary = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
            defer { try? FileManager.default.removeItem(at: temporary) }
            do {
                guard let script else { throw NHError.message("Memory-check resources are missing. Reinstall Studio.") }
                try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: true)
                let config = temporary.appendingPathComponent("prediction.json")
                try data.write(to: config)
                let process = Process()
                process.executableURL = python
                process.arguments = [script.path, "--config", config.path]
                let output = Pipe()
                process.standardOutput = output
                process.standardError = FileHandle.nullDevice
                process.environment = ProcessInfo.processInfo.environment.merging(["PYTHONDONTWRITEBYTECODE": "1"]) { _, new in new }
                try process.run()
                let bytes = output.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                return try JSONDecoder().decode(Result.self, from: bytes)
            } catch {
                return Result(status: "blocked", message: "Memory could not be checked: \(error.localizedDescription)")
            }
        }.value
        guard generation == current, !Task.isCancelled else { return }
        result = response
        checking = false
    }
}
