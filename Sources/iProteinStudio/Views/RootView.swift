import SwiftUI
import StudioCore

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
    @AppStorage("studio.introductionSeen.v1") private var introductionSeen = false

    var body: some View {
        Group {
            if IntroductionPolicy.shouldPresent(hasSeen: introductionSeen,
                installed: installer.installed, hasSavedWork: !app.projects.isEmpty,
                installationBusy: installer.isInstalling,
                recoveryNeeded: installer.completedWithIssues || installer.failure != nil || installer.needsAppleBuildTools) {
                StudioIntroductionView(completionTitle: "Continue to setup") { introductionSeen = true }
            } else if installer.installed {
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
    @Environment(\.openWindow) private var openWindow
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
        .background(StudioPalette.canvas)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { openWindow(id: "studio-introduction") } label: {
                    Label("Discover Studio", systemImage: "book.closed")
                }
                .help("A short introduction to Studio and its workflows")
            }
            ToolbarItem(placement: .primaryAction) {
                Button { showQueue = true } label: {
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
        // Present from the workspace, not the changing toolbar label. A large
        // edge-anchored popover can clip and leave stale presentation dimming.
        .sheet(isPresented: $showQueue) {
            JobQueueView(run: app.run, rfd3: app.rfd3, prediction: app.prediction, nise: app.nise)
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
    @State private var choosingDesign = false
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

                if hasDisplayedRun && !choosingDesign {
                    Button { prepareNewRun() } label: {
                        Label("New run", systemImage: "plus")
                    }
                    .disabled(!canPrepareNewRun)
                    .help("Set up another \(mode.wrappedValue.label) run. Existing jobs continue in the queue.")
                    .accessibilityIdentifier("new-queued-workflow-run")
                }

                HStack(spacing: 6) {
                    StudioSectionTab(title: "Predict", artwork: "predict-object",
                                     selected: !choosingDesign && mode.wrappedValue == .predict) {
                        mode.wrappedValue = .predict
                        choosingDesign = false
                    }
                    StudioSectionTab(title: "Design", artwork: "design-object",
                                     selected: choosingDesign || mode.wrappedValue != .predict) {
                        choosingDesign = true
                    }
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel("Workspace section")
                .accessibilityIdentifier("workspace-section-picker")

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
            .padding(.bottom, 10)
            .background(StudioPalette.panel)

            if !choosingDesign && mode.wrappedValue != .predict {
                HStack(spacing: 8) {
                    Button { choosingDesign = true } label: {
                        Label("Design methods", systemImage: "chevron.left")
                    }
                    .accessibilityIdentifier("choose-design-method")
                    Text(mode.wrappedValue.label).font(.callout.weight(.medium))
                    Spacer()
                }
                .padding(.horizontal, 16).padding(.vertical, 8)
            }

            if let notice = app.runtimeNotice {
                Label(notice, systemImage: "clock").font(.caption).padding(.top, 8)
            }
            if let activeMode {
                Label("\(activeMode.label) has active work. You can add runs from any workflow to the queue; open Queue to see all workspaces.",
                      systemImage: "waveform.path")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.top, 8)
                    .accessibilityIdentifier("active-workflow-banner")
            }
            Divider().padding(.top, 10)

            ZStack {
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
                // Keep the current form mounted while choosing a method: an
                // exploratory navigation click must not discard in-progress input.
                .opacity(choosingDesign ? 0 : 1)
                .allowsHitTesting(!choosingDesign)
                .disabled(choosingDesign)
                .accessibilityHidden(choosingDesign)

                if choosingDesign {
                    DesignMethodChooser(previousMode: mode.wrappedValue) { selection in
                        mode.wrappedValue = selection
                        choosingDesign = false
                    }
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
    @Environment(\.openWindow) private var openWindow
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                HStack(spacing: 14) {
                    StudioArtwork(name: "terra-loop").frame(width: 66, height: 66)
                    VStack(alignment: .leading, spacing: 5) {
                        Text("Your next question starts here.").font(.title.weight(.semibold))
                        Text("Choose a workflow to create a workspace.").foregroundStyle(.secondary)
                    }
                }
                StudioArtwork(name: "branching-possibilities")
                    .frame(maxHeight: 230).clipShape(RoundedRectangle(cornerRadius: 12))
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 235))], spacing: 14) {
                    ForEach(WorkspaceMode.allCases) { mode in
                        Button { app.addProject(name: "", preferredMode: mode) } label: {
                            HStack(alignment: .top, spacing: 12) {
                                StudioWorkflowArtwork(mode: mode).frame(width: 44, height: 44)
                                    .clipShape(RoundedRectangle(cornerRadius: 10))
                                VStack(alignment: .leading, spacing: 5) {
                                    Text(mode.label).font(.headline)
                                    Text(mode.introduction).font(.callout).foregroundStyle(.secondary)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                                Spacer(minLength: 0)
                            }
                            .padding(16).frame(maxWidth: .infinity, minHeight: 108, alignment: .topLeading)
                            .modifier(StudioSurface()).contentShape(RoundedRectangle(cornerRadius: 12))
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Create \(mode.label) workspace")
                    }
                }
                Button("Discover Studio…") { openWindow(id: "studio-introduction") }
                Text("Creating a workspace does not start a run or download an engine.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            .padding(30).frame(maxWidth: 900).frame(maxWidth: .infinity)
        }
        .background(StudioPalette.canvas)
    }
}
