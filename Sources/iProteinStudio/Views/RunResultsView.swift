import SwiftUI
import AppKit

/// One in-app home for successful structures from all three workflows.
/// The loader normalises only the presentation layer; original files remain the
/// source of truth and are always one click away.
struct RunResultsView: View {
    let root: URL
    let workflow: StudioWorkflow
    let title: String

    @Environment(\.dismiss) private var dismiss
    @State private var items: [StudioResultItem]
    @State private var selectedID: String?

    init(root: URL, workflow: StudioWorkflow, title: String? = nil) {
        self.root = root
        self.workflow = workflow
        self.title = title ?? "\(workflow.label) results"
        let loaded = RunResultsLoader.load(root: root, workflow: workflow)
        _items = State(initialValue: loaded)
        _selectedID = State(initialValue: loaded.first?.id)
    }

    private var selection: StudioResultItem? {
        items.first { $0.id == selectedID } ?? items.first
    }

    private var iterativeHitSummary: String? {
        guard workflow == .iterative, !items.isEmpty else { return nil }
        let threshold = RunResultsLoader.iterativeHitThreshold(root: root)
        func passes(_ item: StudioResultItem) -> Bool {
            item.metrics.first { $0.kind == .iptm }.map { $0.value >= threshold } ?? false
        }
        let design = items.filter { $0.stage == .design && passes($0) }.count
        let checked = items.filter { $0.stage == .postPrediction && passes($0) }.count
        return "\(design) design-stage hit\(design == 1 ? "" : "s") · \(checked) post-check hit\(checked == 1 ? "" : "s") at iPTM ≥ \(String(format: "%.2f", threshold))"
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if items.isEmpty {
                ContentUnavailableView(
                    "No viewable structures found",
                    systemImage: "cube.transparent",
                    description: Text("This run has no successful CIF or PDB output yet. Its folder and logs are still available.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                HSplitView {
                    resultsList.frame(minWidth: 240, idealWidth: 275, maxWidth: 340)
                    if let selection {
                        RunResultDetail(item: selection)
                            .id(selection.id)
                            .frame(minWidth: 620, maxWidth: .infinity, maxHeight: .infinity)
                    }
                }
            }
        }
        .frame(minWidth: 920, idealWidth: 1060, minHeight: 650, idealHeight: 760)
        .accessibilityIdentifier("run-results-browser")
    }

    private var header: some View {
        HStack(spacing: 12) {
            Image(systemName: workflow.systemImage)
                .font(.title2).foregroundStyle(.tint)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.headline)
                Text("\(items.count) viewable structure\(items.count == 1 ? "" : "s")")
                    .font(.caption).foregroundStyle(.secondary)
                if let iterativeHitSummary {
                    Text(iterativeHitSummary).font(.caption2).foregroundStyle(.secondary)
                }
            }
            Spacer()
            Button {
                NSWorkspace.shared.activateFileViewerSelecting([root])
            } label: {
                Label("Reveal Run", systemImage: "folder")
            }
            Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
        }
        .padding(14)
    }

    private var resultsList: some View {
        List(selection: $selectedID) {
            ForEach(items) { item in
                RunResultRow(item: item).tag(item.id)
            }
        }
        .listStyle(.sidebar)
        .accessibilityLabel("Structures in this run")
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
                Label("Scores reported by \(item.scoreSource) · \(item.stage.label)",
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
        case .plddt, .ptm: return .blue
        case .iptm, .meanIPTM, .minimumIPTM: return .green
        case .ipsaeMinimum: return .teal
        case .interfacePAEMinimum, .interfacePDE, .pocketMeanDistance: return .orange
        case .pocketFractionWithinCutoff: return .indigo
        case .bindingProbability: return .purple
        case .rankingScore: return .secondary
        }
    }
}
