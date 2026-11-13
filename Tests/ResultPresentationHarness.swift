import Foundation

enum StudioWorkflow: String, Codable { case rfd4, iterative, nise, rfdiffusion3, prediction; var label: String { rawValue } }
final class LoadCounter: @unchecked Sendable {
    private let lock = NSLock()
    private var count = 0
    func increment() { lock.lock(); count += 1; lock.unlock() }
    var value: Int { lock.lock(); defer { lock.unlock() }; return count }
}

@main
struct ResultPresentationHarness {
    @MainActor static func main() async throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent("results-presentation-" + UUID().uuidString)
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: root) }
        let items = (0..<5000).map { n in
            StudioResultItem(id: "c\(n)", title: "c\(n)", subtitle: "", structureURL: root.appendingPathComponent("model.cif"),
                sequence: "GAS", metrics: [.init(kind: .ipsaeMinimum, value: Double(n % 100) / 100), .init(kind: .plddt, value: 0.8)],
                confidenceURL: nil, stage: .design, scoreSource: "Fixture", isHit: n % 2 == 0,
                groupID: "family\(n/100)", variantID: "c\(n)", artifactRole: .designedComplex, cycle: n % 7 + 1)
        }
        let prepared = ResultOverviewIndex(items: items)
        precondition(prepared.groups.count == 50 && prepared.distributions[.ipsaeMinimum]?.count == 5000)
        precondition(prepared.medians[.ipsaeMinimum]?.reduce(0) { $0 + $1.count } == 5000)
        let reference = RunResultsLoader.groups(from: items).flatMap { $0.variants.compactMap { $0.metric(.ipsaeMinimum)?.value } }
        precondition(prepared.distributions[.ipsaeMinimum] == reference)
        precondition(ResultOverviewIndex(items: items, includeScores: false).distributions.isEmpty)
        let model = ResultHitReviewModel()
        var policy = ResultHitPolicy(); policy.mode = .custom
        policy.rules = [.init(metric: .ipsaeMinimum, threshold: "0.5")]
        policy.maxPerFamily = "2"
        model.update(items: items, policy: policy, preferred: .ipsaeMinimum)
        while model.busy { try await Task.sleep(nanoseconds: 10_000_000) }
        precondition(model.shown.count == 100 && model.index.candidates.count == 5000)
        precondition(model.shown.allSatisfy { $0.metric(.ipsaeMinimum)! >= 0.5 })
        precondition(Set(model.index.metrics) == [.ipsaeMinimum, .plddt])
        let exported = ResultAnalysis.csv(model.shown, mode: "custom")
        let csv = root.appendingPathComponent("hits.csv"); try exported.write(to: csv, atomically: true, encoding: .utf8)
        precondition(CSVTable.rows(at: csv).count == 100, "Export must include all pages")
        model.update(items: items, policy: policy, preferred: .ipsaeMinimum)
        policy.rules[0].threshold = "1.1"
        model.update(items: items, policy: policy, preferred: .ipsaeMinimum)
        while model.busy { try await Task.sleep(nanoseconds: 10_000_000) }
        precondition(model.shown.isEmpty, "Cancelled older selections must not overwrite the latest policy")
        let overview = ResultOverviewModel()
        overview.update(items)
        overview.update(Array(items.prefix(10)))
        for _ in 0..<200 {
            if overview.index.distributions[.ipsaeMinimum]?.count == 10 { break }
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        precondition(overview.index.distributions[.ipsaeMinimum]?.count == 10)
        for count in [0, 1, 25, 26, 100, 5000] {
            var visited: [Int] = []
            for page in 0..<ResultPage(count: count, requested: 0).pageCount {
                let range = ResultPage(count: count, requested: page).range
                precondition(range.count <= 25); visited += range
            }
            precondition(visited == Array(0..<count))
            precondition(ResultPage(count: count, requested: Int.max).range.upperBound <= count)
            precondition(ResultPage(count: count, requested: -1).number == 0)
        }
        var sameChainPolicy = ResultSpatialPolicy(); sameChainPolicy.mode = .ligand
        sameChainPolicy.binderChains = "A"; sameChainPolicy.targetChain = "A"; sameChainPolicy.ligandResidue = "901"
        precondition(sameChainPolicy.validationMessage == nil)
        sameChainPolicy.ligandResidue = ""; precondition(sameChainPolicy.validationMessage != nil)
        var spatialPolicy = ResultSpatialPolicy()
        spatialPolicy.binderChains = "A"; spatialPolicy.targetChain = "B"; spatialPolicy.residues = "10"
        var spatialItems = Array(items.prefix(2))
        try Data("coordinate-fixture".utf8).write(to: root.appendingPathComponent("model.cif"))
        for n in spatialItems.indices { spatialItems[n].coordinateStamp = ResultFileStamp.read(spatialItems[n].structureURL) }
        let spatialCandidates = ResultAnalysis.candidates(from: spatialItems)
        var rows: [String: ResultSpatialRow] = [:]
        for candidate in spatialCandidates {
            let source = candidate.analysisSource!
            let object: [String: Any] = ["id": candidate.id, "source_item_id": source.id,
                "source": source.structureURL.path, "source_stamp": source.coordinateStamp!,
                "source_sha256": "fixture", "policy_sha256": spatialPolicy.digest,
                "passed": source.id == "c0", "minimum_distance": 3.0, "maximum_distance": 3.0]
            rows[candidate.id] = try JSONDecoder().decode(ResultSpatialRow.self, from: JSONSerialization.data(withJSONObject: object))
        }
        var spatialHits = ResultHitPolicy(); spatialHits.mode = .custom; spatialHits.maxPerFamily = "1"; spatialHits.spatial = spatialPolicy
        model.update(items: spatialItems, policy: spatialHits, preferred: .ipsaeMinimum, spatialRows: rows)
        while model.busy { try await Task.sleep(nanoseconds: 10_000_000) }
        precondition(model.shown.count == 1 && model.shown[0].analysisSource?.id == "c0", "Spatial gate must run before family caps")
        precondition(model.shown[0].metric(.spatialMaximumDistance) == 3)
        precondition(ResultAnalysis.csv(model.shown, mode: "custom").contains("spatial_structure_sha256"))
        spatialHits.spatial?.cutoff = "7"
        model.update(items: spatialItems, policy: spatialHits, preferred: .ipsaeMinimum, spatialRows: rows)
        while model.busy { try await Task.sleep(nanoseconds: 10_000_000) }
        precondition(model.shown.isEmpty, "Changed spatial policy cannot use stale measurements")
        spatialHits.spatial = spatialPolicy
        try fm.setAttributes([.modificationDate: Date().addingTimeInterval(10)], ofItemAtPath: root.appendingPathComponent("model.cif").path)
        model.update(items: spatialItems, policy: spatialHits, preferred: .ipsaeMinimum, spatialRows: rows)
        while model.busy { try await Task.sleep(nanoseconds: 10_000_000) }
        precondition(model.shown.isEmpty, "Changed pose metadata must invalidate spatial matches")
        let legacyPolicy = Data("{\"mode\":\"saved\",\"rules\":[],\"descending\":true,\"maxPerFamily\":\"0\"}".utf8)
        let legacyDecoded = try JSONDecoder().decode(ResultHitPolicy.self, from: legacyPolicy)
        precondition(legacyDecoded.spatial == nil)
        let counter = LoadCounter()
        let repository = ResultsRepository(loader: { _, _ in counter.increment(); Thread.sleep(forTimeInterval: 0.05); return items })
        _ = await repository.load(root: root, workflow: .rfd4)
        _ = await repository.load(root: root, workflow: .rfd4)
        precondition(counter.value == 1)
        try await Task.sleep(nanoseconds: 1_050_000_000)
        _ = await repository.load(root: root, workflow: .rfd4)
        precondition(counter.value == 1, "Unchanged metadata must skip coordinate parsing and hashing after TTL")
        _ = await repository.load(root: root, workflow: .rfd4, forceReload: true)
        precondition(counter.value == 2, "Explicit Refresh must revalidate unchanged files")
        try "data_fixture".write(to: root.appendingPathComponent("model.cif"), atomically: true, encoding: .utf8)
        try await Task.sleep(nanoseconds: 1_050_000_000)
        async let first = repository.load(root: root, workflow: .rfd4)
        async let second = repository.load(root: root, workflow: .rfd4)
        _ = await (first, second)
        precondition(counter.value == 3, "Coordinate change invalidates cache and concurrent refreshes coalesce")
        try fm.createDirectory(at: root.appendingPathComponent(".studio_live_results"), withIntermediateDirectories: true)
        try "{}".write(to: root.appendingPathComponent(".studio_live_results/chunk.json"), atomically: true, encoding: .utf8)
        try await Task.sleep(nanoseconds: 1_050_000_000)
        _ = await repository.load(root: root, workflow: .rfd4)
        precondition(counter.value == 4, "Hidden live receipts invalidate cache")
        precondition(!ExternalStructureViewer.validStructure(root.appendingPathComponent("missing.cif")))
        precondition(ExternalStructureViewer.validStructure(root.appendingPathComponent("model.cif")))
        precondition(!ExternalStructureViewer.validStructure(URL(string: "https://example.org/model.cif")!))
        let directoryCIF = root.appendingPathComponent("directory.cif")
        try fm.createDirectory(at: directoryCIF, withIntermediateDirectories: true)
        precondition(!ExternalStructureViewer.validStructure(directoryCIF))
        precondition(!ExternalStructureViewer.validApplication(root))
        let nise = await repository.niseSnapshot(root: root)
        try await Task.sleep(nanoseconds: 2_050_000_000)
        let sameNise = await repository.niseSnapshot(root: root)
        precondition(nise.revision == sameNise.revision)
        let forcedNise = await repository.niseSnapshot(root: root, forceReload: true)
        precondition(nise.revision != forcedNise.revision)
        let unstableCounter = LoadCounter()
        let unstable = ResultsRepository(loader: { _, _ in
            unstableCounter.increment()
            if unstableCounter.value == 2 { try! Data("{}".utf8).write(to: root.appendingPathComponent("mid-load.json")) }
            return Array(items.prefix(unstableCounter.value))
        })
        let stableFirst = await unstable.load(root: root, workflow: .rfd4)
        precondition(stableFirst.count == 1)
        let changing = await unstable.load(root: root, workflow: .rfd4, forceReload: true)
        precondition(changing.count == 1, "Concurrent writes must retain the last stable snapshot")
        let stableAfter = await unstable.load(root: root, workflow: .rfd4, forceReload: true)
        precondition(stableAfter.count == 3)
        print("PASS 5000-candidate background presentation, latest-request isolation, complete paged export, bounded pages, cache invalidation/coalescing and external-viewer validation")
    }
}
