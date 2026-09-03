import SwiftUI
import AppKit

/// The shared results surface used by both the live dashboard and the detached
/// Browse Results window. It groups files by scientific design instead of
/// presenting each prediction as an unrelated row.
struct GroupedRunResultsBrowser: View {
    let items: [StudioResultItem]
    var hitsOnly = false
    @State private var selectedGroupID: String?

    private var groups: [StudioResultGroup] {
        let all = RunResultsLoader.groups(from: items)
        return hitsOnly ? all.filter { $0.isHit == true } : all
    }

    var body: some View {
        Group {
            if groups.isEmpty {
                ContentUnavailableView(
                    hitsOnly ? "No saved hits yet" : "Waiting for structures",
                    systemImage: hitsOnly ? "line.3.horizontal.decrease.circle" : "cube.transparent",
                    description: Text(hitsOnly
                        ? "A design appears here only after an independent check passes every saved filter."
                        : "Design structures and their independent checks appear here as durable checkpoints are written.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                HSplitView {
                    List(selection: $selectedGroupID) {
                        ForEach(groups) { group in
                            StudioResultGroupRow(group: group).tag(group.id)
                        }
                    }
                    .listStyle(.sidebar)
                    .frame(minWidth: 230, idealWidth: 270, maxWidth: 330)
                    .accessibilityLabel(hitsOnly ? "Hit designs" : "Design results")

                    if let selectedGroup {
                        StudioResultGroupDetail(group: selectedGroup)
                            .id(selectedGroup.id)
                            .frame(minWidth: 620, maxWidth: .infinity, maxHeight: .infinity)
                    }
                }
            }
        }
        .onAppear { repairSelection() }
        .onChange(of: groups.map(\.id)) { _, _ in repairSelection() }
    }

    private var selectedGroup: StudioResultGroup? {
        groups.first { $0.id == selectedGroupID } ?? groups.first
    }

    private func repairSelection() {
        if !groups.contains(where: { $0.id == selectedGroupID }) {
            selectedGroupID = groups.first?.id
        }
    }
}

/// Polling wrapper for a live campaign. The detached results window and these
/// embedded dashboard tabs therefore use the same loader, grouping and verdict.
struct LiveGroupedRunResultsPane: View {
    let root: URL
    let workflow: StudioWorkflow
    var hitsOnly = false
    @State private var items: [StudioResultItem]

    init(root: URL, workflow: StudioWorkflow, hitsOnly: Bool = false) {
        self.root = root
        self.workflow = workflow
        self.hitsOnly = hitsOnly
        _items = State(initialValue: RunResultsLoader.load(root: root, workflow: workflow))
    }

    var body: some View {
        GroupedRunResultsBrowser(items: items, hitsOnly: hitsOnly)
            .task(id: root.path) {
                while !Task.isCancelled {
                    items = RunResultsLoader.load(root: root, workflow: workflow)
                    try? await Task.sleep(nanoseconds: 2_000_000_000)
                }
            }
    }
}

private struct StudioResultGroupRow: View {
    let group: StudioResultGroup

