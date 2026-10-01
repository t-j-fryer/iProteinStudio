import Foundation
import CryptoKit

@main struct TargetStructureSnapshotHarness {
    static func main() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? fm.removeItem(at: root) }
        let cache = root.appendingPathComponent("target_predictions")
        let prediction = cache.appendingPathComponent("key/prediction-id")
        let source = prediction.appendingPathComponent("results/target/model_0.cif")
        try fm.createDirectory(at: source.deletingLastPathComponent(), withIntermediateDirectories: true)
        let coordinates = Data("saved target coordinates".utf8)
        try coordinates.write(to: source)
        let config = Data("{\"predictors\":[\"esmfold2-fast-mlx\"],\"seed\":42}".utf8)
        try config.write(to: prediction.appendingPathComponent("prediction_config.json"))
        for workflow in ["rfd3", "hunter"] {
            let target = root.appendingPathComponent("\(workflow)/inputs/target.cif")
            try TargetStructureSnapshot.copy(source: source, to: target, predictionCache: cache)
            let saved = try Data(contentsOf: target)
            precondition(saved == coordinates)
            let folder = target.deletingLastPathComponent()
            let savedConfig = try Data(contentsOf: folder.appendingPathComponent("target_prediction_config.json"))
            precondition(savedConfig == config)
            let receipt = try JSONSerialization.jsonObject(with: Data(contentsOf: folder.appendingPathComponent("target_prediction.json"))) as! [String: Any]
            precondition(receipt["structure"] as? String == "target.cif")
            precondition(receipt["structure_sha256"] as? String == SHA256.hash(data: coordinates).map { String(format: "%02x", $0) }.joined())
        }
        let external = root.appendingPathComponent("target_predictions-other/target.pdb")
        try fm.createDirectory(at: external.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data("external coordinates".utf8).write(to: external)
        let destination = root.appendingPathComponent("external/target.pdb")
        try TargetStructureSnapshot.copy(source: external, to: destination, predictionCache: cache)
        precondition(!fm.fileExists(atPath: destination.deletingLastPathComponent().appendingPathComponent("target_prediction.json").path))
        try Data("broken json".utf8).write(to: prediction.appendingPathComponent("prediction_config.json"))
        var rejected = false
        do { try TargetStructureSnapshot.copy(source: source, to: root.appendingPathComponent("bad/target.cif"), predictionCache: cache) }
        catch { rejected = true }
        precondition(rejected)
        try fm.removeItem(at: cache)
        precondition(fm.fileExists(atPath: root.appendingPathComponent("hunter/inputs/target.cif").path))
        print("PASS predicted target snapshots, both workflow layouts, recipe hashes, cache independence and malformed metadata rejection")
    }
}
