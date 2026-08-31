import Foundation
import Darwin

/// Thin wrapper around `Process` that streams stdout+stderr lines to a callback
/// and reports termination. Cancellable.
final class ProcessRunner {
    private var process: Process?
    private let queue = DispatchQueue(label: "nhs.process")
    private let outputLock = NSLock()

    /// Launch `executable` with `arguments`. `onLine` is called on the main
    /// queue for each line; `onExit` with the exit code when finished.
    func launch(executable: URL,
                arguments: [String],
                environment: [String: String],
                workingDir: URL? = nil,
                logURL: URL? = nil,
                preventsSleep: Bool = false,
                onLine: @escaping (String) -> Void,
                onExit: @escaping (Int32) -> Void) {
        let proc = Process()
        if preventsSleep {
            proc.executableURL = URL(fileURLWithPath: "/usr/bin/caffeinate")
            proc.arguments = ["-dimsu", executable.path] + arguments
        } else {
            proc.executableURL = executable
            proc.arguments = arguments
        }
        proc.environment = environment
        if let wd = workingDir { proc.currentDirectoryURL = wd }

        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = pipe

        let handle = pipe.fileHandleForReading
        var buffer = Data()
        var logHandle: FileHandle?
        if let logURL {
            try? FileManager.default.createDirectory(
                at: logURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            FileManager.default.createFile(atPath: logURL.path, contents: nil)
            logHandle = try? FileHandle(forWritingTo: logURL)
        }

        func consume(_ chunk: Data) {
            guard !chunk.isEmpty else { return }
            self.outputLock.lock()
            logHandle?.write(chunk)
            buffer.append(chunk)
            var lines: [String] = []
            while let newline = buffer.firstIndex(of: 0x0A) {
                let lineData = buffer.subdata(in: buffer.startIndex..<newline)
                buffer.removeSubrange(buffer.startIndex...newline)
                if let line = String(data: lineData, encoding: .utf8) { lines.append(line) }
            }
            self.outputLock.unlock()
            for line in lines { DispatchQueue.main.async { onLine(line) } }
        }

        handle.readabilityHandler = { h in
            consume(h.availableData)
        }

        proc.terminationHandler = { p in
            handle.readabilityHandler = nil
            consume(handle.readDataToEndOfFile())
            self.outputLock.lock()
            let tail = buffer
            buffer.removeAll()
            try? logHandle?.synchronize()
            try? logHandle?.close()
            self.outputLock.unlock()
            if !tail.isEmpty, let line = String(data: tail, encoding: .utf8), !line.isEmpty {
                DispatchQueue.main.async { onLine(line) }
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
            guard let process = self?.process, process.isRunning else { return }
            let originalDescendants = Self.descendantPIDs(of: process.processIdentifier)
            for pid in originalDescendants.reversed() { Darwin.kill(pid, SIGTERM) }
            process.terminate()
            self?.queue.asyncAfter(deadline: .now() + 3) {
                // The immediate caffeinate/shell parent often exits before a
                // compiler or downloader that ignored SIGTERM. Retain the
                // original tree and kill surviving members even after the
                // parent has gone and pgrep can no longer discover them.
                var remaining = Set(originalDescendants)
                if process.isRunning {
                    remaining.formUnion(Self.descendantPIDs(of: process.processIdentifier))
                }
                for pid in remaining.reversed() where Darwin.kill(pid, 0) == 0 {
                    Darwin.kill(pid, SIGKILL)
                }
                if process.isRunning { Darwin.kill(process.processIdentifier, SIGKILL) }
            }
        }
    }

    /// Return every descendant rather than only the immediate shell. Installers
    /// spawn pip, git, Python and downloader children; terminating just the shell
    /// leaves those processes writing into a supposedly cancelled environment.
    private static func descendantPIDs(of parent: pid_t) -> [pid_t] {
        let probe = Process()
        let output = Pipe()
        probe.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
        probe.arguments = ["-P", String(parent)]
        probe.standardOutput = output
        probe.standardError = FileHandle.nullDevice
        guard (try? probe.run()) != nil else { return [] }
        probe.waitUntilExit()
        let data = output.fileHandleForReading.readDataToEndOfFile()
        let direct = String(data: data, encoding: .utf8)?
            .split(whereSeparator: \.isWhitespace)
            .compactMap { pid_t($0) } ?? []
        return direct + direct.flatMap { descendantPIDs(of: $0) }
    }

    var isRunning: Bool { process?.isRunning ?? false }
}
