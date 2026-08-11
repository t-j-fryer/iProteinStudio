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
    }
}

/// Shows the design form until a run is launched, then the live dashboard.
struct ProjectDetailView: View {
    let project: Project
    @ObservedObject var run: RunController
    @ObservedObject var metrics: MetricsWatcher

    var body: some View {
        if run.isRunning || run.campaignRoot != nil {
            LiveDashboardView(project: project, run: run, metrics: metrics)
        } else {
            DesignFormView(project: project)
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
