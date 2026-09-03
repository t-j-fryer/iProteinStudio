import SwiftUI

@main
struct iProteinStudioApp: App {
    @StateObject private var app = AppState()
    private let updates = AppUpdateService()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(app)
                .environmentObject(app.thumbnails)
                .environmentObject(app.smilesThumbnails)
                .environmentObject(app.predictions)
                .frame(minWidth: 1080, minHeight: 720)
        }
        .windowStyle(.titleBar)
        .commands {
            CommandGroup(after: .appInfo) {
                CheckForUpdatesView(service: updates)
            }
            CommandGroup(replacing: .newItem) {
                Button("New Workspace") { app.addProject(name: "", preferredMode: .iterative) }
                    .keyboardShortcut("n")
                Button("New Prediction") { app.addProject(name: "", preferredMode: .predict) }
                    .keyboardShortcut("n", modifiers: [.command, .shift])
            }
        }

        WindowGroup("Run Results", for: RunResultsWindowRequest.self) { request in
            if let request = request.wrappedValue {
                RunResultsView(root: request.root, workflow: request.workflow,
                               title: request.title)
                    .environmentObject(app)
                    .environmentObject(app.thumbnails)
                    .environmentObject(app.smilesThumbnails)
                    .environmentObject(app.predictions)
            } else {
                ContentUnavailableView("No run selected", systemImage: "cube.transparent")
            }
        }
        .defaultSize(width: 1060, height: 760)
        .windowResizability(.contentMinSize)

        Settings {
            TabView {
                UpdateSettingsView(service: updates)
                    .tabItem { Label("Application", systemImage: "gear") }
                AIIntegrationsView()
                    .tabItem { Label("AI assistants", systemImage: "sparkles") }
            }
        }
    }
}
