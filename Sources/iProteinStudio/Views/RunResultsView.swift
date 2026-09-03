import SwiftUI
import AppKit
import Charts

/// One in-app home for successful structures from all three workflows.
/// The loader normalises only the presentation layer; original files remain the
/// source of truth and are always one click away.
struct RunResultsView: View {
    private enum ResultsSection: String, CaseIterable, Identifiable {
        case overview = "Overview"
        case structures = "Structures"
        case hits = "Hits"
        var id: String { rawValue }
    }

    let root: URL
    let workflow: StudioWorkflow
    let title: String

    @Environment(\.dismiss) private var dismiss
    @State private var items: [StudioResultItem]
    @State private var selectedID: String?
    @State private var section: ResultsSection = .overview
    @State private var selectedMetric: StudioResultMetric.Kind = .iptm

    init(root: URL, workflow: StudioWorkflow, title: String? = nil) {
        self.root = root
        self.workflow = workflow
        self.title = title ?? "\(workflow.label) results"
        let loaded = RunResultsLoader.load(root: root, workflow: workflow)
        _items = State(initialValue: loaded)
        _selectedID = State(initialValue: loaded.first?.id)
        if let preferred = Self.preferredDistributionMetric(in: loaded) {
            _selectedMetric = State(initialValue: preferred)
        }
    }

    private var selection: StudioResultItem? {
        items.first { $0.id == selectedID } ?? items.first
    }

    private var iterativeHitSummary: String? {
        guard workflow == .iterative, !items.isEmpty else { return nil }
        let threshold = RunResultsLoader.iterativeHitThreshold(root: root)
        func passes(_ item: StudioResultItem) -> Bool {
            if let verdict = item.isHit { return verdict }
            return item.metrics.first { $0.kind == .iptm }.map { $0.value >= threshold } ?? false
        }
        let design = items.filter { $0.stage == .design && passes($0) }.count
        let checked = items.filter { $0.stage == .postPrediction && passes($0) }.count
        let hasSavedVerdicts = items.contains { $0.stage == .postPrediction && $0.isHit != nil }
        if hasSavedVerdicts {
            return "\(design) design-stage hit\(design == 1 ? "" : "s") at iPTM ≥ \(String(format: "%.2f", threshold)) · \(checked) independent check\(checked == 1 ? "" : "s") passed every saved filter"
        }
        return "\(design) design-stage hit\(design == 1 ? "" : "s") · \(checked) post-check hit\(checked == 1 ? "" : "s") at iPTM ≥ \(String(format: "%.2f", threshold))"
    }

    private var rfd3HitSummary: String? {
        guard workflow == .rfdiffusion3 else { return nil }
        let url = root.appendingPathComponent("analysis/hit_summary.json")
        guard let data = try? Data(contentsOf: url),
              let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let hits = (payload["hits"] as? NSNumber)?.intValue,
              let evaluated = (payload["designs_evaluated"] as? NSNumber)?.intValue
        else { return nil }
        return "\(hits) of \(evaluated) selected design\(evaluated == 1 ? "" : "s") passed every saved filter"
    }

