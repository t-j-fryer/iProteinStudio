import Foundation
import Combine

/// One named, cached target-structure prediction.
struct PredictionRecord: Identifiable, Codable, Hashable {
    var id: String            // content+engine+model hash (matches on-disk cache dir)
    var name: String
    var targetKind: TargetKind
    var payload: String       // protein sequence or ligand SMILES
    var engine: String        // TargetEngine.rawValue
    var model: String         // IntelliFoldModel.rawValue
    var createdAt: Date

    var engineLabel: String {
        switch engine {
        case "intellifold": return "IntelliFold (\(model))"
        case "protenix_v2": return "Protenix v2"
        case "protenix_mini": return "Protenix Mini"
        default: return "Boltz"
        }
    }
}

/// Owns the on-disk prediction cache + a named index, shared across all projects.
/// Layout: <support>/target_predictions/{index.json, <id>/…engine output…}
@MainActor
final class PredictionStore: ObservableObject {
    @Published private(set) var records: [PredictionRecord] = []

    init() { load(); reconcile() }

    // MARK: shared cache location + key (also used by TargetPredictor)

    static var cacheRoot: URL {
        let d = AppPaths.support.appendingPathComponent("target_predictions", isDirectory: true)
        try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
        return d
    }

    static func key(targetKind: TargetKind, sequence: String, smiles: String,
                    engine: TargetEngine, model: IntelliFoldModel) -> String {
        let payload = targetKind == .protein ? "P|" + TemplateWriter.clean(sequence)
                                             : "L|" + smiles.trimmingCharacters(in: .whitespacesAndNewlines)
        let s = "\(payload)|\(engine.rawValue)|\(model.rawValue)"
        var h: UInt64 = 1469598103934665603
        for b in s.utf8 { h = (h ^ UInt64(b)) &* 1099511628211 }
        return String(h, radix: 16)
    }

    static func dir(for id: String) -> URL { cacheRoot.appendingPathComponent(id, isDirectory: true) }

    /// Versioned output owned by the shared prediction pipeline. Older Target
    /// Prep builds wrote direct, single-sequence folds beside this directory;
    /// they must not be mistaken for the MSA-backed result.
    static let currentResultDirectoryName = "shared-prediction-v1"

    static func currentResultDir(for id: String) -> URL {
        dir(for: id).appendingPathComponent(currentResultDirectoryName, isDirectory: true)
    }

    /// First structure file under a prediction dir (prefers model_0 / sample-0).
    static func findModelCIF(in dir: URL) -> URL? {
        guard let en = FileManager.default.enumerator(at: dir, includingPropertiesForKeys: nil) else { return nil }
        var cands: [URL] = []
        for case let url as URL in en where url.pathExtension.lowercased() == "cif" { cands.append(url) }
        cands.sort { $0.lastPathComponent < $1.lastPathComponent }
        return cands.first { $0.lastPathComponent.contains("model_0") || $0.lastPathComponent.contains("sample-0") }
            ?? cands.first
    }

    func cifPath(for record: PredictionRecord) -> String? {
        Self.findModelCIF(in: Self.currentResultDir(for: record.id))?.path
            ?? Self.findModelCIF(in: Self.dir(for: record.id))?.path
    }

    // MARK: mutations

    /// Record a prediction. Keeps an existing name if the id is already indexed.
    func upsert(id: String, name: String, targetKind: TargetKind, payload: String,
                engine: TargetEngine, model: IntelliFoldModel) {
        if records.contains(where: { $0.id == id }) { return }  // keep existing name/date
        let clean = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let rec = PredictionRecord(
            id: id,
            name: clean.isEmpty ? defaultName(targetKind: targetKind, payload: payload) : clean,
            targetKind: targetKind, payload: payload,
            engine: engine.rawValue, model: model.rawValue, createdAt: Date())
        records.insert(rec, at: 0)
        save()
    }

    func remove(_ ids: Set<String>) {
        for id in ids { try? FileManager.default.removeItem(at: Self.dir(for: id)) }
        records.removeAll { ids.contains($0.id) }
        save()
    }

    func rename(_ id: String, to name: String) {
        guard let i = records.firstIndex(where: { $0.id == id }) else { return }
        let t = name.trimmingCharacters(in: .whitespacesAndNewlines)
        if !t.isEmpty { records[i].name = t; save() }
    }

    func clearAll() {
        for r in records { try? FileManager.default.removeItem(at: Self.dir(for: r.id)) }
        // Remove any stray prediction dirs too.
        if let items = try? FileManager.default.contentsOfDirectory(at: Self.cacheRoot, includingPropertiesForKeys: nil) {
            for item in items where item.hasDirectoryPath { try? FileManager.default.removeItem(at: item) }
        }
        records = []
        save()
    }

    /// Total bytes used by cached predictions (for display).
    func totalBytes() -> Int64 {
        var total: Int64 = 0
        if let en = FileManager.default.enumerator(at: Self.cacheRoot, includingPropertiesForKeys: [.fileSizeKey]) {
            for case let url as URL in en {
                total += Int64((try? url.resourceValues(forKeys: [.fileSizeKey]))?.fileSize ?? 0)
            }
        }
        return total
    }

    // MARK: persistence

    private var indexURL: URL { Self.cacheRoot.appendingPathComponent("index.json") }

    func save() {
        if let data = try? JSONEncoder().encode(records) { try? data.write(to: indexURL) }
    }

    private func load() {
        guard let data = try? Data(contentsOf: indexURL),
              let recs = try? JSONDecoder().decode([PredictionRecord].self, from: data) else { return }
        records = recs
    }

    /// Drop index entries whose cache dir no longer has a structure.
    private func reconcile() {
        let before = records.count
        records.removeAll { cifPath(for: $0) == nil }
        if records.count != before { save() }
    }

    private func defaultName(targetKind: TargetKind, payload: String) -> String {
        targetKind == .protein ? "Protein (\(TemplateWriter.clean(payload).count) aa)" : "Ligand"
    }
}
