import SwiftUI
import AppKit

/// One home for ordinary Predict runs and reusable target-prep structures.
struct PredictionsLibraryView: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var predictions: PredictionStore
    var onClose: () -> Void

    @State private var selection = Set<String>()
    @State private var confirmClear = false
    @State private var selectedRun: StudioRunRecord?

    private var predictionRuns: [StudioRunRecord] {
        app.history.runs.filter { $0.workflow == .prediction }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if predictions.records.isEmpty && predictionRuns.isEmpty {
                EmptyHint(text: "No saved predictions",
                          detail: "Completed Predict runs and reusable structures from Target Prep will appear here automatically.",
                          systemImage: "cylinder.split.1x2")
                    .frame(maxHeight: .infinity)
            } else {
                List(selection: $selection) {
                    if !predictionRuns.isEmpty {
                        Section("Prediction runs") {
                            ForEach(predictionRuns) { run in
                                PredictionRunRow(record: run) { selectedRun = run }
                            }
                        }
                    }
                    if !predictions.records.isEmpty {
                        Section("Reusable Target Prep structures") {
                            ForEach(predictions.records) { rec in
                                PredictionRow(record: rec).tag(rec.id)
                            }
                        }
                    }
                }
                .listStyle(.inset)
            }
            Divider()
            footer
        }
        .frame(width: 720, height: 560)
        .onAppear { app.history.refresh(projects: app.projects) }
        .sheet(item: $selectedRun) { run in
            RunResultsView(root: run.root, workflow: .prediction,
                           title: "\(run.name) results")
        }
        .confirmationDialog("Delete all \(predictions.records.count) predictions?",
                            isPresented: $confirmClear, titleVisibility: .visible) {
            Button("Delete All", role: .destructive) { predictions.clearAll(); selection = [] }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This frees the cached structures. It cannot be undone.")
        }
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("Predictions Library").font(.headline)
                Text("\(predictionRuns.count) run\(predictionRuns.count == 1 ? "" : "s") · \(predictions.records.count) reusable structure\(predictions.records.count == 1 ? "" : "s") · \(sizeText)")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Button("Done", action: onClose)
        }
        .padding()
    }

    private var footer: some View {
        HStack {
            Text("Target Prep cache")
                .font(.caption).foregroundStyle(.secondary)
            Button(role: .destructive) { predictions.remove(selection); selection = [] } label: {
                Label("Delete Selected", systemImage: "trash")
            }
            .disabled(selection.isEmpty)
            Text(selection.isEmpty ? "" : "\(selection.count) selected")
                .font(.caption).foregroundStyle(.secondary)
            Spacer()
            Button(role: .destructive) { confirmClear = true } label: {
                Label("Clear All", systemImage: "trash.slash")
            }
            .disabled(predictions.records.isEmpty)
        }
        .padding()
    }

    private var sizeText: String {
        ByteCountFormatter.string(fromByteCount: predictions.totalBytes(), countStyle: .file)
    }
}

private struct PredictionRunRow: View {
    let record: StudioRunRecord
    let open: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: record.state.systemImage)
                .foregroundStyle(record.state == .completed ? .blue : .orange)
                .frame(width: 30)
            VStack(alignment: .leading, spacing: 2) {
                Text(record.projectName).font(.body.weight(.medium))
                Text("\(record.date.formatted(date: .abbreviated, time: .shortened)) · \(record.detail)")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            if record.state == .completed {
                Button("View", action: open).controlSize(.small)
            }
            Button {
                NSWorkspace.shared.activateFileViewerSelecting([record.root])
            } label: {
                Image(systemName: "folder")
            }
            .buttonStyle(.plain).help("Reveal prediction run")
        }
        .padding(.vertical, 4)
    }
}

/// One prediction row: thumbnail + name + details; hover shows the sequence/SMILES.
struct PredictionRow: View {
    @EnvironmentObject var thumbnails: ThumbnailStore
    @EnvironmentObject var smilesThumbnails: SmilesThumbnailStore
    @EnvironmentObject var predictions: PredictionStore
    let record: PredictionRecord

    var body: some View {
        HStack(spacing: 12) {
            thumbnail
                .frame(width: 52, height: 40)
                .clipShape(RoundedRectangle(cornerRadius: 6))
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(.quaternary))
            VStack(alignment: .leading, spacing: 2) {
                Text(record.name).font(.body)
                Text("\(record.targetKind == .protein ? "Protein" : "Ligand") · \(record.engineLabel) · \(dateText)")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
        .help(hoverText)   // hover reveals the sequence / SMILES
    }

    @ViewBuilder private var thumbnail: some View {
        if record.targetKind == .ligand {
            SmilesThumbnail(store: smilesThumbnails, smiles: record.payload)
        } else if let cif = predictions.cifPath(for: record) {
            StructureThumbnail(store: thumbnails, structurePath: cif)
        } else {
            RoundedRectangle(cornerRadius: 6).fill(.quaternary.opacity(0.3))
                .overlay(Image(systemName: "cube").foregroundStyle(.tertiary))
        }
    }

    private var hoverText: String {
        let label = record.targetKind == .protein ? "Sequence" : "SMILES"
        return "\(label):\n\(record.payload)"
    }

    private var dateText: String {
        record.createdAt.formatted(date: .abbreviated, time: .shortened)
    }
}