    private var iterativeCountSummary: String? {
        guard workflow == .iterative, !items.isEmpty else { return nil }
        let designs = items.filter { $0.stage == .design }.count
        let starts = items.filter { $0.stage == .startingStructure }.count
        let checks = items.filter { $0.stage == .postPrediction }.count
        return "\(designs) optimized design\(designs == 1 ? "" : "s") · \(starts) cycle-00 start\(starts == 1 ? "" : "s") · \(checks) independent check\(checks == 1 ? "" : "s")"
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if workflow == .rfdiffusion3 {
                Picker("Results section", selection: $section) {
                    ForEach(ResultsSection.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .padding(.horizontal, 14).padding(.vertical, 10)
                Divider()
                switch section {
                case .overview: rfd3Overview
                case .structures: resultsBrowser(items)
                case .hits: resultsBrowser(items.filter { $0.isHit == true }, hitsOnly: true)
                }
            } else {
                resultsBrowser(items)
            }
        }
        .frame(minWidth: 920, idealWidth: 1060, minHeight: 650, idealHeight: 760)
        .accessibilityIdentifier("run-results-browser")
        .task(id: root.path) {
            guard workflow == .rfdiffusion3 else { return }
            while !Task.isCancelled {
                refresh()
                if FileManager.default.fileExists(atPath: root.appendingPathComponent("analysis/hit_summary.json").path) {
                    break
                }
                try? await Task.sleep(nanoseconds: 3_000_000_000)
            }
        }
    }

    private var header: some View {
        HStack(spacing: 12) {
            Image(systemName: workflow.systemImage)
                .font(.title2).foregroundStyle(.tint)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.headline)
                Text(iterativeCountSummary ?? "\(items.count) viewable structure\(items.count == 1 ? "" : "s")")
                    .font(.caption).foregroundStyle(.secondary)
                if let iterativeHitSummary {
                    Text(iterativeHitSummary).font(.caption2).foregroundStyle(.secondary)
                } else if let rfd3HitSummary {
                    Text(rfd3HitSummary).font(.caption2).foregroundStyle(.secondary)
                }
            }
            Spacer()
            if workflow == .rfdiffusion3 {
                Button { refresh() } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
            }
            Button {
                NSWorkspace.shared.activateFileViewerSelecting([root])
            } label: {
                Label("Reveal Run", systemImage: "folder")
            }
            Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
        }
        .padding(14)
    }

    private func resultsBrowser(_ visibleItems: [StudioResultItem], hitsOnly: Bool = false) -> some View {
        Group {
            if visibleItems.isEmpty {
                ContentUnavailableView(
                    hitsOnly ? "No saved hits yet" : "Waiting for structures",
                    systemImage: hitsOnly ? "line.3.horizontal.decrease.circle" : "cube.transparent",
                    description: Text(hitsOnly
                        ? "Hits appear after verification has applied every saved filter. You can still inspect all structures while the campaign runs."
                        : "Accepted backbones and successful verification structures will appear here automatically as they are written.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                HSplitView {
                    resultsList(visibleItems).frame(minWidth: 240, idealWidth: 275, maxWidth: 340)
                    if let selected = visibleItems.first(where: { $0.id == selectedID }) ?? visibleItems.first {
                        RunResultDetail(item: selected)
                            .id(selected.id)
                            .frame(minWidth: 620, maxWidth: .infinity, maxHeight: .infinity)
                    }
                }
            }
        }
    }

    private func resultsList(_ visibleItems: [StudioResultItem]) -> some View {
        List(selection: $selectedID) {
            ForEach(visibleItems) { item in
                RunResultRow(item: item).tag(item.id)
            }
        }
        .listStyle(.sidebar)
        .accessibilityLabel("Structures in this run")
    }

    private var availableMetrics: [StudioResultMetric.Kind] {
        StudioResultMetric.Kind.allCases.filter { kind in
            items.contains { item in item.metrics.contains { $0.kind == kind } }
        }
    }

    private func distributionValues(for kind: StudioResultMetric.Kind) -> [Double] {
        items.compactMap { item in item.metrics.first { $0.kind == kind }?.value }
    }

    /// A campaign can move from backbone-only metrics to predictor metrics
    /// while this sheet is open. Never leave the chart bound to a metric that
    /// disappeared during that stage transition.
    private var effectiveDistributionMetric: StudioResultMetric.Kind? {
        if availableMetrics.contains(selectedMetric),
           !distributionValues(for: selectedMetric).isEmpty {
            return selectedMetric
        }
        return Self.preferredDistributionMetric(in: items)
    }

    private var rfd3Overview: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack(spacing: 12) {
                    SummaryCard(value: items.count, label: "viewable structures")
                    SummaryCard(value: items.filter { $0.stage == .generatedBackbone }.count,
                                label: "generated backbones")
                    SummaryCard(value: items.filter { $0.stage == .verificationPrediction || $0.stage == .rankedDesign }.count,
                                label: "verification structures")
                    SummaryCard(value: items.filter { $0.isHit == true }.count, label: "saved hits")
                }

                if availableMetrics.isEmpty || effectiveDistributionMetric == nil {
                    ContentUnavailableView(
                        "Waiting for scored structures", systemImage: "chart.bar",
                        description: Text("The dashboard refreshes automatically as RFdiffusion3, sequence design and verification checkpoints arrive.")
                    )
                    .frame(minHeight: 360)
                } else if let metric = effectiveDistributionMetric {
                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text("Score distribution").font(.headline)
                            Text(metric.explanation).font(.caption).foregroundStyle(.secondary)
                                .lineLimit(2)
                        }
                        Spacer()
                        Picker("Metric", selection: Binding(
                            get: { metric }, set: { selectedMetric = $0 })) {
                            ForEach(availableMetrics, id: \.self) { kind in Text(kind.label).tag(kind) }
                        }
                        .frame(width: 230)
                    }
                    MetricDistributionChart(kind: metric, values: distributionValues(for: metric))
                        .frame(minHeight: 320)
                        .padding(14)
                        .background(RoundedRectangle(cornerRadius: 12).fill(.quaternary.opacity(0.20)))
                }

                HStack {
                    Button { section = .structures } label: {
                        Label("Browse Structures", systemImage: "cube.transparent")
                    }
                    .buttonStyle(.borderedProminent)
                    Button { section = .hits } label: {
                        Label("Browse Hits", systemImage: "checkmark.seal")
                    }
                    .disabled(!items.contains { $0.isHit == true })
                    Spacer()
                    Text("Updates automatically while the campaign is running")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .padding(18)
        }
    }

    private func refresh() {
        let loaded = RunResultsLoader.load(root: root, workflow: workflow)
        items = loaded
        if !loaded.contains(where: { $0.id == selectedID }) { selectedID = loaded.first?.id }
        if !availableMetrics.contains(selectedMetric),
           let preferred = Self.preferredDistributionMetric(in: loaded) {
            selectedMetric = preferred
        }
    }

    private static func preferredDistributionMetric(in items: [StudioResultItem]) -> StudioResultMetric.Kind? {
        let order: [StudioResultMetric.Kind] = [.iptm, .ipsaeMinimum, .motifPredictionRMSD,
                                                .motifInsertionRMSD, .plddt, .rankingScore,
                                                .backboneCAValidity]
        return order.first { kind in items.contains { $0.metrics.contains { $0.kind == kind } } }
            ?? items.first?.metrics.first?.kind
    }
}

