import SwiftUI

/// Add engines after the first install, and point the app at AlphaFold 3 weights.
///
/// Nobody needs all of these, and together they run to tens of gigabytes, so the
/// first install is a choice rather than a download-everything. That choice has
/// to be revisable — deciding six weeks later that you want OpenFold-3 should not
/// mean reinstalling.
struct ComponentsView: View {
    @ObservedObject var installer: PipelineInstaller
    @State private var selection: Set<InstallComponent> = []
    @State private var weightsMessage: String?

    private var optional: [InstallComponent] {
        InstallComponent.allCases.filter { !$0.isCore }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header
                if installer.isInstalling { progress } else { list }
                alphaFoldWeights
            }
            .padding(28).frame(maxWidth: 720, alignment: .leading).frame(maxWidth: .infinity)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Engines").font(.largeTitle.bold())
            Text("Install only what you need. You can come back and add more at any time — nothing already installed is touched.")
                .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
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
                .disabled(selection.isEmpty)
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
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 8)
            .fill(installed ? Color.green.opacity(0.07) : Color.quaternaryLabelBackground))
    }

    // MARK: AlphaFold 3 weights

    @ViewBuilder private var alphaFoldWeights: some View {
        let state = installer.components[.alphafold3]
        let environmentReady = state != nil && state?.availability != .skipped
        if environmentReady && !installer.isUsable(.alphafold3) {
            VStack(alignment: .leading, spacing: 8) {
                Label("AlphaFold 3 needs its weights", systemImage: "key")
                    .font(.headline).foregroundStyle(.orange)
                Text("The parameter file is governed by Google's terms and cannot be downloaded for you. Request it from Google, then point Studio at the af3.bin file you receive — it will be copied into place.")
                    .font(.callout).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                HStack {
                    Button {
                        let panel = NSOpenPanel()
                        panel.allowsMultipleSelection = false
                        panel.canChooseDirectories = false
                        panel.message = "Choose af3.bin"
                        if panel.runModal() == .OK, let url = panel.url {
                            weightsMessage = installer.installAlphaFoldWeights(from: url)
                        }
                    } label: {
                        Label("Choose af3.bin…", systemImage: "folder")
                    }
                    .buttonStyle(.borderedProminent)
                    Link("Google's request form",
                         destination: URL(string: "https://github.com/google-deepmind/alphafold3")!)
                        .font(.callout)
                }
                if let weightsMessage {
                    Text(weightsMessage).font(.caption).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 10).fill(.orange.opacity(0.08)))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(.orange.opacity(0.3)))
        }
    }
}

extension Color {
    static var quaternaryLabelBackground: Color { Color(nsColor: .quaternaryLabelColor).opacity(0.12) }
}
