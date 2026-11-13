import Foundation

/// Coalesces live/window refreshes off the UI actor. A changing metadata tree
/// retains the last stable snapshot; cache entries are bounded and short-lived.
actor ResultsRepository {
    static let shared = ResultsRepository()
    private struct Entry {
        let date: Date
        let items: [StudioResultItem]
        let fingerprint: [String: String]
    }
    typealias Loader = @Sendable (URL, StudioWorkflow) -> [StudioResultItem]
    private let loader: Loader
    init(loader: @escaping Loader = { RunResultsLoader.load(root: $0, workflow: $1) }) { self.loader = loader }
    private var cache: [String: Entry] = [:]
    private var pending: [String: Task<Entry, Never>] = [:]
    private struct NISEEntry { let date: Date; let snapshot: NISESnapshot; let fingerprint: [String: String] }
    private var niseCache: [String: NISEEntry] = [:]
    private var nisePending: [String: Task<NISEEntry, Never>] = [:]

    func niseSnapshot(root: URL, forceReload: Bool = false) async -> NISESnapshot {
        let key = root.standardizedFileURL.path
        if let task = nisePending[key] { return await task.value.snapshot }
        if !forceReload, let entry = niseCache[key], Date().timeIntervalSince(entry.date) < 2 { return entry.snapshot }
        let previous = niseCache[key]
        let task = Task.detached(priority: .utility) {
            let before = Self.fingerprint(root)
            if !forceReload, let previous, previous.fingerprint == before {
                return NISEEntry(date: Date(), snapshot: previous.snapshot, fingerprint: before)
            }
            var snapshot = NISEResultsLoader.load(root: root)
            snapshot.records = snapshot.records.map { record in
                var item = record.item; item.coordinateStamp = ResultFileStamp.read(item.structureURL)
                return NISERecord(item: item, phase: record.phase, cycle: record.cycle, geometryPassed: record.geometryPassed, eligible: record.eligible, advanced: record.advanced)
            }
            let after = Self.fingerprint(root)
            if before != after, let previous {
                return NISEEntry(date: Date(), snapshot: previous.snapshot, fingerprint: previous.fingerprint)
            }
            return NISEEntry(date: Date(), snapshot: snapshot, fingerprint: before)
        }
        nisePending[key] = task
        let entry = await task.value
        nisePending[key] = nil
        niseCache[key] = entry
        if niseCache.count > 4, let oldest = niseCache.min(by: { $0.value.date < $1.value.date })?.key {
            niseCache[oldest] = nil
        }
        return entry.snapshot
    }

    func load(root: URL, workflow: StudioWorkflow, forceReload: Bool = false) async -> [StudioResultItem] {
        if workflow == .nise { return await niseSnapshot(root: root, forceReload: forceReload).items }
        let key = root.standardizedFileURL.path + "|" + workflow.rawValue
        if let task = pending[key] { return await task.value.items }
        if !forceReload, let entry = cache[key], Date().timeIntervalSince(entry.date) < 1 { return entry.items }
        let previous = cache[key]
        let loader = self.loader
        let task = Task.detached(priority: .utility) {
            let before = Self.fingerprint(root)
            if !forceReload, let previous, previous.fingerprint == before {
                return Entry(date: Date(), items: previous.items, fingerprint: before)
            }
            let items = loader(root, workflow)
            let after = Self.fingerprint(root)
            if before != after, let previous {
                return Entry(date: Date(), items: previous.items, fingerprint: previous.fingerprint)
            }
            return Entry(date: Date(), items: items, fingerprint: before)
        }
        pending[key] = task
        let entry = await task.value
        pending[key] = nil
        cache[key] = entry
        if cache.count > 12, let oldest = cache.min(by: { $0.value.date < $1.value.date })?.key {
            cache[oldest] = nil
        }
        return entry.items
    }

    private nonisolated static func fingerprint(_ root: URL) -> [String: String] {
        let keys: [URLResourceKey] = [.fileSizeKey, .contentModificationDateKey]
        let campaigns = [root] + RunResultsLoader.batchCampaigns(root: root).map(\.root)
        let roots = campaigns + campaigns.map { $0.appendingPathComponent(".studio_live_results") }
        var result: [String: String] = [:]
        for directory in roots {
            guard let files = FileManager.default.enumerator(at: directory, includingPropertiesForKeys: keys, options: [.skipsHiddenFiles]) else { continue }
            for case let file as URL in files where ["csv", "json", "pdb", "cif", "mmcif"].contains(file.pathExtension.lowercased()) {
                guard let values = try? file.resourceValues(forKeys: Set(keys)) else { continue }
                result[file.path] = "\(values.fileSize ?? -1)|\(values.contentModificationDate?.timeIntervalSince1970 ?? -1)"
            }
        }
        return result
    }
}