private struct SummaryCard: View {
    let value: Int
    let label: String
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("\(value)").font(.title2.bold()).monospacedDigit()
            Text(label).font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 10).fill(.quaternary.opacity(0.25)))
    }
}

private struct MetricDistributionChart: View {
    struct Bin: Identifiable {
        let index: Int
        let lower: Double
        let upper: Double
        let count: Int
        var id: Int { index }
        var label: String { String(format: "%.3g–%.3g", lower, upper) }
    }

    let kind: StudioResultMetric.Kind
    let values: [Double]

    private var bins: [Bin] {
        guard let minimum = values.min(), let maximum = values.max() else { return [] }
        let count = min(12, max(1, Int(ceil(sqrt(Double(values.count))))))
        let span = maximum - minimum
        let width = span > 0 ? span / Double(count) : max(abs(minimum) * 0.05, 0.01)
        return (0..<count).map { index in
            let lower = span > 0 ? minimum + Double(index) * width : minimum - width / 2
            let upper = lower + width
            let frequency = values.filter { value in
                index == count - 1 ? value >= lower && value <= upper : value >= lower && value < upper
            }.count
            return Bin(index: index, lower: lower, upper: upper, count: frequency)
        }
    }

    private var sortedValues: [Double] { values.sorted() }

    private var median: Double? {
        let values = sortedValues
        guard !values.isEmpty else { return nil }
        let middle = values.count / 2
        return values.count.isMultiple(of: 2)
            ? (values[middle - 1] + values[middle]) / 2
            : values[middle]
    }

