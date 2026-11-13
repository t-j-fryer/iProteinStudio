import Foundation

/// Metadata-only inspection using the same discovery as AppState. No input bodies.
@main struct ManagedWorkspaceInspectionHarness {
    static func main() throws {
        let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        let prefix = CommandLine.arguments[2]
        let workspaces = ManagedWorkspaceDiscovery.discover(in: root).filter { $0.slug.hasPrefix(prefix) }
        let rows = workspaces.map { ["slug": $0.slug, "id": $0.id.uuidString, "workflow": $0.workflow.rawValue] }
        let data = try JSONSerialization.data(withJSONObject: rows, options: [.prettyPrinted, .sortedKeys])
        print(String(decoding: data, as: UTF8.self))
    }
}
