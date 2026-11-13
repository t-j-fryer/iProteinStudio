import Foundation
import CryptoKit

/// Filesystem-owned workspaces also belong to the app library. Only inspect
/// shallow run markers; no scientific structures, sequences or config bodies.
public enum ManagedWorkspaceDiscovery {
    public enum Workflow: String, Sendable {
        case rfd4, rfd3, prediction, iterative, nise
    }

    public struct Workspace: Sendable {
        public let id: UUID
        public let slug: String
        public let createdAt: Date
        public let workflow: Workflow
    }

    public static func discover(in root: URL, excluding slugs: Set<String> = []) -> [Workspace] {
        let excluded = Set(slugs.map { $0.lowercased() })
        return directories(root).compactMap { directory in
            let slug = directory.lastPathComponent
            guard !excluded.contains(slug.lowercased()), let workflow = workflow(in: directory) else { return nil }
            let date = (try? directory.resourceValues(forKeys: [.creationDateKey]).creationDate) ?? .distantPast
            return Workspace(id: stableID(for: slug), slug: slug, createdAt: date, workflow: workflow)
        }.sorted { $0.slug.localizedStandardCompare($1.slug) == .orderedAscending }
    }

    /// Same UUIDv5 namespace and name as the client-neutral bridge's project_uuid.
    /// A CLI-only project must not acquire a new identity on each app launch.
    public static func stableID(for slug: String) -> UUID {
        var namespace = UUID(uuidString: "6BA7B811-9DAD-11D1-80B4-00C04FD430C8")!.uuid
        var data = withUnsafeBytes(of: &namespace) { Data($0) }
        data.append(contentsOf: "iproteinstudio-project:\(slug)".utf8)
        var bytes = Array(Insecure.SHA1.hash(data: data))
        bytes[6] = (bytes[6] & 0x0f) | 0x50
        bytes[8] = (bytes[8] & 0x3f) | 0x80
        return UUID(uuid: (bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7],
                           bytes[8], bytes[9], bytes[10], bytes[11], bytes[12], bytes[13], bytes[14], bytes[15]))
    }

    private static func workflow(in root: URL) -> Workflow? {
        for (folder, markers, workflow) in [
            ("rfd4_runs", ["rfd4_config.json", "studio_rfd4_request.json"], Workflow.rfd4),
            ("prediction_runs", ["prediction_config.json"], .prediction),
            ("rfd3_runs", ["config/campaign.json", "config/studio_request.json"], .rfd3),
            ("nise_runs", ["nise_config.json"], .nise)
        ] {
            if directories(root.appendingPathComponent(folder)).contains(where: { run in
                markers.contains { regularFile(run.appendingPathComponent($0)) }
            }) { return workflow }
        }
        if regularFile(root.appendingPathComponent("predictions/prediction_config.json")) { return .prediction }
        if regularFile(root.appendingPathComponent("rfd3/config/campaign.json")) { return .rfd3 }
        if directories(root).contains(where: { run in
            ["studio_run.json", "summary_all_runs.csv", "studio_engine_batch.json"].contains {
                regularFile(run.appendingPathComponent($0))
            }
        }) { return .iterative }
        return nil
    }

    private static func regularFile(_ url: URL) -> Bool {
        guard let values = try? url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey]) else { return false }
        return values.isRegularFile == true && values.isSymbolicLink != true
    }

    private static func directories(_ root: URL) -> [URL] {
        let keys: Set<URLResourceKey> = [.isDirectoryKey, .isSymbolicLinkKey]
        return ((try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: Array(keys),
                    options: [.skipsHiddenFiles])) ?? []).filter {
            guard let values = try? $0.resourceValues(forKeys: keys) else { return false }
            return values.isDirectory == true && values.isSymbolicLink != true
        }
    }
}
