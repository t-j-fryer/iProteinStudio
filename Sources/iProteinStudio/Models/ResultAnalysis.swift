import Foundation

/// Read-only analysis units. A cycle/derivative receives one row, with its own
/// associated assessments. Original hit verdicts and structures are immutable.
struct ResultCandidate: Identifiable {
    let id: String
    let name: String
    let family: String
    let cycle: Int?
    let sequence: String?
    let savedHit: Bool?
    let items: [StudioResultItem]
    let group: StudioResultGroup
    let spatial: ResultSpatialRow?

    private let scores: [StudioResultMetric.Kind: Double]
    var metricKinds: Set<StudioResultMetric.Kind> { Set(scores.keys) }

    init(id: String, name: String, family: String, cycle: Int?, sequence: String?,
         savedHit: Bool?, items: [StudioResultItem], group: StudioResultGroup, spatial: ResultSpatialRow? = nil) {
        self.id = id; self.name = name; self.family = family; self.cycle = cycle
        self.sequence = sequence; self.savedHit = savedHit; self.items = items; self.group = group
        let priority: [StudioResultArtifactRole] = [.complexReprediction, .designedComplex, .generatedBackbone, .prediction, .binderAlone, .startingStructure]
        let ordered = items.sorted {
            let a = priority.firstIndex(of: $0.artifactRole) ?? 99
            let b = priority.firstIndex(of: $1.artifactRole) ?? 99
            return a == b ? $0.id < $1.id : a < b
        }
        var values: [StudioResultMetric.Kind: Double] = [:]
        for item in ordered {
            for metric in item.metrics where values[metric.kind] == nil {
                if let value = ResultAnalysis.value(metric) { values[metric.kind] = value }
            }
        }
        self.spatial = spatial
        values.merge(spatial?.scores ?? [:]) { _, new in new }
        scores = values
    }

    var analysisSource: StudioResultItem? {
        let roles: [StudioResultArtifactRole] = [.complexReprediction, .designedComplex, .generatedBackbone, .prediction]
        return items.filter { roles.contains($0.artifactRole) }.sorted {
            let a = roles.firstIndex(of: $0.artifactRole)!, b = roles.firstIndex(of: $1.artifactRole)!
            return a == b ? $0.id < $1.id : a < b
        }.first
    }

    func metric(_ kind: StudioResultMetric.Kind) -> Double? { scores[kind] }

}

enum ResultAnalysis {
    static func value(_ metric: StudioResultMetric) -> Double? {
        guard metric.value.isFinite else { return nil }
        switch metric.kind {
        case .plddt, .binderPLDDT: return metric.value <= 1.000001 ? metric.value * 100 : metric.value
        case .pocketFractionWithinCutoff: return metric.value * 100
        default: return metric.value
        }
    }

    static func defaultMetric(in items: [StudioResultItem]) -> StudioResultMetric.Kind? {
        if items.contains(where: \.smallMoleculeDesign) { return .boltzCombinedScore }
        let order: [StudioResultMetric.Kind] = [.ipsaeMinimum, .iptm, .ptm, .plddt]
        return order.first { kind in items.contains { $0.metrics.contains { $0.kind == kind && $0.value.isFinite } } }
            ?? items.flatMap(\.metrics).first { $0.value.isFinite }?.kind
    }

