import Foundation

/// Executes the persistence boundary even on machines with Command Line Tools
/// alone. XCTest remains required by Tests/run.py and CI.
@main
struct StudioCoreContractHarness {
    static func expect(_ condition: @autoclosure () throws -> Bool, _ message: String) throws {
        guard try condition() else { throw Failure(message: message) }
    }
    struct Failure: Error { let message: String }
    static func expectFailure(_ operation: () throws -> Void) throws {
        do { try operation() } catch { return }
        throw Failure(message: "Expected operation to fail")
    }
    static func main() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: root) }
        let store = RecoverableJSONStore<[String]>(url: root.appendingPathComponent("index.json"))
        try store.save(["one"]); try store.save(["two"])
        try Data("damaged".utf8).write(to: store.url)
        try expectFailure { try store.save([]) }
        try expect(try store.recover() == ["one"], "backup recovery")
        try expect(try fm.contentsOfDirectory(atPath: root.path).contains { $0.contains("unreadable-") }, "damaged evidence preserved")
        let source = root.appendingPathComponent("projects/one")
        let destination = root.appendingPathComponent("archive/one")
        try fm.createDirectory(at: source, withIntermediateDirectories: true)
        try Data("checkpoint".utf8).write(to: source.appendingPathComponent("result"))
        let transfer = WorkspaceTransfer(root: root)
        try transfer.move(from: source, to: destination, saving: [], in: store)
        try expect(try store.load() == [], "archive index")
        try transfer.move(from: destination, to: source, saving: ["one"], in: store)
        try fm.removeItem(at: store.backupURL)
        try fm.createDirectory(at: store.backupURL, withIntermediateDirectories: true)
        try expectFailure { try transfer.move(from: source, to: destination, saving: [], in: store) }
        try expect(fm.fileExists(atPath: source.appendingPathComponent("result").path), "failed save rolls directory back")
        try fm.removeItem(at: store.backupURL)
        struct Journal: Encodable {
            let source: URL; let destination: URL; let index: URL
            let before: Data; let after: Data; let hadFiles: Bool
        }
        // Simulate a process crash after moving the directory, before saving.
        let journal = Journal(source: source, destination: destination, index: store.url,
                              before: try Data(contentsOf: store.url), after: try store.encoded([]), hadFiles: true)
        try JSONEncoder().encode(journal).write(to: transfer.journalURL)
        try fm.moveItem(at: source, to: destination)
        try transfer.recover()
        try expect(fm.fileExists(atPath: source.path), "crash before commit rolls back")
        // Simulate a crash after saving the index, before journal cleanup.
        try JSONEncoder().encode(journal).write(to: transfer.journalURL)
        try fm.moveItem(at: source, to: destination)
        try store.save([])
        try transfer.recover()
        try expect(fm.fileExists(atPath: destination.path), "crash after commit preserves archive")
        var lease: ExecutionLease? = try ExecutionLease(directory: root)
        try expectFailure { _ = try ExecutionLease(directory: root) }
        withExtendedLifetime(lease) {}
        lease = nil
        _ = try ExecutionLease(directory: root)
        let report = SupportReport.make(version: "test", system: "test", memoryBytes: 0,
                                        message: "Could not write token=secret /Users/person/private ACDEFG",
                                        log: ["PBFAIL|secret scientific input"])
        try expect(!report.contains("secret") && !report.contains("/Users/") && !report.contains("ACDEFG"), "support report excludes raw input")
        try expect(report.contains("PBFAIL"), "support report retains safe failure marker")
        print("PASS StudioCore recovery, archive crash replay, lock and support report contracts")
    }
}
