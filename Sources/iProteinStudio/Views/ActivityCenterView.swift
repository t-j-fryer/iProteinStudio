import SwiftUI
import AppKit

/// One place to answer “what is my Mac doing?” across every project and model.
/// Durable history comes from disk; live controller state is layered on top so
/// an active job never disappears merely because the user changes tabs.
struct ActivityCenterView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var run: RunController
    @ObservedObject var rfd3: RFD3Controller
    @ObservedObject var prediction: PredictionController
    @ObservedObject var history: RunHistoryStore
    let projectFilter: Project.ID?
    @State private var selectedResults: StudioRunRecord?

    private let refreshTimer = Timer.publish(every: 5, on: .main, in: .common).autoconnect()

    private var records: [StudioRunRecord] {
        let all = projectFilter.map { id in history.runs.filter { $0.projectID == id } } ?? history.runs
        return Array(all.prefix(30))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label(projectFilter == nil ? "Activity" : "Run history", systemImage: "clock.arrow.circlepath")
                    .font(.title3.bold())
                Spacer()
                Button { refresh() } label: { Image(systemName: "arrow.clockwise") }
                    .buttonStyle(.plain)
                    .help("Refresh activity and results")
                    .accessibilityLabel("Refresh activity")
            }

            if projectFilter == nil, hasLiveActivity {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Running now").font(.headline)
                    if run.isRunning {
                        liveRow(title: "Iterative design", message: "Design campaign is running",
                                image: "arrow.triangle.2.circlepath", stop: run.cancel)
                    }
                    if rfd3.isRunning {
                        liveRow(title: "RFdiffusion3", message: rfd3.currentMessage,
                                image: "sparkles", stop: rfd3.cancel)
                    }
                    if prediction.isRunning {
                        liveRow(title: "Prediction", message: prediction.currentMessage,
                                image: "cube.transparent", stop: prediction.cancel)
                    }
                }
                Divider()
            }

            Text("Recent runs").font(.headline)
            if records.isEmpty {
                ContentUnavailableView("No runs yet", systemImage: "tray",
                                       description: Text("Completed and interrupted work will appear here automatically."))
                    .frame(minHeight: 150)
            } else {
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(records) { record in runRow(record) }
                    }
                }
            }
        }
        .padding(16)
        .frame(width: 500, height: 520, alignment: .topLeading)
        .onAppear { refresh() }
        .onReceive(refreshTimer) { _ in refresh() }
        .sheet(item: $selectedResults) { record in
            RunResultsView(root: record.root, workflow: record.workflow,
                           title: "\(record.name) results")
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(projectFilter == nil ? "Global activity centre" : "Workspace run history")
    }

    private var hasLiveActivity: Bool { run.isRunning || rfd3.isRunning || prediction.isRunning }

    private func refresh() { history.refresh(projects: app.projects) }

    private func liveRow(title: String, message: String, image: String,
                         stop: @escaping () -> Void) -> some View {
        HStack(spacing: 10) {
            ProgressView().controlSize(.small)
            VStack(alignment: .leading, spacing: 2) {
                Label(title, systemImage: image).font(.callout.weight(.semibold))
                Text(message).font(.caption).foregroundStyle(.secondary).lineLimit(2)
            }
            Spacer()
            Button("Stop", role: .destructive, action: stop).controlSize(.small)
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color.accentColor.opacity(0.09)))
    }

    private func runRow(_ record: StudioRunRecord) -> some View {
        HStack(spacing: 10) {
            Image(systemName: record.state.systemImage)
                .foregroundStyle(tint(record.state)).frame(width: 24)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(record.name).font(.callout.weight(.semibold)).lineLimit(1)
                    Text(record.workflow.label).font(.caption2).foregroundStyle(.secondary)
                }
                if projectFilter == nil { Text(record.projectName).font(.caption).foregroundStyle(.secondary) }
                Text("\(record.state.label) · \(record.detail)")
                    .font(.caption).foregroundStyle(.secondary).lineLimit(2)
                Text(record.date, style: .relative).font(.caption2).foregroundStyle(.tertiary)
            }
            Spacer()
            if record.isResumable {
                Button("Resume") { resume(record) }
                    .controlSize(.small)
                    .disabled(hasLiveActivity)
                    .help(hasLiveActivity ? "Stop the active GPU job before resuming this run." : "Continue from completed checkpoints")
            }
            if record.hasViewableResults {
                Button { selectedResults = record } label: {
                    Label("View", systemImage: "cube.transparent")
                }
                .controlSize(.small)
                .help(record.state == .completed
                      ? "View structures and metrics"
                      : "View structures and metrics produced before this run stopped")
                .accessibilityLabel("View results for \(record.name)")
            }
            Button { NSWorkspace.shared.activateFileViewerSelecting([record.root]) } label: {
                Image(systemName: "folder")
            }
            .buttonStyle(.plain)
            .help("Reveal results")
            .accessibilityLabel("Reveal results for \(record.name)")
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 10).fill(.quaternary.opacity(0.35)))
        .accessibilityElement(children: .contain)
        .accessibilityLabel("\(record.workflow.label), \(record.name), \(record.state.label), \(record.detail)")
    }

    private func resume(_ record: StudioRunRecord) {
        app.selectedProjectID = record.projectID
        app.run.resume(record)
        refresh()
    }

    private func tint(_ state: StudioRunState) -> Color {
        switch state {
        case .running: return .green
        case .completed: return .blue
        case .failed: return .orange
        case .stopped: return .secondary
        case .interrupted: return .yellow
        }
    }
}