    static func candidates(from items: [StudioResultItem]) -> [ResultCandidate] {
        let groups = Dictionary(grouping: items, by: \.groupID).map { id, members in
            StudioResultGroup(id: id, title: members.first?.groupTitle ?? id, items: members)
        }
        return groups.flatMap { group -> [ResultCandidate] in
            if Task.isCancelled { return [] }
            let variants = group.variants
            let primary = variants.isEmpty ? [] : group.primaryItems
            let units: [(String, String, [StudioResultItem])] = variants.isEmpty
                ? [(group.id, group.title, group.items)]
                : variants.map { ($0.id, group.title + " · " + $0.title, $0.items) }
            return units.compactMap { variant, name, members in
                let eligible = members.filter { $0.stage != .startingStructure }
                guard !eligible.isEmpty, eligible.contains(where: { $0.isHit == true || !$0.metrics.isEmpty }) else { return nil }
                let design = eligible.sorted {
                    let a = $0.artifactRole == .designedComplex ? 0 : 1
                    let b = $1.artifactRole == .designedComplex ? 0 : 1
                    return a == b ? $0.id < $1.id : a < b
                }
                let verdicts = eligible.compactMap(\.isHit)
                return ResultCandidate(id: "\(group.id.utf8.count):\(group.id)\(variant)", name: name,
                    family: group.id, cycle: eligible.compactMap(\.cycle).first ?? legacyCycle(variant),
                    sequence: design.compactMap(\.sequence).first { !$0.isEmpty },
                    savedHit: verdicts.isEmpty ? nil : verdicts.contains(true), items: eligible,
                    group: .init(id: group.id, title: name, items: variants.isEmpty ? eligible : primary + eligible))
            }
        }
    }

    struct CycleMedian: Identifiable {
        let cycle: Int
        let series: String
        let median: Double
        let count: Int
        var id: String { "\(series)|\(cycle)" }
    }

    static func cycleMedians(items: [StudioResultItem], metric: StudioResultMetric.Kind) -> [CycleMedian] {
        // Multiple structure files for one candidate/assessment must not reweight it.
        var observations: [String: [String: Double]] = [:]
        var labels: [String: (Int, String)] = [:]
        for item in items where item.stage != .startingStructure {
            if Task.isCancelled { break }
            let cycle = item.cycle ?? legacyCycle(item.variantID)
            guard let cycle, cycle >= 0,
                  let raw = item.metrics.first(where: { $0.kind == metric }), let v = value(raw) else { continue }
            let series = item.scoreSource + " · " + item.stage.label + " · " + item.artifactRole.label
            let key = "\(cycle)|\(series)"
            let unit = "\(item.groupID.utf8.count):\(item.groupID)\(item.variantID ?? item.id)"
            if observations[key]?[unit] == nil { observations[key, default: [:]][unit] = v }
            labels[key] = (cycle, series)
        }
        return observations.compactMap { key, rows in
            guard let (cycle, series) = labels[key] else { return nil }
            let values = rows.values.sorted(); let m = values.count / 2
            let median = values.count.isMultiple(of: 2) ? (values[m-1] + values[m]) / 2 : values[m]
            return CycleMedian(cycle: cycle, series: series, median: median, count: values.count)
        }.sorted { $0.series == $1.series ? $0.cycle < $1.cycle : $0.series < $1.series }
    }

    private static func legacyCycle(_ id: String?) -> Int? {
        guard let id, id.hasPrefix("cycle|"), let n = Int(id.dropFirst(6)) else { return nil }
        return n
    }

    static func metricLabel(_ kind: StudioResultMetric.Kind) -> String {
        switch kind {
        case .plddt, .binderPLDDT, .ligandPLDDT: return kind.label + " (0–100)"
        case .ligandFreeSASA, .ligandBoundSASA: return kind.label + " (Å²)"
        case .ligandBuriedPercent, .pocketFractionWithinCutoff, .backboneCAValidity: return kind.label + " (%)"
        case .spatialMinimumDistance, .spatialMaximumDistance, .interfacePAEMinimum, .interfacePDE, .pocketMeanDistance,
             .complexRMSD, .binderBackboneRMSD, .binderRMSD, .ligandRMSD, .pocketPreorgRMSD,
             .motifInsertionRMSD, .motifPredictionRMSD, .motifInputRMSD, .motifPartnerRMSD, .motifCandidateRMSD, .motifMaximumDrift:
            return kind.label + " (Å)"
        default: return kind.label
        }
    }

