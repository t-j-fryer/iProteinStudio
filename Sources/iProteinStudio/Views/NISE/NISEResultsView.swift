import SwiftUI
import AppKit

/// One phase/stage selection drives both the overview and the structure browser.
struct NISEResultsView: View {
    let root: URL
    let title: String
    var embedded = false
    @Environment(\.dismiss) private var dismiss
    @State private var snapshot = NISESnapshot()
    @State private var phase: NISEPhase = .preparation
    @State private var stageID = ""
    @State private var status = "all"
    @State private var search = ""
    @State private var showStructures = false
    @State private var loaded = false
    @State private var selectedMetric: StudioResultMetric.Kind = .ligandPLDDT
    @State private var updatedAt: Date?

    private var stages: [NISEStageProgress] { snapshot.stages.filter { $0.phase == phase } }
    private var records: [NISERecord] {
        snapshot.records.filter { record in
            guard record.phase == phase, stageID.isEmpty || record.stageID == stageID else { return false }
            switch status {
            case "pending": if record.geometryPassed != nil { return false }
            case "geometry": if record.geometryPassed != true { return false }
            case "rejected": if record.geometryPassed != false && record.eligible != false { return false }
            case "eligible": if record.eligible != true { return false }
            case "advanced": if record.advanced != true { return false }
            default: break
            }
            return search.isEmpty || (record.item.title + " " + record.item.groupTitle).localizedCaseInsensitiveContains(search)
        }
    }
    private var items: [StudioResultItem] {
        let visible = records.map(\.item)
        guard phase == .finalChecks else { return visible }
        // Pair each apo result with its exact holo candidate without counting it
        // twice in either phase's progress or distributions.
        let names = Set(visible.map { $0.id.replacingOccurrences(of: "|apo", with: "|holo") })
        return visible + snapshot.items.filter { names.contains($0.id) }
    }
    private var metricKinds: [StudioResultMetric.Kind] {
        let recorded = Set(records.flatMap { $0.item.metrics.map(\.kind) })
        return StudioResultMetric.Kind.allCases.filter { recorded.contains($0) }
    }
    private var metric: StudioResultMetric.Kind? {
        metricKinds.contains(selectedMetric) ? selectedMetric : metricKinds.first
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            VStack(alignment: .leading, spacing: 10) {
                Picker("NISE phase", selection: $phase) {
                    ForEach(NISEPhase.allCases) { phase in
                        Text(phase.label).tag(phase)
                    }
                }.pickerStyle(.segmented)
                Text(phase.explanation).font(.caption).foregroundStyle(.secondary)
                HStack {
                    Picker("Stage", selection: $stageID) {
                        Text("All stages").tag("")
                        ForEach(stages) { Text($0.title).tag($0.id) }
                    }.frame(maxWidth: 320)
                    Picker("Checks", selection: $status) {
                        Text("All candidates").tag("all")
                        if phase != .finalChecks {
                            Text("Awaiting geometry checks").tag("pending")
                            Text("Geometry passed").tag("geometry")
                            Text("Eligible after checks").tag("eligible")
                            Text("Did not pass selection").tag("rejected")
                            if phase == .optimisation { Text("Selected for next cycle").tag("advanced") }
                        }
                    }.frame(maxWidth: 280)
                    TextField(phase == .preparation ? "Find lineage or candidate" : "Find trajectory or candidate", text: $search)
                        .textFieldStyle(.roundedBorder)
                    if status != "all" || !search.isEmpty {
                        Button("Clear filters") { status = "all"; search = "" }
                    }
                }
                Picker("Results section", selection: $showStructures) {
                    Text("Overview").tag(false)
                    Text("Structures (\(records.count))").tag(true)
                }.pickerStyle(.segmented)
            }.padding(14)
            Divider()
            if !snapshot.warnings.isEmpty {
                Text(snapshot.warnings.joined(separator: "\n")).font(.caption).foregroundStyle(.orange).padding(10)
            }
            if showStructures {
                if items.isEmpty { emptyState }
                else { GroupedRunResultsBrowser(items: items) }
            } else { overview }
        }
        .frame(minWidth: 900, idealWidth: 1150, minHeight: 650, idealHeight: 820)
        .accessibilityIdentifier("nise-results-browser")
        .onChange(of: phase) { _, _ in
            stageID = stages.last(where: { $0.completed > 0 })?.id ?? stages.first?.id ?? ""
            status = "all"; search = ""
        }
        .task(id: root.path) {
            while !Task.isCancelled {
                let next = await ResultsRepository.shared.niseSnapshot(root: root)
                guard !Task.isCancelled else { return }
                snapshot = next; updatedAt = Date()
                if !loaded {
                    loaded = true
                    phase = next.records.contains { $0.phase == .optimisation } ? .optimisation : .preparation
                    stageID = stages.last(where: { $0.completed > 0 })?.id ?? stages.first?.id ?? ""
                }
                try? await Task.sleep(nanoseconds: 5_000_000_000)
            }
        }
    }

    private var header: some View {
        HStack(spacing: 12) {
            Image(systemName: "point.3.connected.trianglepath.dotted").font(.title2).foregroundStyle(.tint)
            VStack(alignment: .leading) {
                Text(title).font(.headline)
                Text("Completed structures appear during each stage; checks and selection follow when recorded.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Button("Reveal Run", systemImage: "folder") { NSWorkspace.shared.activateFileViewerSelecting([root]) }
            if !embedded { Button("Done") { dismiss() }.keyboardShortcut(.defaultAction) }
        }.padding(14)
    }

    private var overview: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Stage progress").font(.headline)
                Text("Counts below cover the whole phase. The filters above apply to the score distribution and structure browser.")
                    .font(.caption).foregroundStyle(.secondary)
                ForEach(stages) { stage in
                    Button {
                        stageID = stage.id
                    } label: {
                        stageRow(stage)
                    }.buttonStyle(.plain)
                }
                if stages.isEmpty { emptyState }
                Divider()
                HStack {
                    Text("\(records.count) candidates in this view").font(.headline)
                    Spacer()
                    Button("Browse structures", systemImage: "cube.transparent") { showStructures = true }
                        .disabled(items.isEmpty)
                }
                if let metric {
                    HStack {
                        Text("Score distribution").font(.headline)
                        Spacer()
                        Picker("Metric", selection: Binding(get: { metric }, set: { selectedMetric = $0 })) {
                            ForEach(metricKinds, id: \.self) { Text($0.label).tag($0) }
                        }.frame(width: 260)
                    }
                    Text(metric.explanation).font(.caption).foregroundStyle(.secondary)
                    Text("Only recorded values are included. Missing scores are not zero; geometry-only stages may omit affinity. Choose one stage for like-for-like comparisons.")
                        .font(.caption).foregroundStyle(.secondary)
                    MetricDistributionChart(kind: metric, values: records.compactMap { record in
                        record.item.metrics.first { $0.kind == metric }?.value
                    }).frame(height: 240)
                } else if !records.isEmpty {
                    Text("These structures do not yet have scores for a distribution. They can still be inspected in Structures.")
                        .foregroundStyle(.secondary)
                }
                if let updatedAt {
                    Text("Last refreshed \(updatedAt.formatted(date: .omitted, time: .standard)) · updates every five seconds")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }.padding(18)
        }
    }

    private func stageRow(_ stage: NISEStageProgress) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(stage.title).font(.callout.weight(.semibold))
                Spacer()
                Text(stage.progressLabel).monospacedDigit()
                Image(systemName: "chevron.right").font(.caption)
            }
            if let total = stage.planned, total > 0 {
                ProgressView(value: Double(stage.completed), total: Double(max(total, stage.completed)))
            }
            if stage.completed > 0, stage.phase != .finalChecks {
                Text("\(stage.geometryPassed) geometry passed · \(stage.geometryFailed) geometry failed · \(stage.awaitingChecks) awaiting checks")
                    .font(.caption).foregroundStyle(.secondary)
                Text("\(stage.eligible) eligible after recorded checks" + (stage.phase == .optimisation ? " · \(stage.selected) selected for next cycle" : ""))
                    .font(.caption).foregroundStyle(.secondary)
            }
            if stage.screened > 0 {
                Text("NESSO: \(stage.screened) sequences screened · \(stage.shortlisted) shortlisted for folding")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 10).fill(stageID == stage.id ? Color.accentColor.opacity(0.10) : Color.secondary.opacity(0.06)))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(stageID == stage.id ? Color.accentColor : .clear))
        .contentShape(Rectangle())
        .accessibilityLabel("\(stage.title), \(stage.progressLabel). Select stage")
    }

    private var emptyState: some View {
        ContentUnavailableView(loaded ? "No structures in this selection yet" : "Loading saved progress",
            systemImage: "cube.transparent",
            description: Text(phase == .preparation
                ? "Completed backbone and folding checkpoints will appear here. Try another stage or clear the filters to see earlier work."
                : (phase == .optimisation
                    ? "Optimisation structures appear after Phase 0 selects its starting seeds. Earlier structures remain in Phase 0."
                    : "Apo structures appear after the final shortlist has been checked. Phase 0 and Phase 1 remain available.")))
            .frame(maxWidth: .infinity, minHeight: 200)
    }
}
