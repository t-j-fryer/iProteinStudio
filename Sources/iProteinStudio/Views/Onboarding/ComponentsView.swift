import SwiftUI
import AppKit

/// Add engines after the first install.
///
/// Nobody needs all of these, and together they run to tens of gigabytes, so the
/// first install is a choice rather than a download-everything. That choice has
/// to be revisable — deciding six weeks later that you want OpenFold-3 should not
/// mean reinstalling.
struct ComponentsView: View {
    @ObservedObject var installer: PipelineInstaller
    @State private var selection: Set<InstallComponent> = []
    @State private var pendingRemoval: InstallComponent?
    @State private var pendingInstall: EngineInstallPlan?

    private var optional: [InstallComponent] {
        InstallComponent.allCases.filter { !$0.isCore }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header
                if installer.isInstalling { progress } else { list }
            }
            .padding(28).frame(maxWidth: 720, alignment: .leading).frame(maxWidth: .infinity)
        }
        .alert(item: $pendingRemoval) { component in
            Alert(
                title: Text("Uninstall \(component.label)?"),
                message: Text(installer.uninstallDescription(component)),
                primaryButton: .destructive(Text("Delete engine")) {
                    selection.remove(component)
                    installer.uninstall(component)
                },
                secondaryButton: .cancel()
            )
        }
        .sheet(item: $pendingInstall) { plan in
            EngineInstallReview(plan: plan) {
                installer.optionalSelection = Set(plan.components.filter { !$0.isCore })
                selection.removeAll()
                pendingInstall = nil
                installer.install()
            } onCancel: {
                pendingInstall = nil
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("Engines").font(.largeTitle.bold())
                Spacer()
                Button { installer.refreshInstalledState() } label: {
                    Label("Refresh status", systemImage: "arrow.clockwise")
                }
                .controlSize(.small)
            }
            Text("Install only what you need. You can add or remove engines at any time; removing one never deletes workspaces, results, or saved alignments.")
                .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            LabeledContent("Managed runtime") {
                Text(AppPaths.support.path)
                    .font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)
            }
            .font(.caption)
            .foregroundStyle(.secondary)
            Text("Models and environments live in this managed folder, not inside the app bundle or the source repository.")
                .font(.caption2).foregroundStyle(.tertiary)
            Label("App updates never install or replace an engine checkpoint. Every large download is reviewed here first.",
                  systemImage: "checkmark.shield")
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(.top, 4)
        }
    }

    private var progress: some View {
        VStack(alignment: .leading, spacing: 8) {
            ProgressView(value: installer.progress).progressViewStyle(.linear)
            Text(installer.currentMessage).font(.callout)
            Text("Studio is keeping this Mac awake. Closing the window does not make a partial checkpoint usable; Cancel stops the full installer process tree and keeps resumable download bytes.")
                .font(.caption2).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            HStack {
                Button("Cancel", role: .cancel) { installer.cancel() }.controlSize(.small)
                if let log = installer.latestLogURL {
                    Button("Show installer log") {
                        NSWorkspace.shared.activateFileViewerSelecting([log])
                    }
                    .controlSize(.small)
                }
            }
        }
    }

    private var list: some View {
        VStack(alignment: .leading, spacing: 10) {
            if installer.isRemoving {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text(installer.currentMessage).font(.callout).foregroundStyle(.secondary)
                }
            }
            ForEach(optional) { component in
                row(component)
            }
            HStack {
                Button("Select all") { selection = Set(optional.filter { !installer.isUsable($0) }) }
                    .controlSize(.small)
                Button("Clear") { selection = [] }.controlSize(.small)
                Spacer()
                Button {
                    // Pull in anything the selection depends on, so a user cannot
                    // pick a component that then fails for a missing prerequisite.
                    var wanted = selection
                    for component in selection {
                        for dependency in component.requires where !installer.isUsable(dependency) {
                            wanted.insert(dependency)
                        }
                    }
                    pendingInstall = EngineInstallPlan(components: Array(wanted))
                } label: {
                    Label("Review \(selection.count) download\(selection.count == 1 ? "" : "s")…",
                          systemImage: "list.bullet.clipboard")
                }
                .buttonStyle(.borderedProminent)
                .disabled(selection.isEmpty || installer.isRemoving)
            }
            if let failure = installer.failure {
                Label(failure, systemImage: "exclamationmark.triangle.fill")
                    .font(.callout).foregroundStyle(.orange)
                    .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder private func row(_ component: InstallComponent) -> some View {
        let installed = installer.isUsable(component)
        let present = installer.hasManagedFiles(component)
        let detail = installer.detail(component)
        let availability = installer.components[component]?.availability
        HStack(alignment: .top, spacing: 10) {
            if installed {
                Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
            } else {
                Toggle("", isOn: Binding(
                    get: { selection.contains(component) },
                    set: { on in
                        if on { selection.insert(component) } else { selection.remove(component) }
                    })).toggleStyle(.checkbox).labelsHidden()
            }
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(component.label).font(.callout.weight(.medium))
                    Text(component.approximateSize).font(.caption2).foregroundStyle(.secondary)
                    if installed { Text("installed").font(.caption2).foregroundStyle(.green) }
                    else if availability == .update { Text("update available").font(.caption2).foregroundStyle(.blue) }
                    else if availability == .broken { Text("broken").font(.caption2).foregroundStyle(.red) }
                    else if availability == .busy { Text("in use").font(.caption2).foregroundStyle(.orange) }
                    else if availability == .incomplete || present { Text("incomplete").font(.caption2).foregroundStyle(.orange) }
                }
                Text(component.whatItGivesYou).font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                if !component.requires.isEmpty {
                    Text("Brings with it: " + component.requires.map(\.label).joined(separator: ", "))
                        .font(.caption2).foregroundStyle(.tertiary)
                }
                if installed, !detail.isEmpty, detail != component.label {
                    Text(detail).font(.caption2).foregroundStyle(.tertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer()
            if present {
                Button { pendingRemoval = component } label: {
                    Label("Remove…", systemImage: "trash")
                }
                .help("Uninstall \(component.label)…")
                .buttonStyle(.borderless)
                .controlSize(.small)
                .foregroundStyle(.secondary)
                .disabled(installer.isRemoving)
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 8)
            .fill(installed ? Color.green.opacity(0.07) : Color.quaternaryLabelBackground))
    }

}

/// A final consent boundary between selecting capabilities and transferring
/// multi-gigabyte environments/checkpoints. This is shared by first-run setup
/// and the Engines sheet so neither route can silently start a large download.
struct EngineInstallPlan: Identifiable {
    let id = UUID()
    let components: [InstallComponent]

    init(components: [InstallComponent]) {
        self.components = Array(Set(components)).sorted { $0.label < $1.label }
    }

    var estimatedInstalledBytes: Int64 {
        components.reduce(Int64(0)) { $0 + $1.estimatedInstalledBytes }
    }

    var estimatedInstalledSize: String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        return formatter.string(fromByteCount: estimatedInstalledBytes)
    }
}

struct EngineInstallReview: View {
    let plan: EngineInstallPlan
    let onConfirm: () -> Void
    let onCancel: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 5) {
                Text("Review downloads").font(.title2.bold())
                Text("Nothing is downloaded until you choose Install now.")
                    .foregroundStyle(.secondary)
                Text("Allow approximately \(plan.estimatedInstalledSize) of installed space, plus 3 GB kept free for macOS and temporary files.")
                    .font(.caption).foregroundStyle(.secondary)
            }

            ScrollView {
                VStack(spacing: 8) {
                    ForEach(plan.components) { component in
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: component.isCore ? "shippingbox.fill" : "externaldrive.badge.plus")
                                .foregroundStyle(.tint)
                                .frame(width: 20)
                            VStack(alignment: .leading, spacing: 2) {
                                HStack {
                                    Text(component.label).font(.headline)
                                    Spacer()
                                    Text(component.approximateSize)
                                        .font(.caption.monospacedDigit())
                                        .foregroundStyle(.secondary)
                                }
                                Text(component.whatItGivesYou)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                                if let note = component.downloadNote {
                                    Text(note).font(.caption2).foregroundStyle(.tertiary)
                                }
                            }
                        }
                        .padding(10)
                        .background(RoundedRectangle(cornerRadius: 9).fill(Color.quaternaryLabelBackground))
                    }
                }
            }

            Label("Sizes are approximate installed footprints. Partial transfers are retained for safe resume, and checkpoints are verified before use.",
                  systemImage: "info.circle")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            Label("These downloads are independent of application updates. You can remove an engine later without deleting workspaces, results or saved alignments.",
                  systemImage: "checkmark.shield")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            HStack {
                Button("Cancel", role: .cancel, action: onCancel)
                    .keyboardShortcut(.cancelAction)
                Spacer()
                Button("Install now", action: onConfirm)
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(24)
        .frame(width: 620, height: min(650, 270 + CGFloat(plan.components.count) * 92))
    }
}

extension Color {
    static var quaternaryLabelBackground: Color { Color(nsColor: .quaternaryLabelColor).opacity(0.12) }
}
