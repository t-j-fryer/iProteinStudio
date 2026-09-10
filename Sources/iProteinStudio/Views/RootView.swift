import SwiftUI

/// Top-level router: setup wizard until the pipeline is installed, then the
/// projects workspace. `app.installer` / `app.run` are nested observable
/// objects, so views that depend on them receive them as `@ObservedObject`.
struct RootView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        Group {
            if app.storageAvailable {
                RouterView(installer: app.installer)
            } else {
                ContentUnavailableView {
                    Label("Workspace recovery needed", systemImage: "externaldrive.badge.exclamationmark")
                } description: {
                    Text(app.storageMessage ?? "Your saved files have been kept. Editing is paused until the workspace index can be read.")
                } actions: {
                    Button("Try Reading Again") { app.reloadSavedWorkspaces() }
                    Button("Reveal Saved Files") { NSWorkspace.shared.activateFileViewerSelecting([AppPaths.support]) }
                }
            }
        }
            .modifier(ApplicationLocationNotice())
            .alert("Saved work needs attention", isPresented: Binding(
                get: { app.storageMessage != nil && app.storageAvailable },
                set: { if !$0 { app.storageMessage = nil } }
            )) {
                Button("OK") { app.storageMessage = nil }
            } message: { Text(app.storageMessage ?? "") }
    }
}

private struct RouterView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var installer: PipelineInstaller

    var body: some View {
        Group {
            if installer.installed {
                WorkspaceView(run: app.run, installer: installer)
            } else {
                SetupView()
            }
        }
        .onChange(of: installer.installed) { _, done in
            if done { app.reloadScaffoldsIfNeeded() }
        }
    }
}

struct WorkspaceView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var run: RunController
    @ObservedObject var installer: PipelineInstaller
    @State private var showComponents = false
    @State private var showActivity = false
    @State private var showQueue = false
    @ObservedObject private var jobs = JobCenter.shared
    @State private var showAIIntegrations = false

    var body: some View {
        NavigationSplitView {
            ProjectSidebar()
                .navigationSplitViewColumnWidth(min: 220, ideal: 260, max: 320)
        } detail: {
            if let project = app.selectedProject {
                ProjectDetailView(project: project, run: run, metrics: app.metrics,
                                  rfd3: app.rfd3, prediction: app.prediction,
                                  installer: installer)
                    .id(project.id)
            } else {
                EmptyWorkspace()
            }
        }
        .safeAreaInset(edge: .top) {
            if installer.completedWithIssues {
                HStack {
                    Label("Setup finished with some components incomplete. Available engines can be used.", systemImage: "exclamationmark.triangle")
                    Button("Review installation") { showComponents = true }
                }
                .font(.callout).padding(10)
            }
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { showQueue.toggle() } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "list.bullet.rectangle")
                        if !jobs.active.isEmpty {
                            Text("\(jobs.active.count)").monospacedDigit()
                        }
                    }
                }
                .help("Job queue: \(jobs.waiting.count) waiting, \(jobs.active.count - jobs.waiting.count) running or stopping")
                .accessibilityLabel("Open job queue, \(jobs.active.count) active jobs")
                .accessibilityIdentifier("job-queue-button")
                .popover(isPresented: $showQueue, arrowEdge: .bottom) {
                    JobQueueView(run: app.run, rfd3: app.rfd3, prediction: app.prediction, nise: app.nise)
                }
            }
            ToolbarItem(placement: .primaryAction) {
                Button { showActivity.toggle() } label: {
                    Label("Activity", systemImage: app.run.isRunning || app.rfd3.isRunning || app.prediction.isRunning || app.nise.isRunning
                          ? "waveform.path" : "clock.arrow.circlepath")
                }
                .help("See running work, previous results, and resumable campaigns")
                .keyboardShortcut("a", modifiers: [.command, .shift])
                .accessibilityLabel("Open activity centre")
                .accessibilityIdentifier("activity-center-button")
                .popover(isPresented: $showActivity, arrowEdge: .bottom) {
                    ActivityCenterView(run: app.run, rfd3: app.rfd3,
                                       prediction: app.prediction, history: app.history,
                                       projectFilter: nil)
                }
            }
            ToolbarItem(placement: .primaryAction) {
                Button { showComponents = true } label: {
                    Label("Engines", systemImage: "square.grid.2x2")
                }
                .help("Add folding and design engines")
                .keyboardShortcut("e", modifiers: [.command, .shift])
            }
            ToolbarItem(placement: .primaryAction) {
                Button { showAIIntegrations = true } label: {
                    Label("AI", systemImage: "sparkles")
                }
                .help("Connect Codex or Claude Desktop")
                .accessibilityLabel("Configure AI assistant access")
                .accessibilityIdentifier("ai-integrations-button")
            }
        }
        .sheet(isPresented: $showComponents) {
            VStack(spacing: 0) {
                ComponentsView(installer: installer)
                Divider()
                HStack {
                    Spacer()
                    Button("Done") { showComponents = false }.keyboardShortcut(.defaultAction)
                }.padding(12)
            }
            .frame(width: 720, height: 620)
        }
        .sheet(isPresented: $showAIIntegrations) {
            VStack(spacing: 0) {
                AIIntegrationsView()
                Divider()
                HStack {
                    Spacer()
                    Button("Done") { showAIIntegrations = false }.keyboardShortcut(.defaultAction)
                }.padding(12)
            }
        }
    }
}

