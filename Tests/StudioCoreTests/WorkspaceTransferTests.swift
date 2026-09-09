import XCTest
@testable import StudioCore

final class WorkspaceTransferTests: XCTestCase {
    func testArchiveRestoreAndFailedIndexWrite() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: root) }
        let original = root.appendingPathComponent("projects/one")
        let archive = root.appendingPathComponent("archive/one")
        try fm.createDirectory(at: original, withIntermediateDirectories: true)
        try Data("checkpoint".utf8).write(to: original.appendingPathComponent("result"))
        let store = RecoverableJSONStore<[String]>(url: root.appendingPathComponent("index.json"))
        try store.save(["one"])
        let transfer = WorkspaceTransfer(root: root)
        try transfer.move(from: original, to: archive, saving: [], in: store)
        XCTAssertEqual(try store.load(), [])
        XCTAssertTrue(fm.fileExists(atPath: archive.appendingPathComponent("result").path))
        try transfer.move(from: archive, to: original, saving: ["one"], in: store)
        try fm.removeItem(at: store.backupURL)
        try fm.createDirectory(at: store.backupURL, withIntermediateDirectories: true)
        XCTAssertThrowsError(try transfer.move(from: original, to: archive, saving: [], in: store))
        XCTAssertTrue(fm.fileExists(atPath: original.appendingPathComponent("result").path))
        XCTAssertFalse(fm.fileExists(atPath: archive.path))
        XCTAssertEqual(try store.load(), ["one"])
    }
}
