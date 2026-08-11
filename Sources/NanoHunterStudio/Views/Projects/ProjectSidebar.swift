import SwiftUI
import AppKit

/// Left-hand list of design projects with create / delete / reveal actions.
struct ProjectSidebar: View {
    @EnvironmentObject var app: AppState
    @State private var newName = ""
    @State private var showingNew = false
    @State private var renaming: Project?
    @State private var renameText = ""
    @State private var showLibrary = false

    var body: some View {
        List(selection: Binding(
            get: { app.selectedProjectID },
            set: { app.selectedProjectID = $0 }
        )) {
            Section("Design Projects") {
                ForEach(app.projects) { project in
                    ProjectRow(project: project)
                        .tag(project.id)
                        .contextMenu {
                            Button("Rename…") { beginRename(project) }
                            Button("Reveal in Finder") {
                                NSWorkspace.shared.activateFileViewerSelecting([AppPaths.projectDir(project)])
                            }
                            Button("Delete", role: .destructive) { app.deleteProject(project) }
                        }
                }
            }
        }
        .listStyle(.sidebar)
        .safeAreaInset(edge: .bottom) {
            VStack(spacing: 8) {
                Button {
                    showingNew = true
                } label: {
                    Label("New Design Project", systemImage: "plus")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                Button {
                    showLibrary = true
                } label: {
                    Label("Predictions Library", systemImage: "cylinder.split.1x2")
                        .frame(maxWidth: .infinity)
                }
            }
            .padding(10)
        }
        .sheet(isPresented: $showLibrary) {
            PredictionsLibraryView { showLibrary = false }
        }
        .sheet(isPresented: $showingNew) {
            NewProjectSheet(title: "New Design Project", name: $newName) {
                app.addProject(name: newName); newName = ""; showingNew = false
            } cancel: { newName = ""; showingNew = false }
        }
        .sheet(item: $renaming) { project in
            NewProjectSheet(title: "Rename Project", name: $renameText) {
                app.renameProject(project, to: renameText); renaming = nil
            } cancel: { renaming = nil }
        }
    }

    private func beginRename(_ project: Project) {
        renameText = project.name
        renaming = project
    }
}

struct ProjectRow: View {
    @EnvironmentObject var smilesThumbnails: SmilesThumbnailStore
    let project: Project
    private var subtitle: String {
        let r = project.request
        switch r.designType {
        case .nanobody:   return "Nanobody · \(r.designer.label) · \(r.cdrs.flagValue)"
        case .minibinder: return "Mini-binder · \(r.designer.label) · \(r.binderMinLen)–\(r.binderMaxLen) aa"
        case .peptide:    return "Peptide · \(r.designer.label) · \(r.binderMinLen)–\(r.binderMaxLen) aa"
        }
    }
    private var ligandSmiles: String? {
        let r = project.request
        let s = r.targetSmiles.trimmingCharacters(in: .whitespaces)
        return (r.targetKind == .ligand && !s.isEmpty) ? s : nil
    }
    var body: some View {
        HStack(spacing: 8) {
            if let smiles = ligandSmiles {
                SmilesThumbnail(store: smilesThumbnails, smiles: smiles, cornerRadius: 5)
                    .frame(width: 30, height: 30)
            } else {
                Image(systemName: "flask")
                    .foregroundStyle(.tint)
            }
            VStack(alignment: .leading, spacing: 1) {
                Text(project.name).lineLimit(1)
                Text(subtitle)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .padding(.vertical, 2)
    }
}

struct NewProjectSheet: View {
    var title: String = "New Design Project"
    @Binding var name: String
    var create: () -> Void
    var cancel: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(title).font(.headline)
            TextField("Project name (e.g. Anti-CMY2 nanobody)", text: $name)
                .textFieldStyle(.roundedBorder)
                .frame(width: 340)
                .onSubmit(create)
            HStack {
                Spacer()
                Button("Cancel", role: .cancel, action: cancel)
                Button("Save", action: create)
                    .buttonStyle(.borderedProminent)
                    .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding(20)
    }
}
