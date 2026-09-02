import Combine
import AppKit
import Foundation
import Sparkle
import SwiftUI

/// Owns application updates only. Scientific engines, environments and model
/// checkpoints are deliberately managed by `PipelineInstaller` and can never be
/// pulled in by Sparkle.
@MainActor
final class AppUpdateService {
    let controller: SPUStandardUpdaterController
    let isConfigured: Bool
    let configurationProblem: String?
    let trustNotice: String?

    var updater: SPUUpdater { controller.updater }

    init(bundle: Bundle = .main) {
        let feed = bundle.object(forInfoDictionaryKey: "SUFeedURL") as? String
        let publicKey = bundle.object(forInfoDictionaryKey: "SUPublicEDKey") as? String
        let sparkleUpdateBuild = bundle.object(forInfoDictionaryKey: "IPStudioSparkleUpdateBuild") as? Bool == true
        let distributionChannel = bundle.object(forInfoDictionaryKey: "IPStudioDistributionChannel") as? String
        let feedIsSecure = feed.flatMap(URL.init(string:))?.scheme == "https"
        let keyLooksValid = (publicKey?.count ?? 0) >= 40

        if sparkleUpdateBuild && feedIsSecure && keyLooksValid {
            isConfigured = true
            configurationProblem = nil
            if distributionChannel == "unsigned-beta" {
                trustNotice = "Trusted beta channel: Sparkle verifies every update archive with the project's EdDSA key, but Apple has not verified or notarized this developer."
            } else {
                trustNotice = nil
            }
        } else {
            isConfigured = false
            trustNotice = nil
            configurationProblem = "This development build has no verified update feed. Install a distribution build to receive application updates."
        }

        controller = SPUStandardUpdaterController(
            startingUpdater: isConfigured,
            updaterDelegate: nil,
            userDriverDelegate: nil
        )
    }

    var versionDescription: String {
        let short = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "development"
        let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unversioned"
        return "Version \(short) (\(build))"
    }
}

@MainActor
private final class CheckForUpdatesViewModel: ObservableObject {
    @Published var canCheckForUpdates = false
    private var observation: AnyCancellable?

    init(service: AppUpdateService) {
        guard service.isConfigured else { return }
        observation = service.updater.publisher(for: \.canCheckForUpdates)
            .receive(on: RunLoop.main)
            .assign(to: \.canCheckForUpdates, on: self)
    }
}

struct CheckForUpdatesView: View {
    let service: AppUpdateService
    @StateObject private var model: CheckForUpdatesViewModel

    init(service: AppUpdateService) {
        self.service = service
        _model = StateObject(wrappedValue: CheckForUpdatesViewModel(service: service))
    }

    var body: some View {
        Button("Check for Updates…") { service.updater.checkForUpdates() }
            .disabled(!service.isConfigured || !model.canCheckForUpdates)
    }
}

/// Sparkle's two preferences are already backed by UserDefaults. Keep local
/// State only as UI glue and write back solely in response to user actions.
struct UpdateSettingsView: View {
    let service: AppUpdateService
    @State private var automaticallyChecksForUpdates: Bool
    @State private var automaticallyDownloadsUpdates: Bool
    @StateObject private var copies = ApplicationCopyManager()
    @State private var pendingTrash: ApplicationCopy?

    init(service: AppUpdateService) {
        self.service = service
        _automaticallyChecksForUpdates = State(initialValue: service.updater.automaticallyChecksForUpdates)
        _automaticallyDownloadsUpdates = State(initialValue: service.updater.automaticallyDownloadsUpdates)
    }

