import SwiftUI

@main
struct iProteinStudioApp: App {
    @StateObject private var app = AppState()

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
            CommandGroup(replacing: .newItem) {
                Button("New Design Project") { app.addProject(name: "Untitled Design") }
                    .keyboardShortcut("n")
            }
        }
    }
}
