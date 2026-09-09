import Foundation

/// Workspace routing only. Engine availability still gates each workflow.
enum InstalledRuntime {
    static func hasCompletedComponent(at support: URL) -> Bool {
        let fm = FileManager.default
        let venvs = support.appendingPathComponent("venvs", isDirectory: true)
        // LigandMPNN is the unconditional core install. Boltz is selected by
        // default, but remains optional so a user can intentionally install a
        // different predictor without setup being reported as a failure.
        let mpnn = venvs.appendingPathComponent("NanoHunter_ligandmpnn/bin/python")
        let source = support.appendingPathComponent("src/LigandMPNN", isDirectory: true)
        let required = [
            source.appendingPathComponent("run.py"),
            source.appendingPathComponent("model_params/proteinmpnn_v_48_020.pt"),
            source.appendingPathComponent("model_params/solublempnn_v_48_020.pt"),
            source.appendingPathComponent("model_params/ligandmpnn_v_32_010_25.pt"),
        ]
        if fm.isExecutableFile(atPath: mpnn.path)
            && required.allSatisfy({ fm.fileExists(atPath: $0.path) }) { return true }
        // Routing into the workspace is independent of core sequence design.
        // A completed predictor can still serve Predict after a core download
        // failed. Per-workflow availability checks continue to gate execution.
        for key in ["boltz", "intellifold", "openfold3", "protenix_v2", "protenix_mini", "rfd3"] {
            let receipt = support.appendingPathComponent("receipts/\(key).json")
            guard let data = try? Data(contentsOf: receipt),
                  let record = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
                  record["component"] as? String == key,
                  record["schema_version"] as? Int == 1,
                  let python = record["python"] as? [String: Any],
                  let executable = python["executable"] as? String,
                  fm.isExecutableFile(atPath: executable),
                  let artifacts = record["artifacts"] as? [String: String], !artifacts.isEmpty,
                  artifacts.keys.allSatisfy({ fm.fileExists(atPath: $0) }) else { continue }
            return true
        }
        return false
    }

}
