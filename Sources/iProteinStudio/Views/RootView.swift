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
                WorkspaceView(run: app.run)
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
    @State private var showComponents = false

    var body: some View {
        NavigationSplitView {
            ProjectSidebar()
                .navigationSplitViewColumnWidth(min: 220, ideal: 260, max: 320)
        } detail: {
            if let project = app.selectedProject {
                ProjectDetailView(project: project, run: run, metrics: app.metrics)
            } else {
                EmptyWorkspace()
            }
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { showComponents = true } label: {
                    Label("Engines", systemImage: "square.grid.2x2")
                }
                .help("Add folding and design engines, or point Studio at AlphaFold 3 weights")
            }
        }
        .sheet(isPresented: $showComponents) {
            VStack(spacing: 0) {
                ComponentsView(installer: app.installer)
                Divider()
                HStack {
                    Spacer()
                    Button("Done") { showComponents = false }.keyboardShortcut(.defaultAction)
                }.padding(12)
            }
            .frame(width: 720, height: 620)
        }
        .onAppear {
            // AlphaFold 3 installed but unfed is the one state that looks like a
            // broken install and is actually a missing file the user must fetch.
            if app.installer.needsAlphaFoldWeights { showComponents = true }
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
    @State private var mode: ProjectMode = .iterative

    var body: some View {
        VStack(spacing: 0) {
            // Hidden while a run is live: switching tabs mid-campaign invites
            // starting a second GPU-heavy job on top of the first.
            if !run.isRunning && !app.rfd3.isRunning && !app.prediction.isRunning {
                Picker("", selection: $mode) {
                    ForEach(ProjectMode.allCases) { m in
                        Label(m.label, systemImage: m.systemImage).tag(m)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(maxWidth: 420)
                .padding(.top, 12)
                Divider().padding(.top, 10)
            }

            switch mode {
            case .iterative:
                if run.isRunning || run.campaignRoot != nil {
                    LiveDashboardView(project: project, run: run, metrics: metrics)
                } else {
                    DesignFormView(project: project)
                }
            case .rfdiffusion:
                RFD3View(project: project, controller: app.rfd3)
            case .predict:
                PredictView(project: project, controller: app.prediction)
            }
        }
        .onAppear {
            // A detached RFdiffusion3 campaign can outlive the app; reattach so a
            // multi-day run does not look like it vanished on restart.
            app.rfd3.reattachIfRunning(project: project)
            if app.rfd3.isRunning { mode = .rfdiffusion }
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