    var body: some View {
        HStack(spacing: 9) {
            Image(systemName: "square.stack.3d.up.fill")
                .foregroundStyle(.tint).frame(width: 20)
            VStack(alignment: .leading, spacing: 3) {
                Text(group.title).font(.callout.weight(.semibold)).lineLimit(1)
                Text("\(group.items.count) related structure\(group.items.count == 1 ? "" : "s")")
                    .font(.caption2).foregroundStyle(.secondary)
                HStack(spacing: 8) {
                    if let iptm = group.metric(.iptm) {
                        Text("iPTM \(iptm.displayValue)")
                    }
                    if let ipsae = group.metric(.ipsaeMinimum) {
                        Text("ipSAE \(ipsae.displayValue)").foregroundStyle(.teal)
                    }
                }
                .font(.caption2.monospacedDigit())
            }
            Spacer(minLength: 3)
            if let verdict = group.isHit {
                Image(systemName: verdict ? "checkmark.seal.fill" : "xmark.circle")
                    .foregroundStyle(verdict ? .green : .secondary)
                    .help(verdict ? "Passed every saved filter" : "Did not pass every saved filter")
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }
}

private struct StudioResultGroupDetail: View {
    let group: StudioResultGroup
    @State private var sequenceCopied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider()
            ScrollView(.vertical) {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Structures and scores")
                        .font(.headline)
                    Text("Generated/design coordinates, independent complex repredictions and binder-alone folds are kept together for direct comparison.")
                        .font(.caption).foregroundStyle(.secondary)

                    ScrollView(.horizontal, showsIndicators: true) {
                        LazyHStack(alignment: .top, spacing: 12) {
                            ForEach(group.sortedItems) { item in
                                StudioResultArtifactCard(item: item)
                                    .frame(width: 320)
                            }
                        }
                        .padding(.bottom, 5)
                    }

                    if group.isHit == false, !group.failedFilters.isEmpty {
                        Label("Did not pass: \(group.failedFilters.map(filterLabel).joined(separator: ", "))",
                              systemImage: "line.3.horizontal.decrease.circle")
                            .font(.caption).foregroundStyle(.secondary)
                    }

                    if let motifItem = group.items.first(where: { !$0.motifMapping.isEmpty }) {
                        MotifMappingSummary(item: motifItem)
                    }

                    if let sequence = group.sequence, !sequence.isEmpty {
                        DisclosureGroup("Designed binder sequence") {
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
                                    Label(sequenceCopied ? "Copied" : "Copy",
                                          systemImage: sequenceCopied ? "checkmark" : "doc.on.doc")
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
        }
    }

    private var header: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(group.title).font(.headline)
                Text("One design · \(group.items.count) related artifact\(group.items.count == 1 ? "" : "s")")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            if let verdict = group.isHit {
                Label(verdict ? "Hit — all filters passed" : "Did not pass all filters",
                      systemImage: verdict ? "checkmark.seal.fill" : "xmark.circle")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(verdict ? .green : .secondary)
            }
        }
        .padding(12)
    }

    private func filterLabel(_ raw: String) -> String {
        raw.replacingOccurrences(of: "_unavailable", with: " unavailable")
            .replacingOccurrences(of: "_", with: " ")
    }
}

private struct StudioResultArtifactCard: View {
    let item: StudioResultItem
    private let columns = [GridItem(.flexible()), GridItem(.flexible())]

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            VStack(alignment: .leading, spacing: 2) {
                Text(item.artifactRole.label).font(.headline)
                Text(item.subtitle).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
                Text(provenanceLabel).font(.caption2).foregroundStyle(.secondary)
            }
            StructureViewer(structurePath: item.structureURL.path)
                .frame(height: 250)
                .background(RoundedRectangle(cornerRadius: 8).fill(.black.opacity(0.025)))
                .clipShape(RoundedRectangle(cornerRadius: 8))

            if item.metrics.isEmpty {
                Text("No supported score was emitted for this artifact.")
                    .font(.caption2).foregroundStyle(.secondary)
                    .frame(minHeight: 45, alignment: .topLeading)
            } else {
                LazyVGrid(columns: columns, alignment: .leading, spacing: 6) {
                    ForEach(item.metrics) { metric in
                        VStack(alignment: .leading, spacing: 1) {
                            Text(metric.displayValue).font(.callout.bold()).monospacedDigit()
                            Text(metric.kind.label).font(.caption2).foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(7)
                        .background(RoundedRectangle(cornerRadius: 7).fill(.quaternary.opacity(0.28)))
                        .help(metric.kind.explanation)
                    }
                }
            }

            HStack {
                Button {
                    NSWorkspace.shared.activateFileViewerSelecting([item.structureURL])
                } label: { Label("Structure", systemImage: "doc") }
                if let confidence = item.confidenceURL {
                    Button {
                        NSWorkspace.shared.activateFileViewerSelecting([confidence])
                    } label: { Label("Scores", systemImage: "chart.bar.doc.horizontal") }
                }
            }
            .controlSize(.small)
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 11).fill(.quaternary.opacity(0.18)))
        .overlay(RoundedRectangle(cornerRadius: 11).stroke(.quaternary))
    }

    private var provenanceLabel: String {
        item.artifactRole == .generatedBackbone
            ? "Generated by \(item.scoreSource)"
            : "Scored by \(item.scoreSource)"
    }
}

private struct MotifMappingSummary: View {
    let item: StudioResultItem

    var body: some View {
        DisclosureGroup("Motif correspondence") {
            VStack(alignment: .leading, spacing: 6) {
                ForEach(item.motifMapping.keys.sorted(), id: \.self) { source in
                    HStack {
                        Text(source).font(.caption.monospaced().weight(.semibold))
                        Image(systemName: "arrow.right").font(.caption2).foregroundStyle(.secondary)
                        Text(item.motifMapping[source] ?? "—").font(.caption.monospaced())
                        Spacer()
                        if let value = item.motifResidueRMSDs[source] {
                            Text(String(format: "%.2f Å", value))
                                .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .padding(.top, 6)
        }
        .font(.callout)
    }
}
