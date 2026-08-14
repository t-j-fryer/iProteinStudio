import SwiftUI
import AppKit

enum DashTab: String, CaseIterable, Identifiable {
    case overview = "Overview"
    case structures = "Structures"
    case hits = "Hits"
    var id: String { rawValue }
}

/// Live campaign dashboard with three tabs: Overview (status + chart + log),
/// Structures (live grid by run × cycle), and Hits (design vs validation).
struct LiveDashboardView: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var smilesThumbnails: SmilesThumbnailStore
    let project: Project
    @ObservedObject var run: RunController
    @ObservedObject var metrics: MetricsWatcher
    @State private var tab: DashTab = .overview
    @State private var showResults = false

    private var ligandSmiles: String? {
        let r = project.request
        let s = r.targetSmiles.trimmingCharacters(in: .whitespaces)
        return (r.targetKind == .ligand && !s.isEmpty) ? s : nil
    }

    private var threshold: Double { app.selectedProject?.request.hitThreshold ?? 0.7 }
    private var designPoints: [DesignPoint] { metrics.designPoints }
    private var designHits: [DesignPoint] { designPoints.filter { $0.isHit(threshold: threshold) } }
    private var validationHits: [DesignPoint] { metrics.validationPoints.filter { $0.isHit(threshold: threshold) } }
    private var bestIPTM: Double { designPoints.map(\.iptm).max() ?? 0 }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header
            statTiles
            Picker("", selection: $tab) {
                ForEach(DashTab.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(maxWidth: 360)
            .accessibilityLabel("Dashboard section")

            switch tab {
            case .overview:   overviewTab
            case .structures: StructuresGridView(metrics: metrics, threshold: threshold)
            case .hits:       HitsGalleryView(designHits: designHits, validationHits: validationHits, threshold: threshold)
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .onReceive(run.$phase) { _ in if case .finished = run.phase { metrics.refresh() } }
        .sheet(isPresented: $showResults) {
            if let root = run.campaignRoot {
                RunResultsView(root: root, workflow: .iterative)
            }
        }
    }

    private var overviewTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if case .failed(let message) = run.phase {
                    ActionableErrorCard(title: "Design run needs attention", message: message,
                                        retryTitle: "Retry from checkpoints", retry: run.retry,
                                        output: run.campaignRoot, log: run.log)
                }
                Card(title: "Design iPTM by cycle", systemImage: "chart.xyaxis.line") {
                    MetricsChartsView(points: designPoints, threshold: threshold)
                }
                if case .failed = run.phase { EmptyView() }
                else {
                    Card(title: "Activity log", systemImage: "text.alignleft") {
                        TechnicalLogDisclosure(lines: run.log)
                    }
                }
            }
        }
    }

    private var header: some View {
        HStack(alignment: .center) {
            if let smiles = ligandSmiles {
                SmilesThumbnail(store: smilesThumbnails, smiles: smiles, cornerRadius: 8)
                    .frame(width: 72, height: 54)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(project.name).font(.title.bold())
                statusLabel
            }
            Spacer()
            HStack(spacing: 10) {
                if !run.isRunning, run.campaignRoot != nil {
                    Button { showResults = true } label: {
                        Label("Browse Results", systemImage: "cube.transparent")
                    }
                    .buttonStyle(.borderedProminent)
                    .accessibilityIdentifier("view-design-results")
                }
                Button {
                    if let root = run.campaignRoot { NSWorkspace.shared.activateFileViewerSelecting([root]) }
                } label: { Label("Reveal Output", systemImage: "folder") }
                if run.isRunning {
                    Button(role: .destructive) { run.cancel() } label: { Label("Stop", systemImage: "stop.fill") }
                        .buttonStyle(.borderedProminent)
                } else {
                    Button { metrics.stop(); run.reset() } label: { Label("New Run", systemImage: "arrow.uturn.backward") }
                }
            }
        }
    }

    @ViewBuilder private var statusLabel: some View {
        switch run.phase {
        case .running:      Label("Running…", systemImage: "circle.fill").foregroundStyle(.green).font(.subheadline)
        case .finished:     Label("Finished", systemImage: "checkmark.circle.fill").foregroundStyle(.blue).font(.subheadline)
        case .failed(_):    Label("Needs attention", systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange).font(.subheadline)
        case .cancelled:    Label("Stopped", systemImage: "stop.circle").foregroundStyle(.secondary).font(.subheadline)
        case .idle:         Text("Idle").font(.subheadline).foregroundStyle(.secondary)
        }
    }

    private var statTiles: some View {
        HStack(spacing: 12) {
            StatTile(title: "Designs", value: "\(designPoints.count)", systemImage: "square.stack.3d.up", tint: .blue)
            StatTile(title: "Design hits", value: "\(designHits.count)", systemImage: "trophy", tint: .green)
            StatTile(title: "Validation hits", value: "\(validationHits.count)", systemImage: "checkmark.seal", tint: .teal)
            StatTile(title: "Best iPTM", value: bestIPTM > 0 ? String(format: "%.3f", bestIPTM) : "—", systemImage: "star", tint: .yellow)
        }
    }
}

struct StatTile: View {
    let title: String; let value: String; let systemImage: String; let tint: Color
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: systemImage).font(.title2).foregroundStyle(tint)
                .frame(width: 40, height: 40).background(Circle().fill(tint.opacity(0.15)))
            VStack(alignment: .leading, spacing: 1) {
                Text(value).font(.title2.bold()).monospacedDigit()
                Text(title).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(14).frame(maxWidth: .infinity)
        .background(RoundedRectangle(cornerRadius: 12).fill(.quaternary.opacity(0.4)))
    }
}

struct LogView: View {
    let lines: [String]
    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 1) {
                    ForEach(Array(lines.enumerated()), id: \.offset) { i, line in
                        Text(line).font(.system(.caption2, design: .monospaced))
                            .foregroundStyle(.secondary).textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading).id(i)
                    }
                }
                .padding(8)
            }
            .frame(height: 160)
            .background(RoundedRectangle(cornerRadius: 8).fill(.black.opacity(0.05)))
            .onChange(of: lines.count) { _, n in withAnimation { proxy.scrollTo(n - 1, anchor: .bottom) } }
        }
    }
}
