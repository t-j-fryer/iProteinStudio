import Foundation
import CryptoKit

/// A geometry receipt applies only to its own unchanged structure and result.
enum LigandGeometryResult {
    static func read(_ structure: URL) -> [String: Any]? {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: structure.path + ".ligand_geometry.json")),
              let saved = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let result = saved["result"] as? [String: Any],
              let canonical = saved["result_json"] as? String,
              let canonicalData = canonical.data(using: .utf8),
              let checksum = saved["result_sha256"] as? String,
              hash(canonicalData) == checksum,
              let checked = try? JSONSerialization.jsonObject(with: canonicalData) as? [String: Any],
              NSDictionary(dictionary: checked).isEqual(to: result),
              let expected = result["structure_sha256"] as? String,
              let coordinates = try? Data(contentsOf: structure), hash(coordinates) == expected else { return nil }
        return result
    }
    static func required(root: URL) -> Bool {
        for (name, key) in [("rfd4_config.json", "settings"), ("nise_config.json", "request"), ("studio_run.json", "request"), ("config/campaign.json", ""), ("config.json", "")] {
            guard let data = try? Data(contentsOf: root.appendingPathComponent(name)),
                  let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
            let settings = key.isEmpty ? value : value[key] as? [String: Any] ?? [:]
            if settings["ligand_geometry"] is [String: Any] { return true }
        }
        return false
    }
    static func apply(_ item: StudioResultItem, required: Bool = false) -> StudioResultItem {
        if !required || item.artifactRole == .binderAlone { return item }
        guard let result = read(item.structureURL), let passed = result["passed"] as? Bool else {
            if required || FileManager.default.fileExists(atPath: item.structureURL.path + ".ligand_geometry.json") {
                var copy = item; copy.isHit = false
                copy.failedFilters += ["Ligand geometry unavailable or receipt does not match this structure."]
                return copy
            }
            return item
        }
        var copy = item
        copy.isHit = passed && item.isHit != false && item.failedFilters.isEmpty
        copy.failedFilters += (result["failures"] as? [String] ?? []).filter { !copy.failedFilters.contains($0) && !copy.failedFilters.contains("Ligand geometry: " + $0) }.map { "Ligand geometry: " + $0 }
        return copy
    }
    static func spatialPayload(_ structure: URL, result: [String: Any]) -> String? {
        guard result["cone"] is [String: Any], let data = try? Data(contentsOf: structure) else { return nil }
        var value = result
        value["structure_b64"] = data.base64EncodedString()
        value["format"] = structure.pathExtension.lowercased() == "pdb" ? "pdb" : "cif"
        guard let json = try? JSONSerialization.data(withJSONObject: value) else { return nil }
        return json.base64EncodedString()
    }
    private static func hash(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
}
