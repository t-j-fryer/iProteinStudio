import Foundation

/// Coalesces live/window refreshes off the UI actor. A changing metadata tree
/// retains the last stable snapshot; cache entries are bounded and short-lived.
actor ResultsRepository {
    static let shared = ResultsRepository()
    private struct Entry { let date: Date; let items: [StudioResultItem] }
    private var cache: [String: Entry] = [:]
    private var pending: [String: Task<[StudioResultItem], Never>] = [:]
    private var niseCache: [String: (Date, NISESnapshot)] = [:]
    private var nisePending: [String: Task<NISESnapshot, Never>] = [:]

    func niseSnapshot(root: URL) async -> NISESnapshot {
        let key = root.standardizedFileURL.path
        if let task = nisePending[key] { return await task.value }
        if let (date, snapshot) = niseCache[key], Date().timeIntervalSince(date) < 2 { return snapshot }
        let task = Task.detached(priority: .utility) { NISEResultsLoader.load(root: root) }
        nisePending[key] = task
        let snapshot = await task.value
        nisePending[key] = nil
        niseCache[key] = (Date(), snapshot)
        if niseCache.count > 4, let oldest = niseCache.min(by: { $0.value.0 < $1.value.0 })?.key {
            niseCache[oldest] = nil
        }
        return snapshot
    }

    func load(root: URL, workflow: StudioWorkflow) async -> [StudioResultItem] {
        if workflow == .nise { return await niseSnapshot(root: root).items }
        let key = root.standardizedFileURL.path + "|" + workflow.rawValue
        if let task = pending[key] { return await task.value }
        if let entry = cache[key], Date().timeIntervalSince(entry.date) < 1 { return entry.items }
        let previous = cache[key]?.items
        let task = Task.detached(priority: .utility) {
            let before = Self.fingerprint(root)
            let items = RunResultsLoader.load(root: root, workflow: workflow)
            let after = Self.fingerprint(root)
            if before != after, let previous { return previous }
            return items
        }
        pending[key] = task
        let items = await task.value
        pending[key] = nil
        cache[key] = Entry(date: Date(), items: items)
        if cache.count > 12, let oldest = cache.min(by: { $0.value.date < $1.value.date })?.key {
            cache[oldest] = nil
        }
        return items
    }

    private nonisolated static func fingerprint(_ root: URL) -> [String: String] {
        let keys: [URLResourceKey] = [.fileSizeKey, .contentModificationDateKey]
        let roots = [root] + RunResultsLoader.batchCampaigns(root: root).map(\.root)
        var result: [String: String] = [:]
        for directory in roots {
        guard let files = FileManager.default.enumerator(at: directory, includingPropertiesForKeys: keys, options: [.skipsHiddenFiles]) else { continue }
        for case let file as URL in files where ["csv", "json"].contains(file.pathExtension) {
            guard let values = try? file.resourceValues(forKeys: Set(keys)) else { continue }
            result[file.path] = "\(values.fileSize ?? -1)|\(values.contentModificationDate?.timeIntervalSince1970 ?? -1)"
        }
        }
        return result
    }
}