    private func display(_ value: Double?) -> String {
        guard let value else { return "—" }
        return StudioResultMetric(kind: kind, value: value).displayValue
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Chart(bins) { bin in
                BarMark(x: .value(kind.label, bin.label),
                        y: .value("Structures", bin.count), width: .ratio(0.82))
                    .foregroundStyle(Color.accentColor.opacity(0.78))
                    .annotation(position: .top, spacing: 3) {
                        if bin.count > 0 {
                            Text("\(bin.count)").font(.caption2).foregroundStyle(.primary)
                        }
                    }
            }
            .chartXAxis {
                AxisMarks(position: .bottom) { _ in
                    AxisTick(stroke: StrokeStyle(lineWidth: 1)).foregroundStyle(.primary)
                    AxisValueLabel().foregroundStyle(.primary)
                }
            }
            .chartYAxis {
                AxisMarks(position: .leading) { _ in
                    AxisTick(stroke: StrokeStyle(lineWidth: 1)).foregroundStyle(.primary)
                    AxisValueLabel().foregroundStyle(.primary)
                }
            }
            .chartYScale(domain: 0...max(1, (bins.map(\.count).max() ?? 0) + 1))
            .accessibilityLabel("Distribution of \(kind.label) across \(values.count) structures")

            HStack(spacing: 20) {
                DistributionStatistic(label: "n", value: "\(values.count)")
                DistributionStatistic(label: "minimum", value: display(values.min()))
                DistributionStatistic(label: "median", value: display(median))
                DistributionStatistic(label: "maximum", value: display(values.max()))
            }
        }
    }
}

private struct DistributionStatistic: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption2).foregroundStyle(.secondary)
            Text(value).font(.callout.monospacedDigit().weight(.medium))
        }
    }
}

private struct RunResultRow: View {
    let item: StudioResultItem

