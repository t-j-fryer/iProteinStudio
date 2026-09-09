import SwiftUI
import AppKit

/// Shared by first-run Setup and later engine installation.
struct AppleBuildToolsHelpView: View {
    @ObservedObject var installer: PipelineInstaller
    @State private var settingsError: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Apple tools needed before setup", systemImage: "wrench.and.screwdriver")
                .font(.headline)
            Text("Some engine dependencies need Apple's Command Line Tools. This is a separate Apple download; you do not need the full Xcode app or Terminal.")
                .fixedSize(horizontal: false, vertical: true)
            Text("1. Choose Install Apple Tools and complete Apple's installation window.\n2. If macOS says the tools are already installed, check Software Update.\n3. When installation finishes, return here and choose Retry Setup.")
                .font(.callout).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            ViewThatFits(in: .horizontal) {
                HStack { installButton; softwareUpdateButton }
                VStack(alignment: .leading) { installButton; softwareUpdateButton }
            }
            if let message = installer.appleBuildToolsMessage {
                Text(message).font(.callout).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let settingsError { Text(settingsError).font(.callout).foregroundStyle(.orange) }
            HStack {
                Button("Retry Setup") { installer.retryAfterAppleBuildTools() }
                    .disabled(installer.isRequestingAppleBuildTools || installer.isRemoving)
                if let log = installer.latestLogURL {
                    Button("Show log") { NSWorkspace.shared.activateFileViewerSelecting([log]) }
                }
            }
            Text("Your selected engines are kept. Setup checks the compiler again before downloading anything.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 12).fill(.orange.opacity(0.08)))
    }

    private var installButton: some View {
        Button(installer.isRequestingAppleBuildTools ? "Opening Apple Installer…" : "Install Apple Tools") {
            installer.requestAppleBuildTools()
        }
        .buttonStyle(.borderedProminent)
        .disabled(installer.isRequestingAppleBuildTools || installer.isRemoving)
    }

    private var softwareUpdateButton: some View {
        Button("Open Software Update") {
            let url = URL(string: "x-apple.systempreferences:com.apple.Software-Update-Settings.extension")!
            settingsError = NSWorkspace.shared.open(url) ? nil
                : "Open System Settings, then General → Software Update."
        }
    }
}
