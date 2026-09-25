import SwiftUI
import AppKit
import Combine

/// One place to answer “what is my Mac doing?” across every project and model.
/// Durable history comes from disk; live controller state is layered on top so
/// an active job never disappears merely because the user changes tabs.
struct ActivityCenterView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject private var jobs = JobCenter.shared
    @Environment(\.openWindow) private var openWindow
    @ObservedObject var run: RunController
    @ObservedObject var rfd3: RFD3Controller
    @ObservedObject var prediction: PredictionController
    @ObservedObject var history: RunHistoryStore
    let projectFilter: Project.ID?
    @State private var progressJob: ManagedJob?

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

            if let error = jobs.operationError ?? jobs.error {
                Label(error, systemImage: "exclamationmark.triangle")
                    .font(.caption).foregroundStyle(.orange)
            }
            if !visibleJobs.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Active and queued work").font(.headline)
                    ForEach(visibleJobs) { job in
                        VStack(alignment: .leading, spacing: 4) {
                            liveRow(title: job.display_name ?? job.project, message: job.message ?? job.status,
                                    image: "waveform.path", stop: { jobs.cancel(job) })
                                .disabled(job.status == "stopping")
                            Button("Progress & logs") { progressJob = job }.controlSize(.small)
                        }
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
        .sheet(item: $progressJob) { job in JobProgressView(job: job) }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(projectFilter == nil ? "Global activity centre" : "Workspace run history")
    }

    private var visibleJobs: [ManagedJob] {
        jobs.active.filter { job in
            projectFilter == nil || app.projects.first(where: { $0.slug == job.project })?.id == projectFilter
        }
    }
    private func canResume(_ record: StudioRunRecord) -> Bool {
        if jobs.active.contains(where: { $0.id == record.managedJobID }) { return false }
        if isEngineBatch(record) || record.managedJobID == nil { return run.canStartAnother }
        if record.workflow == .nise { return app.nise.canStartAnother }
        return true
    }

    private func refresh() { Task { await jobs.refresh(); history.refresh(projects: app.projects) } }

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
            if let id = record.managedJobID {
                Button("Logs") {
                    Task {
                        do { progressJob = try await BrokerClient.call(["job-status", id], as: ManagedJob.self) }
                        catch { jobs.reportOperationError(error.localizedDescription) }
                    }
                }.controlSize(.small)
            }
            if record.isResumable {
                Button(isEngineBatch(record) ? "Resume batch" : "Resume") { resume(record) }
                    .controlSize(.small)
                    .disabled(!canResume(record))
                    .help("Resume from saved checkpoints. If other work is active, this job waits in the queue.")
            }
            if record.hasViewableResults {
                Button {
                    openWindow(value: RunResultsWindowRequest(
                        root: record.root, workflow: record.workflow,
                        title: "\(record.name) results"))
                } label: {
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

    private func isEngineBatch(_ record: StudioRunRecord) -> Bool {
        FileManager.default.fileExists(atPath: record.root.appendingPathComponent("studio_engine_batch.json").path)
            || jobs.jobs.contains { $0.id == record.managedJobID && $0.kind == "desktop_iterative_batch" }
    }

    private func resume(_ record: StudioRunRecord) {
        app.selectedProjectID = record.projectID
        if isEngineBatch(record) {
            guard app.run.prepareNewRun() else { return }
            app.updateSelected { $0.preferredMode = .iterative }
            app.run.resume(record)
        } else if record.workflow == .nise, let id = record.managedJobID {
            guard app.nise.prepareNewRun() else { return }
            app.updateSelected { $0.preferredMode = .nise }
            app.nise.reattach(root: record.root, jobID: id, resume: true)
        } else if let id = record.managedJobID, let job = jobs.jobs.first(where: { $0.id == id }) {
            jobs.resume(job)
        } else {
            guard app.run.prepareNewRun() else { return }
            app.run.resume(record)
            if let root = app.run.campaignRoot { app.metrics.start(root: root) }
        }
        refresh()
    }

    private func tint(_ state: StudioRunState) -> Color {
        switch state {
        case .prepared, .queued: return .secondary
        case .stopping: return .orange
        case .running: return .green
        case .completed: return .blue
        case .failed: return .orange
        case .stopped: return .secondary
        case .interrupted: return .yellow
        }
    }
}