    var body: some View {
        HStack(spacing: 9) {
            Image(systemName: "cube.transparent.fill")
                .foregroundStyle(.tint).frame(width: 20)
            VStack(alignment: .leading, spacing: 2) {
                Text(item.title).font(.callout.weight(.semibold)).lineLimit(1)
                Text(item.subtitle).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer(minLength: 4)
            if let isHit = item.isHit {
                Image(systemName: isHit ? "checkmark.seal.fill" : "xmark.circle")
                    .foregroundStyle(isHit ? .green : .secondary)
                    .help(isHit ? "Passed every saved hit filter" : "Did not pass every saved hit filter")
            }
            if let metric = item.primaryMetric {
                VStack(alignment: .trailing, spacing: 0) {
                    Text(metric.displayValue).font(.caption.monospacedDigit().weight(.medium))
                    Text(metric.kind.label).font(.caption2).foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(rowAccessibilityLabel)
    }

    private var rowAccessibilityLabel: String {
        guard let metric = item.primaryMetric else { return "\(item.title), \(item.subtitle)" }
        return "\(item.title), \(item.subtitle), \(metric.kind.label) \(metric.displayValue)"
    }
}

private struct RunResultDetail: View {
    let item: StudioResultItem
    @State private var sequenceCopied = false

    private let columns = [GridItem(.adaptive(minimum: 128, maximum: 180), spacing: 10)]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            detailHeader
            Divider()
            StructureViewer(structurePath: item.structureURL.path)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color.black.opacity(0.025))
                .accessibilityLabel("Interactive py2Dmol structure for \(item.title)")
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if item.metrics.isEmpty {
                        Label("This engine did not emit a supported summary metric for this structure.",
                              systemImage: "info.circle")
                            .font(.callout).foregroundStyle(.secondary)
                    } else {
                        LazyVGrid(columns: columns, alignment: .leading, spacing: 10) {
                            ForEach(item.metrics) { metric in MetricTile(metric: metric) }
                        }
                    }

                    if shouldExplainMissingIPSAE {
                        Text("ipSAE(min) could not be calculated because this run has no supported PAE output. Studio does not substitute minimum PAE or interface PDE for it.")
                            .font(.caption2).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    if item.isHit == false, !item.failedFilters.isEmpty {
                        Label("Did not pass: \(item.failedFilters.map(filterLabel).joined(separator: ", "))",
                              systemImage: "line.3.horizontal.decrease.circle")
                            .font(.caption).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    if !item.motifMapping.isEmpty {
                        DisclosureGroup("Motif correspondence") {
                            VStack(alignment: .leading, spacing: 6) {
                                Text("Source residues are matched to their actual positions in the generated chain. RMSD values use the same global fit of the explicitly constrained motif atoms.")
                                    .font(.caption2).foregroundStyle(.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                                ForEach(item.motifMapping.keys.sorted(), id: \.self) { source in
                                    HStack {
                                        Text(source).font(.caption.monospaced().weight(.semibold))
                                        Image(systemName: "arrow.right").font(.caption2).foregroundStyle(.secondary)
                                        Text(item.motifMapping[source] ?? "—").font(.caption.monospaced())
                                        Spacer()
                                        if let value = item.motifResidueRMSDs[source] {
                                            Text(String(format: "%.2f Å", value))
                                                .font(.caption.monospacedDigit())
                                                .foregroundStyle(.secondary)
                                        }
                                    }
                                }
                            }
                            .padding(.top, 6)
                        }
                        .font(.callout)
                    }

                    if let sequence = item.sequence, !sequence.isEmpty {
                        DisclosureGroup("Sequence") {
                            HStack(alignment: .top) {
                                Text(sequence)
                                    .font(.system(.caption, design: .monospaced))
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                Button {
                                    NSPasteboard.general.clearContents()
                                    NSPasteboard.general.setString(sequence, forType: .string)
                                    sequenceCopied = true
                                } label: {
                                    Label(sequenceCopied ? "Copied" : "Copy", systemImage: sequenceCopied ? "checkmark" : "doc.on.doc")
                                }
                                .controlSize(.small)
                            }
                            .padding(.top, 6)
                        }
                        .font(.callout)
                    }
                }
                .padding(14)
            }
            .frame(maxHeight: 220)
            .background(.quaternary.opacity(0.18))
        }
    }

    private var detailHeader: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(item.title).font(.headline)
                Text(item.subtitle).font(.caption).foregroundStyle(.secondary)
                Label(provenanceLabel,
                      systemImage: "checkmark.seal")
                    .font(.caption2).foregroundStyle(.secondary)
            }
            Spacer()
            if let confidence = item.confidenceURL {
                Button {
                    NSWorkspace.shared.activateFileViewerSelecting([confidence])
                } label: {
                    Label("Confidence File", systemImage: "chart.bar.doc.horizontal")
                }
                .controlSize(.small)
            }
            Button {
                NSWorkspace.shared.activateFileViewerSelecting([item.structureURL])
            } label: {
                Label("Structure File", systemImage: "doc")
            }
            .controlSize(.small)
        }
        .padding(12)
    }

    private var shouldExplainMissingIPSAE: Bool {
        !item.metrics.contains { $0.kind == .ipsaeMinimum }
            && item.metrics.contains { [.iptm, .interfacePAEMinimum, .interfacePDE].contains($0.kind) }
    }

    private var provenanceLabel: String {
        if item.stage == .generatedBackbone {
            return "Generated by \(item.scoreSource) · \(item.stage.label)"
        }
        return "Predicted and scored by \(item.scoreSource) · \(item.stage.label)"
    }


    private func filterLabel(_ raw: String) -> String {
        raw.replacingOccurrences(of: "_unavailable", with: " unavailable")
            .replacingOccurrences(of: "_", with: " ")
    }
}

private struct MetricTile: View {
    let metric: StudioResultMetric

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(metric.displayValue)
                .font(.title3.bold()).monospacedDigit()
                .foregroundStyle(tint)
            Text(metric.kind.label).font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 9).fill(tint.opacity(0.10)))
        .help(metric.kind.explanation)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(metric.kind.label), \(metric.displayValue). \(metric.kind.explanation)")
    }

    private var tint: Color {
        switch metric.kind {
        case .plddt, .ptm, .binderPLDDT: return .blue
        case .iptm, .meanIPTM, .minimumIPTM: return .green
        case .ipsaeMinimum: return .teal
        case .interfacePAEMinimum, .interfacePDE, .pocketMeanDistance,
             .complexRMSD, .binderBackboneRMSD, .binderRMSD,
             .motifInsertionRMSD, .motifPredictionRMSD, .motifMaximumDrift: return .orange
        case .pocketFractionWithinCutoff: return .indigo
        case .bindingProbability: return .purple
        case .backboneCAValidity: return .cyan
        case .rankingScore: return .secondary
        }
    }
}
