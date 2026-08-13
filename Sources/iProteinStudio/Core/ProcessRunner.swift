import Foundation

/// Thin wrapper around `Process` that streams stdout+stderr lines to a callback
/// and reports termination. Cancellable.
final class ProcessRunner {
    private var process: Process?
    private let queue = DispatchQueue(label: "nhs.process")

    /// Launch `executable` with `arguments`. `onLine` is called on the main
    /// queue for each line; `onExit` with the exit code when finished.
    func launch(executable: URL,
                arguments: [String],
                environment: [String: String],
                workingDir: URL? = nil,
                onLine: @escaping (String) -> Void,
                onExit: @escaping (Int32) -> Void) {
        let proc = Process()
        proc.executableURL = executable
        proc.arguments = arguments
        proc.environment = environment
        if let wd = workingDir { proc.currentDirectoryURL = wd }

        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = pipe

        let handle = pipe.fileHandleForReading
        var buffer = Data()
        handle.readabilityHandler = { h in
            let chunk = h.availableData
            guard !chunk.isEmpty else { return }
            buffer.append(chunk)
            while let nl = buffer.firstIndex(of: 0x0A) {
                let lineData = buffer.subdata(in: buffer.startIndex..<nl)
                buffer.removeSubrange(buffer.startIndex...nl)
                if let line = String(data: lineData, encoding: .utf8) {
                    DispatchQueue.main.async { onLine(line) }
                }
            }
        }

        proc.terminationHandler = { p in
            handle.readabilityHandler = nil
            if !buffer.isEmpty, let tail = String(data: buffer, encoding: .utf8), !tail.isEmpty {
                DispatchQueue.main.async { onLine(tail) }
            }
            DispatchQueue.main.async { onExit(p.terminationStatus) }
        }

        self.process = proc
        queue.async {
            do { try proc.run() }
            catch {
                DispatchQueue.main.async {
                    onLine("Failed to launch: \(error.localizedDescription)")
                    onExit(127)
                }
            }
        }
    }

    func cancel() {
        queue.async { [weak self] in
            self?.process?.terminate()
        }
    }

    var isRunning: Bool { process?.isRunning ?? false }
}
