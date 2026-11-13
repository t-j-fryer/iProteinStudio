import XCTest
@testable import StudioCore

final class ManagedWorkspaceDiscoveryTests: XCTestCase {
    private func fixture(_ body: (URL) throws -> Void) throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try body(root)
    }
    private func marker(_ path: String, under root: URL) throws {
        let url = root.appendingPathComponent(path)
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        // Discovery must not parse scientific input or mutate any output bytes.
        try Data("opaque fixture, intentionally not JSON".utf8).write(to: url)
    }

    func testCLIOnlyNativeIterativeBeamWorkspacesAreDiscoveredWithoutRewritingOutputs() throws {
        try fixture { root in
            for path in ["first/rfd4_runs/native/rfd4_config.json", "second/rfd4_runs/native-extra/rfd4_config.json",
                         "second/rfd4_runs/iterative/rfd4_config.json", "second/rfd4_runs/beam/rfd4_config.json"] {
                try marker(path, under: root)
            }
            let before = try Data(contentsOf: root.appendingPathComponent("second/rfd4_runs/beam/rfd4_config.json"))
            let found = ManagedWorkspaceDiscovery.discover(in: root)
            XCTAssertEqual(found.map(\.slug), ["first", "second"])
            XCTAssertEqual(found.map(\.workflow), [.rfd4, .rfd4])
            XCTAssertEqual(try Data(contentsOf: root.appendingPathComponent("second/rfd4_runs/beam/rfd4_config.json")), before)
            XCTAssertFalse(FileManager.default.fileExists(atPath: root.appendingPathComponent("config.json").path))
        }
    }

    func testExistingAndArchivedWorkspacesAreNotDuplicated() throws {
        try fixture { root in
            try marker("existing/prediction_runs/a/prediction_config.json", under: root)
            try marker("archived/rfd4_runs/a/rfd4_config.json", under: root)
            try marker("fresh/nise_runs/a/nise_config.json", under: root)
            XCTAssertEqual(ManagedWorkspaceDiscovery.discover(in: root, excluding: ["EXISTING", "archived"]).map(\.slug), ["fresh"])
        }
    }

    func testEveryWorkflowAndLateArrivingRun() throws {
        try fixture { root in
            XCTAssertTrue(ManagedWorkspaceDiscovery.discover(in: root).isEmpty)
            for path in ["prediction/prediction_runs/a/prediction_config.json", "rfd3/rfd3_runs/a/config/campaign.json",
                         "hunter/a/studio_run.json", "legacy/rfd3/config/campaign.json"] { try marker(path, under: root) }
            let found = ManagedWorkspaceDiscovery.discover(in: root)
            XCTAssertEqual(Set(found.map(\.workflow)), [.prediction, .rfd3, .iterative])
            XCTAssertEqual(found.count, 4)
            let old = found.first { $0.slug == "hunter" }!.id
            try marker("hunter/later/summary_all_runs.csv", under: root)
            XCTAssertEqual(ManagedWorkspaceDiscovery.discover(in: root).first { $0.slug == "hunter" }!.id, old)
        }
    }

    func testEmptyExportsHiddenAndSymlinkDirectoriesAreIgnored() throws {
        try fixture { root in
            try marker("exports/analysis/summary_counts.csv", under: root)
            try marker(".hidden/rfd4_runs/a/rfd4_config.json", under: root)
            try FileManager.default.createDirectory(at: root.appendingPathComponent("empty"), withIntermediateDirectories: true)
            try fixture { outside in
                try marker("run/rfd4_runs/a/rfd4_config.json", under: outside)
                try FileManager.default.createSymbolicLink(at: root.appendingPathComponent("linked"),
                    withDestinationURL: outside.appendingPathComponent("run"))
                XCTAssertTrue(ManagedWorkspaceDiscovery.discover(in: root).isEmpty)
            }
        }
    }

    func testIdentityMatchesPythonBridgeUUIDv5() {
        XCTAssertEqual(ManagedWorkspaceDiscovery.stableID(for: "figure3b-optimized-mac50-0844").uuidString.lowercased(),
                       "e4e0192b-a9fe-5a76-8105-08f0f3f67535")
        XCTAssertNotEqual(ManagedWorkspaceDiscovery.stableID(for: "first"), ManagedWorkspaceDiscovery.stableID(for: "second"))
    }
}
