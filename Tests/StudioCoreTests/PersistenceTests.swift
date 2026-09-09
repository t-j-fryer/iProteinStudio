import XCTest
@testable import StudioCore

final class PersistenceTests: XCTestCase {
    func testCorruptionRequiresRecoveryAndPreservesEvidence() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = RecoverableJSONStore<[String]>(url: root.appendingPathComponent("config.json"))
        try store.save(["original"])
        try store.save(["new"])
        try Data("broken".utf8).write(to: store.url)
        XCTAssertThrowsError(try store.load())
        XCTAssertThrowsError(try store.save([]))
        XCTAssertEqual(try String(contentsOf: store.url), "broken")
        XCTAssertEqual(try store.recover(), ["original"])
        XCTAssertTrue(try FileManager.default.contentsOfDirectory(atPath: root.path).contains { $0.contains("unreadable-") })
        try store.save(["recovered edit"])
        XCTAssertEqual(try store.load(), ["recovered edit"])
    }

    func testMissingPrimaryDoesNotDiscardBackup() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = RecoverableJSONStore<[String]>(url: root.appendingPathComponent("config.json"))
        try store.save(["one"]); try store.save(["two"])
        try FileManager.default.removeItem(at: store.url)
        XCTAssertThrowsError(try store.save([]))
        XCTAssertEqual(try store.recover(), ["one"])
    }

    func testFailedWriteLeavesReadablePrimary() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = RecoverableJSONStore<[String]>(url: root.appendingPathComponent("config.json"))
        try store.save(["saved"])
        // A directory at the backup destination deterministically injects an I/O
        // failure without relying on permissions or a real full disk.
        try FileManager.default.createDirectory(at: store.backupURL, withIntermediateDirectories: true)
        XCTAssertThrowsError(try store.save(["unsaved"]))
        XCTAssertEqual(try store.load(), ["saved"])
    }

    func testExecutionLeaseExcludesConcurrentOwners() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        var first: ExecutionLease? = try ExecutionLease(directory: root)
        XCTAssertThrowsError(try ExecutionLease(directory: root))
        withExtendedLifetime(first) {}
        first = nil
        XCTAssertNoThrow(try ExecutionLease(directory: root))
    }
}