/// Shows the design form until a run is launched, then the live dashboard.
struct ProjectDetailView: View {
    @EnvironmentObject var app: AppState
    let project: Project
    @ObservedObject var run: RunController
    @ObservedObject var metrics: MetricsWatcher
    @ObservedObject var rfd3: RFD3Controller
    @ObservedObject var prediction: PredictionController
    @ObservedObject var installer: PipelineInstaller
    @State private var showRunHistory = false
    @State private var showingRename = false
    @State private var renameText = ""

    private var mode: Binding<WorkspaceMode> {
        Binding(
            get: { app.projects.first(where: { $0.id == project.id })?.preferredMode ?? project.preferredMode },
            set: { newMode in app.updateProject(id: project.id) { $0.preferredMode = newMode } }
        )
    }

    private var activeMode: WorkspaceMode? {
        if run.isRunning { return .iterative }
        if rfd3.isRunning { return .rfdiffusion }
        if prediction.isRunning { return .predict }
        if app.nise.isRunning { return .nise }
        return nil
    }

    private var hasDisplayedRun: Bool {
        switch mode.wrappedValue {
        case .iterative: return run.projectID == project.id && run.campaignRoot != nil
        case .rfdiffusion: return rfd3.projectSlug == project.slug && rfd3.campaignRoot != nil
        case .predict: return prediction.projectSlug == project.slug && prediction.outputRoot != nil
        case .nise: return app.nise.projectSlug == project.slug && app.nise.outputRoot != nil
        }
    }

    private var canPrepareNewRun: Bool {
        switch mode.wrappedValue {
        case .iterative: return run.canStartAnother
        case .rfdiffusion: return rfd3.canStartAnother
        case .predict: return prediction.canStartAnother
        case .nise: return app.nise.canStartAnother
        }
    }

    private func prepareNewRun() {
        switch mode.wrappedValue {
        case .iterative: run.prepareNewRun()
        case .rfdiffusion: rfd3.prepareNewRun()
        case .predict: prediction.prepareNewRun()
        case .nise: app.nise.prepareNewRun()
        }
    }

    var body: some View {
        // NavigationSplitView may ask its detail for an unconstrained ideal
        // height. RFdiffusion3's long form then reports its full content height,
        // which can grow the detail far beyond the window and move this picker
        // off-screen. GeometryReader supplies the real viewport; the workflow
        // content below must scroll inside the space left by the fixed header.
        GeometryReader { viewport in
            detailContents
                .frame(width: viewport.size.width, height: viewport.size.height,
                       alignment: .top)
                .clipped()
        }
        .onAppear {
            app.history.refresh(projects: app.projects)
            // A detached RFdiffusion3 campaign can outlive the app; reattach so a
            // multi-day run does not look like it vanished on restart.
            rfd3.reattachIfRunning(project: project)
        }
        .sheet(isPresented: $showingRename) {
            NameEditorSheet(
                title: "Rename Workspace",
                prompt: "Use a name that will still make sense when this workspace contains predictions and design runs.",
                placeholder: "Workspace name",
                name: $renameText,
                actionLabel: "Rename"
            ) {
                app.renameProject(project, to: renameText)
                showingRename = false
            } cancel: {
                showingRename = false
            }
        }
    }

