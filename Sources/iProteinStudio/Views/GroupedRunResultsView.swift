import SwiftUI
import AppKit

/// Shared browser for live and completed campaigns. The sidebar contains the
/// scientific parent (an RFD3 backbone or iterative run), while the detail
/// view nests MPNN derivatives or iterative cycles beneath it.
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
                        ? "A derivative or cycle appears here only after an independent check passes every saved filter."
                        : "Backbones, sequence derivatives and independent checks appear as durable checkpoints are written.")
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
                    .frame(minWidth: 220, idealWidth: 250, maxWidth: 300)
                    .accessibilityLabel(hitsOnly ? "Hit backbones and runs" : "Backbones and runs")

                    if let selectedGroup {
                        StudioResultGroupDetail(group: selectedGroup, hitsOnly: hitsOnly)
                            .id(selectedGroup.id + (hitsOnly ? "|hits" : "|all"))
                            .frame(minWidth: 720, maxWidth: .infinity, maxHeight: .infinity)
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

/// Polling wrapper used by embedded live Structures and Hits tabs.
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

    private var unitDescription: String {
        guard !group.variants.isEmpty else {
            return "\(group.items.count) structure\(group.items.count == 1 ? "" : "s")"
        }
        let noun = group.id.hasPrefix("rfd3|") ? "MPNN derivative" : "cycle"
        return "\(group.variants.count) \(noun)\(group.variants.count == 1 ? "" : "s")"
    }

    var body: some View {
        HStack(spacing: 9) {
            Image(systemName: group.id.hasPrefix("rfd3|") ? "cube.transparent.fill" : "arrow.triangle.2.circlepath")
                .foregroundStyle(.tint).frame(width: 20)
            VStack(alignment: .leading, spacing: 3) {
                Text(group.title).font(.callout.weight(.semibold)).lineLimit(1)
                Text(unitDescription).font(.caption2).foregroundStyle(.secondary)
                HStack(spacing: 8) {
                    if let iptm = group.metric(.iptm) { Text("iPTM \(iptm.displayValue)") }
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
                    .help(verdict ? "At least one child passed every saved filter" : "No child passed every saved filter")
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }
}

private struct StudioResultGroupDetail: View {
    let group: StudioResultGroup
    let hitsOnly: Bool
    @State private var selectedArtifactID: String?

    private var visibleVariants: [StudioResultVariant] {
        hitsOnly ? group.variants.filter { $0.isHit == true } : group.variants
    }

    private var visibleItems: [StudioResultItem] {
        group.primaryItems + visibleVariants.flatMap(\.sortedItems)
    }

    private var trajectoryFrames: [StructureTrajectoryFrame] {
        guard !hitsOnly else { return [] }
        return group.iterativeTrajectoryItems.map { item in
            StructureTrajectoryFrame(id: item.variantID ?? item.id,
                                     label: item.variantTitle ?? item.title,
                                     structurePath: item.structureURL.path)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider()
            ScrollView(.vertical) {
                LazyVStack(alignment: .leading, spacing: 18) {
                    if !visibleItems.isEmpty {
                        SelectedResultViewer(allItems: visibleItems,
                                             trajectoryFrames: trajectoryFrames,
                                             selection: $selectedArtifactID)
                    }

                    if !group.primaryItems.isEmpty {
                        ResultSectionHeader(
                            title: group.id.hasPrefix("rfd3|") ? "Source RFdiffusion3 backbone" : "Source structure",
                            detail: "The parent coordinates from which the sequence derivatives below were evaluated."
                        )
                        ArtifactComparisonGrid(items: group.primaryItems,
                                               selectedArtifactID: $selectedArtifactID)
                    }

                    ForEach(visibleVariants) { variant in
                        StudioResultVariantSection(variant: variant,
                                                   selectedArtifactID: $selectedArtifactID)
                    }
                }
                .padding(16)
            }
        }
        .onAppear { repairArtifactSelection() }
        .onChange(of: visibleItems.map(\.id)) { _, _ in repairArtifactSelection() }
    }

    private var header: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text(group.title).font(.title3.weight(.semibold))
                if !group.variants.isEmpty {
                    Text("\(group.variants.count) nested \(group.id.hasPrefix("rfd3|") ? "MPNN sequence derivative" : "design cycle")\(group.variants.count == 1 ? "" : "s") · \(group.items.count) structures")
                        .font(.caption).foregroundStyle(.secondary)
                } else {
                    Text("\(group.items.count) related structure\(group.items.count == 1 ? "" : "s")")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            Spacer()
            if hitsOnly {
                Label("Showing passing children", systemImage: "line.3.horizontal.decrease.circle.fill")
                    .font(.caption.weight(.semibold)).foregroundStyle(.green)
            } else if let verdict = group.isHit {
                Label(verdict ? "Contains a saved hit" : "No saved hit",
                      systemImage: verdict ? "checkmark.seal.fill" : "xmark.circle")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(verdict ? .green : .secondary)
            }
        }
        .padding(14)
    }

    private func repairArtifactSelection() {
        let trajectoryID = SelectedResultViewer.trajectoryID
        let trajectorySelected = selectedArtifactID == trajectoryID && trajectoryFrames.count > 1
        if !trajectorySelected && !visibleItems.contains(where: { $0.id == selectedArtifactID }) {
            selectedArtifactID = visibleItems.first?.id
        }
    }
}

private struct SelectedResultViewer: View {
    static let trajectoryID = "__target_aligned_iterative_trajectory__"
    let allItems: [StudioResultItem]
    let trajectoryFrames: [StructureTrajectoryFrame]
    @Binding var selection: String?

    private var item: StudioResultItem {
        allItems.first { $0.id == selection } ?? allItems[0]
    }

    private var showsTrajectory: Bool {
        trajectoryFrames.count > 1 && selection == Self.trajectoryID
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(showsTrajectory ? "Optimization trajectory" : "Selected structure")
                        .font(.headline)
                    Text(showsTrajectory
                         ? "Design-stage cycles · target-aligned on chains B onward"
                         : "\(item.artifactRole.label) · \(item.scoreSource)")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Picker("Displayed structure", selection: Binding(
                    get: { selection ?? item.id }, set: { selection = $0 }
                )) {
                    if trajectoryFrames.count > 1 {
                        Text("Trajectory · \(trajectoryFrames.first?.label ?? "start") → \(trajectoryFrames.last?.label ?? "final")")
                            .tag(Self.trajectoryID)
                        Divider()
                    }
                    ForEach(allItems) { candidate in
                        Text(pickerLabel(candidate)).tag(candidate.id)
                    }
                }
                .labelsHidden()
                .frame(maxWidth: 310)
            }

            Group {
                if showsTrajectory {
                    StructureTrajectoryViewer(frames: trajectoryFrames)
                } else {
                    StructureViewer(structurePath: item.structureURL.path)
                }
            }
                .frame(minHeight: 410, idealHeight: 470)
                .background(RoundedRectangle(cornerRadius: 10).fill(.black.opacity(0.025)))
                .clipShape(RoundedRectangle(cornerRadius: 10))

            HStack {
                Text(showsTrajectory
                     ? "Use the bottom slider or Play control to move through target-fitted cycles."
                     : item.subtitle)
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                if !showsTrajectory {
                    Button {
                        NSWorkspace.shared.activateFileViewerSelecting([item.structureURL])
                    } label: { Label("Reveal structure", systemImage: "doc") }
                    .controlSize(.small)
                }
            }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 12).fill(.quaternary.opacity(0.16)))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(.quaternary))
    }

    private func pickerLabel(_ candidate: StudioResultItem) -> String {
        let parent = candidate.variantTitle.map { "\($0) · " } ?? ""
        return parent + candidate.artifactRole.label + " · " + candidate.scoreSource
    }
}

