import Foundation
import Darwin

struct Project {
    let slug: String
}

@main
struct PipelineSnapshotContractHarness {
    static func fail(_ message: String) -> Never {
        FileHandle.standardError.write(Data("FAIL: \(message)\n".utf8))
        exit(1)
    }

    static func inode(_ url: URL) throws -> UInt64 {
        let values = try FileManager.default.attributesOfItem(atPath: url.path)
        return (values[.systemFileNumber] as? NSNumber)?.uint64Value ?? 0
    }

    static func main() throws {
        let fm = FileManager.default
        guard let raw = ProcessInfo.processInfo.environment["IPROTEINSTUDIO_TEST_SUPPORT_ROOT"]
        else { fail("isolated support root was not provided") }
        let root = URL(fileURLWithPath: raw, isDirectory: true)
        let firstCampaign = root.appendingPathComponent("campaign-one", isDirectory: true)
        let secondCampaign = root.appendingPathComponent("campaign-two", isDirectory: true)
        try fm.createDirectory(at: firstCampaign, withIntermediateDirectories: true)
        try fm.createDirectory(at: secondCampaign, withIntermediateDirectories: true)

        let first = try AppPaths.createPipelineSnapshot(in: firstCampaign)
        let second = try AppPaths.createPipelineSnapshot(in: secondCampaign)
        let firstMetadata = try JSONSerialization.jsonObject(
            with: Data(contentsOf: first.appendingPathComponent("snapshot.json"))
        ) as? [String: Any]
        guard let digest = firstMetadata?["pipeline_sha256"] as? String,
              digest.count == 64,
              (firstMetadata?["schema_version"] as? NSNumber)?.intValue == 2
        else { fail("snapshot provenance is incomplete") }
        let object = root.appendingPathComponent("objects/pipeline/sha256/\(digest)",
                                                 isDirectory: true)
        let relative = "PIPELINE_VERSION"
        let objectFile = object.appendingPathComponent(relative)
        let firstFile = first.appendingPathComponent(relative)
        let secondFile = second.appendingPathComponent(relative)
        guard fm.fileExists(atPath: first.appendingPathComponent("scripts/prepare_boltz_template.py").path)
        else { fail("target-template normalizer was omitted from the campaign snapshot") }
        guard fm.fileExists(atPath: first.appendingPathComponent("scripts/prepare_intellifold_template.py").path),
              fm.fileExists(atPath: first.appendingPathComponent("scripts/intellifold_user_template.py").path)
        else { fail("IntelliFold target-template policy was omitted from the campaign snapshot") }
        let original = try Data(contentsOf: objectFile)
        guard try Data(contentsOf: firstFile) == original,
              try Data(contentsOf: secondFile) == original,
              try inode(firstFile) != inode(objectFile),
              try inode(secondFile) != inode(firstFile)
        else { fail("campaign snapshots are not independent materialisations") }

        try Data("changed-only-in-first-campaign\n".utf8).write(to: firstFile)
        guard try Data(contentsOf: objectFile) == original,
              try Data(contentsOf: secondFile) == original
        else { fail("editing one campaign mutated another snapshot or its object") }

        let objects = try fm.contentsOfDirectory(at: object.deletingLastPathComponent(),
                                                  includingPropertiesForKeys: nil)
            .filter { !$0.lastPathComponent.hasPrefix(".") }
        guard objects.count == 1 else { fail("identical pipelines created duplicate objects") }
        print("PASS content-addressed pipeline snapshots")
    }
}
