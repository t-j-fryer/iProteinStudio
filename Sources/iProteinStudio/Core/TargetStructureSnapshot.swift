import Foundation
import CryptoKit

/// Own a target before queueing generation. Keep Target Prep's exact input
/// settings beside the copied structure; external structures need no invented
/// prediction provenance. No model weights or prediction caches are copied.
enum TargetStructureSnapshot {
    static func copy(source: URL, to destination: URL, predictionCache: URL) throws {
        let fm = FileManager.default
        try fm.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
        try fm.copyItem(at: source, to: destination)
        let cache = predictionCache.resolvingSymlinksInPath().standardizedFileURL
        let resolved = source.resolvingSymlinksInPath().standardizedFileURL
        guard resolved.path.hasPrefix(cache.path + "/") else { return }
        var directory = resolved.deletingLastPathComponent()
        while directory.path.hasPrefix(cache.path + "/") {
            let config = directory.appendingPathComponent("prediction_config.json")
            if fm.fileExists(atPath: config.path) {
                let data = try Data(contentsOf: config)
                // Fail rather than attach unreadable or malformed provenance.
                _ = try JSONSerialization.jsonObject(with: data)
                let savedConfig = destination.deletingLastPathComponent().appendingPathComponent("target_prediction_config.json")
                try data.write(to: savedConfig, options: .atomic)
                let structure = try Data(contentsOf: destination)
                let receipt: [String: Any] = [
                    "schema_version": 1, "source": "studio_target_prediction",
                    "structure": destination.lastPathComponent,
                    "structure_sha256": SHA256.hash(data: structure).map { String(format: "%02x", $0) }.joined(),
                    "prediction_config": savedConfig.lastPathComponent,
                    "prediction_config_sha256": SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
                ]
                try JSONSerialization.data(withJSONObject: receipt, options: [.prettyPrinted, .sortedKeys])
                    .write(to: destination.deletingLastPathComponent().appendingPathComponent("target_prediction.json"), options: .atomic)
                return
            }
            directory.deleteLastPathComponent()
        }
        // Older imported library entries may predate saved prediction configs.
        // Their structure is still owned by this run, with no fabricated recipe.
    }
}