private struct ResultSectionHeader: View {
    let title: String
    let detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.headline)
            Text(detail).font(.caption).foregroundStyle(.secondary)
        }
    }
}

private struct StudioResultVariantSection: View {
    let variant: StudioResultVariant
    @Binding var selectedArtifactID: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(variant.title).font(.headline)
                    Text("\(variant.items.count) paired result\(variant.items.count == 1 ? "" : "s")")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if let verdict = variant.isHit {
                    Label(verdict ? "Hit" : "Did not pass",
                          systemImage: verdict ? "checkmark.seal.fill" : "xmark.circle")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(verdict ? .green : .secondary)
                }
            }

            if let sequence = variant.sequence, !sequence.isEmpty {
                DisclosureGroup("Designed binder sequence") {
                    HStack(alignment: .top) {
                        Text(sequence)
                            .font(.system(.caption, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Button {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(sequence, forType: .string)
                        } label: { Label("Copy", systemImage: "doc.on.doc") }
                        .controlSize(.small)
                    }
                    .padding(.top, 6)
                }
                .font(.callout)
            }

            ArtifactComparisonGrid(items: variant.sortedItems,
                                   selectedArtifactID: $selectedArtifactID)

            if variant.isHit == false, !variant.failedFilters.isEmpty {
                Label("Did not pass: \(variant.failedFilters.map(filterLabel).joined(separator: ", "))",
                      systemImage: "line.3.horizontal.decrease.circle")
                    .font(.caption).foregroundStyle(.secondary)
            }

            if let motifItem = variant.items.first(where: { !$0.motifMapping.isEmpty }) {
                MotifMappingSummary(item: motifItem)
            }
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: 12).fill(.quaternary.opacity(0.12)))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(.quaternary))
    }

    private func filterLabel(_ raw: String) -> String {
        raw.replacingOccurrences(of: "_unavailable", with: " unavailable")
            .replacingOccurrences(of: "_", with: " ")
    }
}