    private var detailContents: some View {
        VStack(spacing: 0) {
            // Navigation must remain available while a long campaign runs. The
            // broker serializes submitted jobs; navigation remains available.
            HStack(alignment: .center, spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(project.name)
                        .font(.title3.bold())
                        .lineLimit(1)
                    Text("Workspace")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Button {
                    renameText = project.name
                    showingRename = true
                } label: {
                    Image(systemName: "pencil")
                }
                .buttonStyle(.plain)
                .help("Rename workspace")
                .accessibilityLabel("Rename \(project.name)")

                Spacer(minLength: 12)

                if hasDisplayedRun {
                    Button { prepareNewRun() } label: {
                        Label("New run", systemImage: "plus")
                    }
                    .disabled(!canPrepareNewRun)
                    .help("Set up another \(mode.wrappedValue.label) run. Existing jobs continue in the queue.")
                    .accessibilityIdentifier("new-queued-workflow-run")
                }

                Picker("", selection: mode) {
                    ForEach(WorkspaceMode.allCases) { m in
                        Label(m.label, systemImage: m.systemImage).tag(m)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(maxWidth: 540)
                .accessibilityLabel("Workflow")
                .accessibilityIdentifier("project-mode-picker")

                Button { showRunHistory.toggle() } label: {
                    Label("Runs", systemImage: "clock.arrow.circlepath")
                }
                .help("Open this workspace's completed and resumable runs")
                .accessibilityLabel("Open run history for \(project.name)")
                .accessibilityIdentifier("project-run-history-button")
                .popover(isPresented: $showRunHistory, arrowEdge: .bottom) {
                    ActivityCenterView(run: app.run, rfd3: app.rfd3,
                                       prediction: app.prediction, history: app.history,
                                       projectFilter: project.id)
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)

            if let notice = app.runtimeNotice {
                Label(notice, systemImage: "clock").font(.caption).padding(.top, 8)
            }
            if let activeMode {
                Label("\(activeMode.label) has active work. You can add runs from any tab to the queue; open Queue to see all workspaces.",
                      systemImage: "waveform.path")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.top, 8)
                    .accessibilityIdentifier("active-workflow-banner")
            }
            Divider().padding(.top, 10)

            Group {
                switch mode.wrappedValue {
                case .iterative:
                    if run.projectID == project.id, let context = run.projectContext,
                       run.isRunning || run.campaignRoot != nil {
                        LiveDashboardView(project: context, run: run, metrics: metrics)
                    } else {
                        DesignFormView(project: project, installer: installer, run: run)
                    }
                case .rfdiffusion:
                    RFD3View(project: project, controller: rfd3, installer: installer)
                case .nise:
                    NISEView(project: project, controller: app.nise, installer: installer)
                case .predict:
                    PredictView(project: project, controller: prediction, installer: installer)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .layoutPriority(1)
            .clipped()
        }
    }
}

struct EmptyWorkspace: View {
    @EnvironmentObject var app: AppState
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "atom")
                .font(.system(size: 52))
                .foregroundStyle(.tint)
            Text("Start some work").font(.title2.bold())
            Text("Create a workspace for predictions, Protein Hunter, NISE, or RFdiffusion3.")
                .foregroundStyle(.secondary)
            HStack(spacing: 10) {
                Button { app.addProject(name: "", preferredMode: .predict) } label: {
                    Label("New Prediction", systemImage: "cube.transparent")
                }
                .buttonStyle(.borderedProminent)
                Button { app.addProject(name: "", preferredMode: .iterative) } label: {
                    Label("New Workspace", systemImage: "plus")
                }
            }
            .controlSize(.large)
        }
        .padding(40)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
