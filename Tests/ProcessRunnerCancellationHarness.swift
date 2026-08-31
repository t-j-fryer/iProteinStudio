import Foundation
import Darwin

@main
struct ProcessRunnerCancellationHarness {
    static func main() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("iproteinstudio-process-cancel-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let leaf = root.appendingPathComponent("leaf.sh")
        let child = root.appendingPathComponent("child.sh")
        let parent = root.appendingPathComponent("parent.sh")
        try """
        #!/bin/bash
        trap '' TERM
        echo "LEAF:$$"
        while true; do /bin/sleep 1; done
        """.write(to: leaf, atomically: true, encoding: .utf8)
        try """
        #!/bin/bash
        trap '' TERM
        "\(leaf.path)" &
        wait
        """.write(to: child, atomically: true, encoding: .utf8)
        try """
        #!/bin/bash
        trap 'exit 0' TERM
        "\(child.path)" &
        wait
        """.write(to: parent, atomically: true, encoding: .utf8)
        for script in [leaf, child, parent] {
            try FileManager.default.setAttributes([.posixPermissions: 0o755],
                                                  ofItemAtPath: script.path)
        }

        let runner = ProcessRunner()
        var leafPID: pid_t?
        var exited = false
        runner.launch(
            executable: parent,
            arguments: [],
            environment: ProcessInfo.processInfo.environment,
            onLine: { line in
                if line.hasPrefix("LEAF:"), let value = pid_t(line.dropFirst(5)) {
                    leafPID = value
                    runner.cancel()
                }
            },
            onExit: { _ in exited = true }
        )

        let deadline = Date().addingTimeInterval(10)
        while Date() < deadline && (!exited || leafPID.map { Darwin.kill($0, 0) == 0 } != false) {
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        }
        guard exited else {
            fputs("FAIL: parent process did not exit after cancellation\n", stderr)
            exit(1)
        }
        guard let leafPID, Darwin.kill(leafPID, 0) != 0 else {
            fputs("FAIL: SIGTERM-resistant grandchild survived cancellation\n", stderr)
            exit(1)
        }
        print("PASS process runner cancellation")
    }
}
