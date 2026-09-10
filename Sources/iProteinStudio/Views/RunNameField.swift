import SwiftUI

struct RunNameField: View {
    @EnvironmentObject var app: AppState
    let project: Project
    let mode: WorkspaceMode

    var body: some View {
        TextField("Run name (optional)", text: Binding(
            get: { app.projects.first(where: { $0.id == project.id })?.runNames[mode.rawValue] ?? "" },
            set: { name in app.updateProject(id: project.id) { $0.runNames[mode.rawValue] = String(name.prefix(120)) } }))
            .textFieldStyle(.roundedBorder)
            .frame(minWidth: 160, idealWidth: 220, maxWidth: 280)
            .help("A name for this run in Queue and Activity. Leave blank for an automatic name. Reusing a name creates a separate run.")
            .accessibilityLabel("Run name, optional")
            .accessibilityIdentifier("run-name-\(mode.rawValue)")
    }
}
