import SwiftUI
import AppKit

/// A partial result is actionable, never reported as a successful full install.
struct IncompleteSetupView: View {
    @ObservedObject var installer: PipelineInstaller

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Some components need another attempt", systemImage: "exclamationmark.triangle.fill")
                .font(.headline).foregroundStyle(.orange)
            Text("Setup continued with the other components. Available engines can be used; incomplete engines stay unavailable. Retry keeps verified files and resumes interrupted downloads.")
                .font(.callout).fixedSize(horizontal: false, vertical: true)
            ForEach(installer.failedComponents.keys.sorted(by: { $0.label < $1.label })) { component in
                VStack(alignment: .leading, spacing: 3) {
                    Text(component.label).font(.callout.bold())
                    Text(installer.failedComponents[component] ?? "")
                        .font(.caption).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            HStack {
                Button("Retry unfinished components") { installer.retryIncompleteComponents() }
                    .buttonStyle(.borderedProminent)
                if let log = installer.latestLogURL {
                    Button("Show setup log") { NSWorkspace.shared.activateFileViewerSelecting([log]) }
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
    }
}
