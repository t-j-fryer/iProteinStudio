import Foundation
import Combine

/// Prepared off the UI actor once for each changed selection of result records.
struct ResultOverviewIndex {
    var groups: [StudioResultGroup] = []
    var distributions: [StudioResultMetric.Kind: [Double]] = [:]
    var medians: [StudioResultMetric.Kind: [ResultAnalysis.CycleMedian]] = [:]
    var defaultMetric: StudioResultMetric.Kind?

    init(items: [StudioResultItem] = [], includeScores: Bool = true) {
        groups = RunResultsLoader.groups(from: items)
        guard includeScores else { return }
        defaultMetric = ResultAnalysis.defaultMetric(in: items)
        for group in groups {
            if Task.isCancelled { return }
            let variants = group.variants
            let units = variants.isEmpty ? [group.sortedItems] : variants.map(\.sortedItems)
            for unit in units {
                let ordered = unit.sorted {
                    StudioResultGroup.metricPriority($0.artifactRole) < StudioResultGroup.metricPriority($1.artifactRole)
                }
                var seen = Set<StudioResultMetric.Kind>()
                for item in ordered {
                    for metric in item.metrics where !seen.contains(metric.kind) && metric.value.isFinite {
                        distributions[metric.kind, default: []].append(metric.value)
                        seen.insert(metric.kind)
                    }
                }
            }
        }
        for kind in distributions.keys {
            if Task.isCancelled { return }
            medians[kind] = ResultAnalysis.cycleMedians(items: items, metric: kind)
        }
    }
}

@MainActor
final class ResultOverviewModel: ObservableObject {
    @Published private(set) var index = ResultOverviewIndex()
    private var task: Task<Void, Never>?
    private var generation = 0

    func update(_ items: [StudioResultItem], includeScores: Bool = true) {
        generation += 1
        let expected = generation
        task?.cancel()
        task = Task { [weak self] in
            let worker = Task.detached(priority: .userInitiated) { ResultOverviewIndex(items: items, includeScores: includeScores) }
            let next = await withTaskCancellationHandler { await worker.value } onCancel: { worker.cancel() }
            guard !Task.isCancelled, let self, self.generation == expected else { return }
            self.index = next
        }
    }

    deinit { task?.cancel() }
}

struct ResultReviewIndex {
    var source: [StudioResultItem] = []
    var candidates: [ResultCandidate] = []
    var metrics: [StudioResultMetric.Kind] = []
    var preferred: StudioResultMetric.Kind?

    init(items: [StudioResultItem] = []) {
        source = items
        candidates = ResultAnalysis.candidates(from: items)
        let available = candidates.reduce(into: Set<StudioResultMetric.Kind>()) { $0.formUnion($1.metricKinds) }
        metrics = StudioResultMetric.Kind.allCases.filter { available.contains($0) }
        preferred = ResultAnalysis.defaultMetric(in: items)
    }
}

@MainActor
final class ResultHitReviewModel: ObservableObject {
    @Published private(set) var index = ResultReviewIndex()
    @Published private(set) var shown: [ResultCandidate] = []
    @Published private(set) var busy = false
    private var task: Task<Void, Never>?
    private var generation = 0

    func update(items: [StudioResultItem], policy: ResultHitPolicy, preferred: StudioResultMetric.Kind?, spatialRows: [String: ResultSpatialRow] = [:]) {
        generation += 1
        let expected = generation
        let cached = index
        task?.cancel()
        busy = true
        task = Task { [weak self] in
            let worker = Task.detached(priority: .userInitiated) {
                var index = cached.source == items ? cached : ResultReviewIndex(items: items)
                // Cached candidates may carry a previous review; rebuild their supplemental
                // fields from the exact matching source and policy, never reuse stale metrics.
                let key = policy.spatial?.digest
                index.candidates = index.candidates.map { candidate in
                    var valid: ResultSpatialRow?
                    if let row = spatialRows[candidate.id], row.policy_sha256 == key,
                       let source = candidate.analysisSource, source.id == row.source_item_id,
                       source.structureURL.path == row.source, source.coordinateStamp == row.source_stamp,
                       ResultFileStamp.read(source.structureURL) == row.source_stamp { valid = row }
                    return ResultCandidate(id: candidate.id, name: candidate.name, family: candidate.family, cycle: candidate.cycle,
                        sequence: candidate.sequence, savedHit: candidate.savedHit, items: candidate.items, group: candidate.group, spatial: valid)
                }
                let available = index.candidates.reduce(into: Set<StudioResultMetric.Kind>()) { $0.formUnion($1.metricKinds) }
                index.metrics = StudioResultMetric.Kind.allCases.filter { available.contains($0) }
                let shown = policy.select(index.candidates, defaultMetric: preferred ?? index.preferred)
                return (index, shown)
            }
            let next = await withTaskCancellationHandler { await worker.value } onCancel: { worker.cancel() }
            guard !Task.isCancelled, let self, self.generation == expected else { return }
            self.index = next.0; self.shown = next.1; self.busy = false
        }
    }

    deinit { task?.cancel() }
}
