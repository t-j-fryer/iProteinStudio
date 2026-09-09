import Foundation

/// A tiny journal joins a same-volume directory move to an atomic index write.
/// Recovery either recognizes the committed index or restores the original path.
public struct WorkspaceTransfer {
    public let root: URL
    public var journalURL: URL { root.appendingPathComponent("workspace-transfer.json") }
    public init(root: URL) { self.root = root }
    private struct Journal: Codable {
        let source: URL
        let destination: URL
        let index: URL
        let before: Data
        let after: Data
        let hadFiles: Bool
    }
    public func move<Value>(from source: URL, to destination: URL,
                            saving value: Value, in store: RecoverableJSONStore<Value>) throws {
        try recover()
        let fm = FileManager.default
        guard contains(source), contains(destination), contains(store.url),
              !fm.fileExists(atPath: destination.path) else { throw TransferError.conflict }
        let journal = Journal(source: source, destination: destination, index: store.url,
                              before: try Data(contentsOf: store.url), after: try store.encoded(value),
                              hadFiles: fm.fileExists(atPath: source.path))
        try JSONEncoder().encode(journal).write(to: journalURL, options: .atomic)
        do {
            try fm.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
            if journal.hadFiles { try fm.moveItem(at: source, to: destination) }
            try store.save(value)
        } catch {
            // A failed rollback leaves the journal for next-launch recovery.
            try recover()
            throw error
        }
        try fm.removeItem(at: journalURL)
    }
    public func recover() throws {
        let fm = FileManager.default
        guard fm.fileExists(atPath: journalURL.path) else { return }
        let journal = try JSONDecoder().decode(Journal.self, from: Data(contentsOf: journalURL))
        guard contains(journal.source), contains(journal.destination), contains(journal.index) else { throw TransferError.conflict }
        let saved = try Data(contentsOf: journal.index)
        if saved == journal.after {
            try fm.removeItem(at: journalURL)
            return
        }
        guard saved == journal.before else { throw TransferError.conflict }
        if journal.hadFiles && !fm.fileExists(atPath: journal.source.path) {
            try fm.moveItem(at: journal.destination, to: journal.source)
        }
        try fm.removeItem(at: journalURL)
    }
    private func contains(_ url: URL) -> Bool {
        url.resolvingSymlinksInPath().standardizedFileURL.path.hasPrefix(root.resolvingSymlinksInPath().standardizedFileURL.path + "/")
    }
    public enum TransferError: LocalizedError {
        case conflict
        public var errorDescription: String? { "The workspace transfer conflicts with existing files. Studio kept the files and paused the operation." }
    }
}
