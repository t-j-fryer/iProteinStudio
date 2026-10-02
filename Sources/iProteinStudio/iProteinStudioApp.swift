import SwiftUI

@main
struct iProteinStudioApp: App {
    @StateObject private var app = AppState()
    @Environment(\.openWindow) private var openWindow
    private let updates = AppUpdateService()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(app)
                .environmentObject(app.thumbnails)
                .environmentObject(app.smilesThumbnails)
                .environmentObject(app.predictions)
                .frame(minWidth: 820, minHeight: 600)
                .modifier(StudioAppearance())
        }
        .windowStyle(.titleBar)
        .commands {
            CommandGroup(after: .appInfo) {
                CheckForUpdatesView(service: updates)
            }
            CommandGroup(before: .help) {
                Button("Discover iProteinStudio…") { openWindow(id: "studio-introduction") }
            }
            CommandGroup(replacing: .newItem) {
                Button("New Workspace") { app.addProject(name: "", preferredMode: .iterative) }
                    .keyboardShortcut("n")
                Button("New Prediction") { app.addProject(name: "", preferredMode: .predict) }
                    .keyboardShortcut("n", modifiers: [.command, .shift])
            }
        }

        Window("Discover iProteinStudio", id: "studio-introduction") {
            StudioIntroductionWindow()
        }
        .defaultSize(width: 820, height: 680)
        .windowResizability(.contentMinSize)

        WindowGroup("Run Results", for: RunResultsWindowRequest.self) { request in
            if let request = request.wrappedValue {
                RunResultsView(root: request.root, workflow: request.workflow,
                               title: request.title)
                    .environmentObject(app)
                    .environmentObject(app.thumbnails)
                    .environmentObject(app.smilesThumbnails)
                    .environmentObject(app.predictions)
                    .modifier(StudioAppearance())
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
                StudioAppearanceSettings()
                    .tabItem { Label("Appearance", systemImage: "circle.lefthalf.filled") }
                AIIntegrationsView()
                    .tabItem { Label("AI assistants", systemImage: "sparkles") }
            }
            .modifier(StudioAppearance())
        }
    }
}
