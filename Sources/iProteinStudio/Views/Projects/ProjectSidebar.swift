import SwiftUI
import AppKit

/// Left-hand home for reusable workspaces and results from every workflow.
struct ProjectSidebar: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var predictions: PredictionStore
    @State private var newName = ""
    @State private var showingNew = false
    @State private var renaming: Project?
    @State private var renameText = ""
    @State private var deleting: Project?
    @State private var showPredictions = false
    @State private var showActivity = false

    private var predictionCount: Int {
        predictions.records.count + app.history.runs.filter { $0.workflow == .prediction }.count
    }

    var body: some View {
        List(selection: Binding(
            get: { app.selectedProjectID },
            set: { app.selectedProjectID = $0 }
        )) {
            Section("Library") {
                Button { showPredictions = true } label: {
                    LibraryRow(title: "Predictions", count: predictionCount,
                               systemImage: "cube.transparent.3d")
                }
                .buttonStyle(.plain)
                .help("Browse prediction runs and reusable target structures")

                Button { showActivity.toggle() } label: {
                    LibraryRow(title: "All Runs", count: app.history.runs.count,
                               systemImage: "clock.arrow.circlepath")
                }
                .buttonStyle(.plain)
                .help("See running, completed, failed, and resumable work")
                .popover(isPresented: $showActivity, arrowEdge: .trailing) {
                    ActivityCenterView(run: app.run, rfd3: app.rfd3,
                                       prediction: app.prediction, history: app.history,
                                       projectFilter: nil)
                }
            }

            Section("Workspaces") {
                ForEach(app.projects) { project in
                    ProjectRow(
                        project: project,
                        rename: { beginRename(project) },
                        reveal: {
                            NSWorkspace.shared.activateFileViewerSelecting([AppPaths.projectDir(project)])
                        },
                        delete: { deleting = project }
                    )
                    .tag(project.id)
                }
            }
        }
        .listStyle(.sidebar)
        .safeAreaInset(edge: .bottom) {
            VStack(spacing: 8) {
                Button {
                    app.addProject(name: "", preferredMode: .predict)
                } label: {
                    Label("New Prediction", systemImage: "cube.transparent")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut("n", modifiers: [.command, .shift])

                Button {
                    newName = ""
                    showingNew = true
                } label: {
                    Label("New Workspace", systemImage: "plus")
                        .frame(maxWidth: .infinity)
                }
                .keyboardShortcut("n", modifiers: .command)
            }
            .padding(10)
        }
        .sheet(isPresented: $showPredictions) {
            PredictionsLibraryView { showPredictions = false }
        }
        .sheet(isPresented: $showingNew) {
            NameEditorSheet(
                title: "New Workspace",
                prompt: "A workspace can contain predictions, iterative design, and RFdiffusion3 runs for the same piece of work.",
                placeholder: "e.g. Cobratoxin binders",
                name: $newName,
                actionLabel: "Create"
            ) {
                app.addProject(name: newName, preferredMode: .iterative)
                newName = ""
                showingNew = false
            } cancel: {
                newName = ""
                showingNew = false
            }
        }
        .sheet(item: $renaming) { project in
            NameEditorSheet(
                title: "Rename Workspace",
                prompt: "This changes the name shown in Studio. Existing result paths remain stable.",
                placeholder: "Workspace name",
                name: $renameText,
                actionLabel: "Rename"
            ) {
                app.renameProject(project, to: renameText)
                renaming = nil
            } cancel: {
                renaming = nil
            }
        }
        .confirmationDialog(
            deleting.map { "Delete \($0.name)?" } ?? "Delete workspace?",
            isPresented: Binding(
                get: { deleting != nil },
                set: { if !$0 { deleting = nil } }
            ),
            titleVisibility: .visible
        ) {
            if let project = deleting {
                Button("Delete Workspace and Results", role: .destructive) {
                    app.deleteProject(project)
                    deleting = nil
                }
            }
            Button("Cancel", role: .cancel) { deleting = nil }
        } message: {
            Text("This removes the workspace and its saved runs from this Mac. It cannot be undone.")
        }
    }

    private func beginRename(_ project: Project) {
        renameText = project.name
        renaming = project
    }
}

private struct LibraryRow: View {
    let title: String
    let count: Int
    let systemImage: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: systemImage).foregroundStyle(.tint).frame(width: 18)
            Text(title)
            Spacer()
            if count > 0 {
                Text("\(count)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
        .contentShape(Rectangle())
        .padding(.vertical, 2)
    }
}

struct ProjectRow: View {
    @EnvironmentObject var smilesThumbnails: SmilesThumbnailStore
    let project: Project
    let rename: () -> Void
    let reveal: () -> Void
    let delete: () -> Void

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
                Image(systemName: project.preferredMode.systemImage)
                    .foregroundStyle(.tint)
                    .frame(width: 30)
            }
            VStack(alignment: .leading, spacing: 1) {
                Text(project.name).lineLimit(1)
                Text(project.workflowSummary)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 2)
            Menu {
                Button("Rename…", action: rename)
                Button("Reveal in Finder", action: reveal)
                Divider()
                Button("Delete…", role: .destructive, action: delete)
            } label: {
                Image(systemName: "ellipsis.circle")
                    .foregroundStyle(.secondary)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Workspace actions")
            .accessibilityLabel("Actions for \(project.name)")
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
        .onTapGesture(count: 2, perform: rename)
        .contextMenu {
            Button("Rename…", action: rename)
            Button("Reveal in Finder", action: reveal)
            Button("Delete…", role: .destructive, action: delete)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("\(project.name), \(project.workflowSummary)")
    }
}

/// Shared editor for workspace and prediction display names.
struct NameEditorSheet: View {
    let title: String
    let prompt: String
    let placeholder: String
    @Binding var name: String
    let actionLabel: String
    var save: () -> Void
    var cancel: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(title).font(.headline)
            Text(prompt)
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            TextField(placeholder, text: $name)
                .textFieldStyle(.roundedBorder)
                .frame(width: 380)
                .onSubmit(save)
            HStack {
                Spacer()
                Button("Cancel", role: .cancel, action: cancel)
                Button(actionLabel, action: save)
                    .buttonStyle(.borderedProminent)
                    .disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(20)
        .frame(width: 430)
    }
}