private struct ArtifactComparisonGrid: View {
    let items: [StudioResultItem]
    @Binding var selectedArtifactID: String?

    private let columns = [
        GridItem(.adaptive(minimum: 265, maximum: 440), spacing: 12, alignment: .top)
    ]

    var body: some View {
        LazyVGrid(columns: columns, alignment: .leading, spacing: 12) {
            ForEach(items) { item in
                StudioResultArtifactSummaryCard(
                    item: item,
                    selected: selectedArtifactID == item.id,
                    select: { selectedArtifactID = item.id }
                )
            }
        }
    }
}

private struct StudioResultArtifactSummaryCard: View {
    let item: StudioResultItem
    let selected: Bool
    let select: () -> Void
    private let metricColumns = [GridItem(.flexible()), GridItem(.flexible())]

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.artifactRole.label).font(.callout.weight(.semibold))
                    Text(item.scoreSource).font(.caption2).foregroundStyle(.secondary)
                }
                Spacer()
                if selected {
                    Label("Selected", systemImage: "viewfinder")
                        .font(.caption2.weight(.semibold)).foregroundStyle(.tint)
                }
            }

            StructurePreview(structurePath: item.structureURL.path)
                .frame(height: 175)
                .background(RoundedRectangle(cornerRadius: 8).fill(.black.opacity(0.025)))
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .contentShape(Rectangle())
                .onTapGesture(perform: select)
                .help("Show this structure in the large interactive viewer")

            if item.metrics.isEmpty {
                Text("No supported score was emitted for this artifact.")
                    .font(.caption2).foregroundStyle(.secondary)
                    .frame(minHeight: 34, alignment: .topLeading)
            } else {
                LazyVGrid(columns: metricColumns, alignment: .leading, spacing: 6) {
                    ForEach(item.metrics) { metric in
                        VStack(alignment: .leading, spacing: 1) {
                            Text(metric.displayValue).font(.callout.bold()).monospacedDigit()
                            Text(metric.kind.label).font(.caption2).foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(6)
                        .background(RoundedRectangle(cornerRadius: 6).fill(.quaternary.opacity(0.25)))
                        .help(metric.kind.explanation)
                    }
                }
            }

            HStack {
                Button("View larger", action: select).controlSize(.small)
                Spacer()
                Button {
                    NSWorkspace.shared.activateFileViewerSelecting([item.structureURL])
                } label: { Image(systemName: "doc") }
                .buttonStyle(.borderless).help("Reveal structure file")
                if let confidence = item.confidenceURL {
                    Button {
                        NSWorkspace.shared.activateFileViewerSelecting([confidence])
                    } label: { Image(systemName: "chart.bar.doc.horizontal") }
                    .buttonStyle(.borderless).help("Reveal saved score file")
                }
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 10).fill(.background))
        .overlay(RoundedRectangle(cornerRadius: 10)
            .stroke(selected ? Color.accentColor : Color.secondary.opacity(0.22),
                    lineWidth: selected ? 2 : 1))
        .contentShape(RoundedRectangle(cornerRadius: 10))
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
