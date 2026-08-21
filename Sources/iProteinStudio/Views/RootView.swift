import SwiftUI

/// Top-level router: setup wizard until the pipeline is installed, then the
/// projects workspace. `app.installer` / `app.run` are nested observable
/// objects, so views that depend on them receive them as `@ObservedObject`.
struct RootView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        RouterView(installer: app.installer)
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

    var body: some View {
        NavigationSplitView {
            ProjectSidebar()
                .navigationSplitViewColumnWidth(min: 220, ideal: 260, max: 320)
        } detail: {
            if let project = app.selectedProject {
                ProjectDetailView(project: project, run: run, metrics: app.metrics,
                                  rfd3: app.rfd3, prediction: app.prediction,
                                  installer: installer)
            } else {
                EmptyWorkspace()
            }
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { showActivity.toggle() } label: {
                    Label("Activity", systemImage: app.run.isRunning || app.rfd3.isRunning || app.prediction.isRunning
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
                .keyboardShortcut(",", modifiers: .command)
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
    }
}

/// The two ways to approach a target. They share the project, so a target
/// entered once can be attacked either way.
enum ProjectMode: String, CaseIterable, Identifiable, Hashable {
    case iterative
    case rfdiffusion
    case predict

    var id: String { rawValue }
    var label: String {
        switch self {
        case .iterative:   return "Iterative design"
        case .rfdiffusion: return "RFdiffusion3"
        case .predict:     return "Predict"
        }
    }
    var systemImage: String {
        switch self {
        case .iterative:   return "arrow.triangle.2.circlepath"
        case .rfdiffusion: return "sparkles"
        case .predict:     return "cube.transparent"
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
    @State private var mode: ProjectMode = .iterative
    @State private var showRunHistory = false

    private var activeMode: ProjectMode? {
        if run.isRunning { return .iterative }
        if rfd3.isRunning { return .rfdiffusion }
        if prediction.isRunning { return .predict }
        return nil
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
            if rfd3.isRunning { mode = .rfdiffusion }
        }
    }

    private var detailContents: some View {
        VStack(spacing: 0) {
            // Navigation must remain available while a long campaign runs. The
            // individual Start buttons prevent concurrent GPU work; hiding this
            // picker trapped users inside RFdiffusion3 for multi-day campaigns.
            HStack(spacing: 10) {
                Picker("", selection: $mode) {
                    ForEach(ProjectMode.allCases) { m in
                        Label(m.label, systemImage: m.systemImage).tag(m)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(maxWidth: 420)
                .accessibilityLabel("Workflow")
                .accessibilityIdentifier("project-mode-picker")

                Button { showRunHistory.toggle() } label: {
                    Label("Runs", systemImage: "clock.arrow.circlepath")
                }
                .help("Open this project's completed and resumable runs")
                .accessibilityLabel("Open run history for \(project.name)")
                .accessibilityIdentifier("project-run-history-button")
                .popover(isPresented: $showRunHistory, arrowEdge: .bottom) {
                    ActivityCenterView(run: app.run, rfd3: app.rfd3,
                                       prediction: app.prediction, history: app.history,
                                       projectFilter: project.id)
                }
            }
            .padding(.top, 12)

            if let activeMode {
                Label("\(activeMode.label) is running. You can inspect every tab; starting another run is paused.",
                      systemImage: "waveform.path")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.top, 8)
                    .accessibilityIdentifier("active-workflow-banner")
            }
            Divider().padding(.top, 10)

            Group {
                switch mode {
                case .iterative:
                    if run.isRunning || run.campaignRoot != nil {
                        LiveDashboardView(project: project, run: run, metrics: metrics)
                    } else {
                        DesignFormView(project: project, installer: installer)
                    }
                case .rfdiffusion:
                    RFD3View(project: project, controller: rfd3, installer: installer)
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
            Text("Design a nanobody").font(.title2.bold())
            Text("Create a project to specify your target and start a design run.")
                .foregroundStyle(.secondary)
            Button { app.addProject(name: "Untitled Design") } label: {
                Label("New Design Project", systemImage: "plus")
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
        }
        .padding(40)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
