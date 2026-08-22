import SwiftUI

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
        }
    }

    private var progress: some View {
        VStack(alignment: .leading, spacing: 8) {
            ProgressView(value: installer.progress).progressViewStyle(.linear)
            Text(installer.currentMessage).font(.callout)
            Button("Cancel", role: .cancel) { installer.cancel() }.controlSize(.small)
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
                    installer.optionalSelection = wanted
                    installer.install()
                } label: {
                    Label("Install \(selection.count) engine\(selection.count == 1 ? "" : "s")",
                          systemImage: "arrow.down.circle")
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
                    else if present { Text("incomplete").font(.caption2).foregroundStyle(.orange) }
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

extension Color {
    static var quaternaryLabelBackground: Color { Color(nsColor: .quaternaryLabelColor).opacity(0.12) }
}