    static func csv(_ candidates: [ResultCandidate], mode: String) -> String {
        let metrics = StudioResultMetric.Kind.allCases.filter { k in candidates.contains { $0.metric(k) != nil } }
        func text(_ value: String) -> String {
            let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
            let safe = trimmed.first.map { "=+-@".contains($0) } == true ? "'" + value : value
            return "\"" + safe.replacingOccurrences(of: "\"", with: "\"\"") + "\""
        }
        let hasSpatial = candidates.contains { $0.spatial != nil }
        let spatialHeaders = hasSpatial ? ["spatial_structure", "spatial_structure_sha256", "spatial_policy_sha256", "spatial_receipt"] : []
        let header = ["design_name", "design_sequence", "family_id", "design_id", "cycle", "saved_hit", "selection_mode", "score_sources"]
            + spatialHeaders + metrics.map { metricLabel($0) }
        var lines = [header.map(text).joined(separator: ",")]
        for candidate in candidates {
            let fields = [candidate.name, candidate.sequence ?? "", candidate.family, candidate.id,
                          candidate.cycle.map(String.init) ?? "", candidate.savedHit.map { $0 ? "true" : "false" } ?? "",
                          mode, Array(Set(candidate.items.map(\.scoreSource))).sorted().joined(separator: "; ")]
            let extra = hasSpatial ? [candidate.spatial?.source ?? "", candidate.spatial?.source_sha256 ?? "", candidate.spatial?.policy_sha256 ?? "", candidate.spatial?.receipt ?? ""] : []
            lines.append(((fields + extra).map(text) + metrics.map { candidate.metric($0).map { String($0) } ?? "" }).joined(separator: ","))
        }
        return lines.joined(separator: "\r\n") + "\r\n"
    }
}

struct ResultHitPolicy: Codable, Equatable {
    enum Mode: String, Codable { case saved, custom }
    enum Comparison: String, Codable, CaseIterable { case minimum = "≥", maximum = "≤", greater = ">", less = "<" }
    struct Rule: Codable, Identifiable, Equatable {
        var id = UUID()
        var metric: StudioResultMetric.Kind
        var comparison: Comparison = .minimum
        var threshold = ""
        var number: Double? { Double(threshold.trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isFinite ? $0 : nil } }
        func passes(_ candidate: ResultCandidate) -> Bool {
            guard let limit = number, let value = candidate.metric(metric) else { return false }
            switch comparison {
            case .minimum: return value >= limit
            case .maximum: return value <= limit
            case .greater: return value > limit
            case .less: return value < limit
            }
        }
    }
    var spatial: ResultSpatialPolicy? = nil
    var mode: Mode = .saved
    var rules: [Rule] = []
    var sortMetric: StudioResultMetric.Kind?
    var descending = true
    var maxPerFamily = "0"
    var limit: Int? {
        let text = maxPerFamily.trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? 0 : Int(text).flatMap { $0 >= 0 ? $0 : nil }
    }
    var validationMessage: String? {
        if let message = spatial?.validationMessage { return message }
        if limit == nil { return "Enter a nonnegative whole number for the family limit (0 means unlimited)." }
        if mode == .custom && rules.contains(where: { $0.number == nil }) { return "Enter a finite number for each score threshold." }
        return nil
    }

    func select(_ candidates: [ResultCandidate], defaultMetric: StudioResultMetric.Kind?) -> [ResultCandidate] {
        guard validationMessage == nil, let limit else { return [] }
        let kind = sortMetric ?? defaultMetric
        let spatialKey = spatial?.digest
        let sorted = candidates.filter { candidate in
            let scorePass = mode == .saved ? candidate.savedHit == true : rules.allSatisfy { $0.passes(candidate) }
            guard scorePass else { return false }
            if spatialKey != nil { return candidate.spatial?.policy_sha256 == spatialKey && candidate.spatial?.passed == true }
            return true
        }
        // Written separately to keep comparator and missing-value handling deterministic.
        let ordered = sorted.sorted { a, b in
            let av = kind.flatMap { a.metric($0) }, bv = kind.flatMap { b.metric($0) }
            if let av, let bv, av != bv { return descending ? av > bv : av < bv }
            if av != nil && bv == nil { return true }
            if av == nil && bv != nil { return false }
            return a.id < b.id
        }
        guard limit > 0 else { return ordered }
        var counts: [String: Int] = [:]
        return ordered.filter { candidate in
            guard counts[candidate.family, default: 0] < limit else { return false }
            counts[candidate.family, default: 0] += 1
            return true
        }
    }
}
