import Foundation

@main struct InstalledRuntimeHarness {
    static func main() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent("studio-install-readiness-\(UUID().uuidString)")
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: root) }
        func file(_ relative: String, executable: Bool = false) throws -> URL {
            let path = root.appendingPathComponent(relative)
            try fm.createDirectory(at: path.deletingLastPathComponent(), withIntermediateDirectories: true)
            try Data("fixture".utf8).write(to: path)
            if executable { try fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: path.path) }
            return path
        }
        precondition(!InstalledRuntime.hasCompletedComponent(at: root))
        let python = try file("venvs/boltz/bin/python", executable: true)
        let checkpoint = try file("models/boltz.ckpt")
        let receipt = try file("receipts/boltz.json")
        let payload: [String: Any] = ["schema_version": 1, "component": "boltz", "python": ["executable": python.path], "artifacts": [checkpoint.path: "fixture-hash"]]
        precondition(!InstalledRuntime.hasCompletedComponent(at: root)) // invalid receipt
        try JSONSerialization.data(withJSONObject: payload).write(to: receipt)
        precondition(InstalledRuntime.hasCompletedComponent(at: root)) // Predict without MPNN
        try fm.removeItem(at: checkpoint)
        precondition(!InstalledRuntime.hasCompletedComponent(at: root))
        _ = try file("venvs/NanoHunter_ligandmpnn/bin/python", executable: true)
        for name in ["run.py", "model_params/proteinmpnn_v_48_020.pt", "model_params/solublempnn_v_48_020.pt", "model_params/ligandmpnn_v_32_010_25.pt"] {
            _ = try file("src/LigandMPNN/" + name)
        }
        precondition(InstalledRuntime.hasCompletedComponent(at: root)) // AbMPNN is independent
        print("PASS workspace access after partial setup, corrupt receipt rejection, missing artifact and core without AbMPNN")
    }
}