    var body: some View {
        Form {
            Section("Application updates") {
                Text(service.versionDescription)
                    .font(.callout.monospacedDigit())

                Toggle("Automatically check for app updates", isOn: $automaticallyChecksForUpdates)
                    .disabled(!service.isConfigured)
                    .onChange(of: automaticallyChecksForUpdates) { _, enabled in
                        service.updater.automaticallyChecksForUpdates = enabled
                    }

                Toggle("Download app updates automatically", isOn: $automaticallyDownloadsUpdates)
                    .disabled(!service.isConfigured || !automaticallyChecksForUpdates)
                    .onChange(of: automaticallyDownloadsUpdates) { _, enabled in
                        service.updater.automaticallyDownloadsUpdates = enabled
                    }

                CheckForUpdatesView(service: service)

                if let problem = service.configurationProblem {
                    Label(problem, systemImage: "hammer")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if let notice = service.trustNotice {
                    Label(notice, systemImage: "checkmark.shield")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Section("Engines and checkpoints") {
                Label("Never downloaded automatically", systemImage: "externaldrive.badge.xmark")
                    .font(.headline)
                Text("App updates contain the interface and bundled pipeline code only. A new engine or checkpoint is shown separately in Engines with its purpose and approximate disk cost, and downloads only after you confirm it.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Text("Updating the app never removes projects, results, saved alignments, environments or existing model weights.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Section("Application copies") {
                Text("Keep one current copy in Applications. Old copies can still appear in Spotlight and Finder and will not be replaced when a different copy updates.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                HStack {
                    Button { copies.scan() } label: {
                        Label(copies.isScanning ? "Searching…" : "Find other copies", systemImage: "magnifyingglass")
                    }
                    .disabled(copies.isScanning)
                    if copies.isScanning { ProgressView().controlSize(.small) }
                }

                ForEach(copies.copies) { copy in
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: copy.isCurrent ? "checkmark.seal.fill" : "app.dashed")
                            .foregroundStyle(copy.isCurrent ? .green : .orange)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(copy.isCurrent ? "Current copy — \(copy.version)" : "Other copy — \(copy.version)")
                                .font(.caption.weight(.medium))
                            Text(copy.path).font(.caption2.monospaced()).textSelection(.enabled)
                        }
                        Spacer()
                        Button("Reveal") { copies.reveal(copy) }.controlSize(.small)
                        if !copy.isCurrent {
                            Button("Move to Bin…", role: .destructive) { pendingTrash = copy }
                                .controlSize(.small)
                        }
                    }
                }

                if let failure = copies.failure {
                    Label(failure, systemImage: "exclamationmark.triangle")
                        .font(.caption).foregroundStyle(.orange)
                }
            }
        }
        .formStyle(.grouped)
        .padding(12)
        .frame(width: 620, height: 620)
        .alert(item: $pendingTrash) { copy in
            Alert(
                title: Text("Move this old app to the Bin?"),
                message: Text("Only \(copy.path) will be moved. Projects, engines and results under ~/.iproteinstudio are not touched."),
                primaryButton: .destructive(Text("Move to Bin")) { copies.moveToTrash(copy) },
                secondaryButton: .cancel()
            )
        }
    }
}

struct ApplicationCopy: Identifiable, Hashable {
    var id: String { path }
    let path: String
    let version: String
    let isCurrent: Bool
}

@MainActor
final class ApplicationCopyManager: ObservableObject {
    @Published var copies: [ApplicationCopy] = []
    @Published var isScanning = false
    @Published var failure: String?

    private let bundleID = "ai.nanohunter.studio"

    func scan() {
        guard !isScanning else { return }
        isScanning = true
        failure = nil
        let current = Bundle.main.bundleURL.standardizedFileURL.path
        let bundleID = bundleID

        Task.detached(priority: .utility) {
            let process = Process()
            let pipe = Pipe()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/mdfind")
            process.arguments = ["kMDItemCFBundleIdentifier == \"\(bundleID)\""]
            process.standardOutput = pipe
            process.standardError = FileHandle.nullDevice
            do {
                try process.run()
                process.waitUntilExit()
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                let output = String(decoding: data, as: UTF8.self)
                var paths = Set(output.split(separator: "\n").map(String.init))
                if current.hasSuffix(".app") { paths.insert(current) }
                let found = paths.compactMap { path -> ApplicationCopy? in
                    guard path.hasSuffix(".app"),
                          let bundle = Bundle(path: path),
                          bundle.bundleIdentifier == bundleID else { return nil }
                    let short = bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown version"
                    let build = bundle.object(forInfoDictionaryKey: "CFBundleVersion") as? String
                    let version = build.map { "\(short) (\($0))" } ?? short
                    return ApplicationCopy(path: path, version: version,
                                           isCurrent: URL(fileURLWithPath: path).standardizedFileURL.path == current)
                }.sorted { lhs, rhs in
                    if lhs.isCurrent != rhs.isCurrent { return lhs.isCurrent }
                    return lhs.path.localizedStandardCompare(rhs.path) == .orderedAscending
                }
                await MainActor.run {
                    self.copies = found
                    self.isScanning = false
                    if process.terminationStatus != 0 {
                        self.failure = "Spotlight could not complete the application search."
                    }
                }
            } catch {
                await MainActor.run {
                    self.isScanning = false
                    self.failure = "Could not search for application copies: \(error.localizedDescription)"
                }
            }
        }
    }

    func reveal(_ copy: ApplicationCopy) {
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: copy.path)])
    }

    func moveToTrash(_ copy: ApplicationCopy) {
        let current = Bundle.main.bundleURL.standardizedFileURL.path
        let url = URL(fileURLWithPath: copy.path).standardizedFileURL
        guard !copy.isCurrent, url.path != current, url.pathExtension == "app",
              let bundle = Bundle(url: url), bundle.bundleIdentifier == bundleID else {
            failure = "Studio refused to remove a path that is not a verified old iProteinStudio application."
            return
        }
        do {
            try FileManager.default.trashItem(at: url, resultingItemURL: nil)
            scan()
        } catch {
            failure = "Could not move the old copy to the Bin: \(error.localizedDescription)"
        }
    }
}

/// A signed distribution should run from /Applications (or the user's own
/// Applications directory), not a read-only DMG, Downloads, or an app-
/// translocation path where Sparkle may be unable to replace it.
struct ApplicationLocationNotice: ViewModifier {
    @State private var isPresented = ApplicationLocationNotice.shouldPrompt

    private static var shouldPrompt: Bool {
        guard Bundle.main.object(forInfoDictionaryKey: "IPStudioDistributionBuild") as? Bool == true else {
            return false
        }
        let path = Bundle.main.bundleURL.standardizedFileURL.path
        let userApplications = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Applications", isDirectory: true).path + "/"
        return !path.hasPrefix("/Applications/") && !path.hasPrefix(userApplications)
    }

    func body(content: Content) -> some View {
        content.alert("Move iProteinStudio to Applications", isPresented: $isPresented) {
            Button("Show this app in Finder") {
                NSWorkspace.shared.activateFileViewerSelecting([Bundle.main.bundleURL])
            }
            Button("Not now", role: .cancel) {}
        } message: {
            Text("This copy is not in an Applications folder. Move it there so macOS launches one canonical copy and signed updates can replace it reliably.")
        }
    }
}
