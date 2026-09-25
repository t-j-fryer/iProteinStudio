import SwiftUI

/// Global view of the broker registry, independent of the dashboard currently
/// being observed. Opening a job changes observation, never its saved settings.
struct JobQueueView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject private var jobs = JobCenter.shared
    @ObservedObject var run: RunController
    @ObservedObject var rfd3: RFD3Controller
    @ObservedObject var prediction: PredictionController
    @ObservedObject var nise: NISEController
    @State private var selectedJob: ManagedJob?
    private var recent: [ManagedJob] { Array(jobs.jobs.filter { !$0.isActive }.prefix(12)) }

    private var running: [ManagedJob] { jobs.active.filter { $0.status != "queued" } }
    private var waiting: [ManagedJob] {
        jobs.waiting.sorted { ($0.created_at ?? "", $0.id) < ($1.created_at ?? "", $1.id) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Job queue", systemImage: "list.bullet.rectangle").font(.title3.bold())
                Spacer()
                Button { Task { await jobs.refresh() } } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .help("Refresh queue")
                .accessibilityLabel("Refresh job queue")
            }
            Text("All workspaces share the GPU. Waiting jobs start automatically when the active job ends; a multi-engine batch keeps its place until the whole batch ends.")
                .font(.caption).foregroundStyle(.secondary)
            if let error = jobs.operationError ?? jobs.error {
                Label(error, systemImage: "exclamationmark.triangle")
                    .font(.caption).foregroundStyle(.orange)
            }
            if jobs.jobs.isEmpty {
                ContentUnavailableView("No active jobs", systemImage: "tray",
                    description: Text("Start a run from Protein Hunter, NISE, RFdiffusion3, or Predict. Further runs can be queued while work continues."))
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        if !running.isEmpty {
                            Text("Running").font(.headline)
                            ForEach(running) { row($0) }
                        }
                        if !waiting.isEmpty {
                            Text("Waiting · \(waiting.count)").font(.headline)
                            Text("Shown by submission time. Start order is not guaranteed.")
                                .font(.caption2).foregroundStyle(.secondary)
                            ForEach(waiting) { row($0) }
                        }
                        if !recent.isEmpty {
                            Text("Recent jobs").font(.headline)
                            ForEach(recent) { row($0) }
                        }
                    }
                }
            }
            Text("Closing Studio leaves submitted jobs running or waiting. Use Cancel or Stop to remove work.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(16)
        .frame(width: 580, height: 560)
        .task { jobs.start(); await jobs.refresh() }
        .sheet(item: $selectedJob) { job in JobProgressView(job: job) }
        .accessibilityIdentifier("job-queue-panel")
    }

    private func row(_ job: ManagedJob) -> some View {
        let project = app.projects.first { $0.slug == job.project }
        return VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: job.status == "queued" ? "hourglass" : "waveform.path")
                Text(project?.name ?? job.project).font(.callout.bold()).lineLimit(1)
                Spacer()
                Text(job.displayStatus).font(.caption)
            }
            Text(job.display_name ?? job.output?.lastPathComponent ?? job.id)
                .font(.caption).textSelection(.enabled).lineLimit(2)
            Text(job.workflowLabel).font(.caption).foregroundStyle(.secondary)
            if let label = job.engine_label {
                Text("\(label) · engine \(job.engine_index ?? 1) of \(job.engine_count ?? 1)")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if job.status != "queued", let message = job.message {
                Text(message).font(.caption).foregroundStyle(.secondary).lineLimit(2)
            }
            HStack {
                Button("Progress & logs") { selectedJob = job }
                if let project {
                    Button("Show run") { show(job, project: project) }
                    .disabled(!canShow(job))
                }
                if let root = job.output {
                    Button("Show files") { NSWorkspace.shared.activateFileViewerSelecting([root]) }
                }
                Spacer()
                if job.isActive {
                    Button(job.status == "queued" ? "Cancel" : "Stop", role: .destructive) {
                        jobs.cancel(job)
                    }
                    .disabled(job.status == "stopping")
                    .help(job.status == "queued" ? "Remove this waiting job without running it" : "Stop this job and keep completed checkpoints")
                }
            }
            .controlSize(.small)
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color.accentColor.opacity(0.07)))
        .accessibilityElement(children: .contain)
    }

    private func canShow(_ job: ManagedJob) -> Bool {
        if job.kind.contains("iterative") { return run.canStartAnother }
        if job.kind.contains("nise") { return nise.canStartAnother }
        if job.kind.contains("rfd3") || job.kind.contains("rfdiffusion3") { return rfd3.canStartAnother }
        if job.kind.contains("prediction") { return prediction.canStartAnother }
        return true
    }

    private func show(_ job: ManagedJob, project: Project) {
        guard let root = job.output, canShow(job) else { return }
        let mode: WorkspaceMode
        if job.kind.contains("iterative") {
            run.inspect(job, project: project); mode = .iterative
        } else if job.kind.contains("nise") {
            if nise.observedJobID != job.id, nise.prepareNewRun() {
                nise.reattach(root: root, jobID: job.id)
            }
            mode = .nise
        } else if job.kind.contains("rfd3") || job.kind.contains("rfdiffusion3") {
            if rfd3.observedJobID != job.id, rfd3.prepareNewRun() {
                rfd3.reattach(root: root, jobID: job.id)
            }
            mode = .rfdiffusion
        } else if job.kind.contains("prediction") {
            if prediction.observedJobID != job.id, prediction.prepareNewRun() {
                prediction.reattach(root: root, jobID: job.id)
            }
            mode = .predict
        } else { app.selectedProjectID = project.id; return }
        app.updateProject(id: project.id) { $0.preferredMode = mode }
        app.selectedProjectID = project.id
    }
}
