import AppKit
import Foundation
import SwiftUI

enum AIIntegrationClient: String, CaseIterable, Identifiable {
    case codex
    case claudeDesktop = "claude-desktop"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .codex: return "Codex"
        case .claudeDesktop: return "Claude Desktop"
        }
    }

    var detail: String {
        switch self {
        case .codex:
            return "Codex app, CLI and IDE integrations that share your user configuration."
        case .claudeDesktop:
            return "Claude's macOS desktop application. Claude Code has a separate project/CLI configuration."
        }
    }

    var applicationNames: [String] {
        switch self {
        case .codex: return ["Codex.app"]
        case .claudeDesktop: return ["Claude.app"]
        }
    }
}

enum AIIntegrationAccess: String, CaseIterable, Identifiable {
    case readOnly
    case readAndRun

    var id: String { rawValue }
    var label: String { self == .readOnly ? "Read only" : "Read and run workflows" }
    var profiles: String { self == .readOnly ? "read" : "read,run" }
}

struct AIClientConfiguration: Equatable {
    var configured = false
    var profiles: [String] = []
    var path = ""
    var invalid = false
}

struct AIRemoteGateway: Decodable, Equatable {
    var running: Bool
    var status: String?
    var profile: String?
    var port: Int?
    var local_endpoint: String?
    var credential_warning: String?
}

@MainActor
final class AIIntegrationService: ObservableObject {
    @Published var clients: [AIIntegrationClient: AIClientConfiguration] = [:]
    @Published var isWorking = false
    @Published var message: String?
    @Published var failure: String?
    @Published var remote = AIRemoteGateway(running: false)

    private struct RawClientConfiguration: Decodable {
        let configured: Bool
        let profiles: [String]
        let path: String
        let invalid: Bool?
    }

    private struct StatusReport: Decodable {
        let codex: RawClientConfiguration?
        let claude_desktop: RawClientConfiguration?
    }

    init() {
        clients = Dictionary(uniqueKeysWithValues: AIIntegrationClient.allCases.map { ($0, AIClientConfiguration()) })
    }

    func refresh() async {
        await perform(arguments: ["--client", "local-desktops", "--scope", "user", "--status"], success: nil)
        await refreshRemote()
    }

    func enable(_ client: AIIntegrationClient, access: AIIntegrationAccess) async {
        await perform(
            arguments: ["--client", client.rawValue, "--scope", "user", "--profiles", access.profiles, "--write"],
            success: "Enabled \(client.label). Restart it or open a new session so it reloads the MCP tools."
        )
    }

    func remove(_ client: AIIntegrationClient) async {
        await perform(
            arguments: ["--client", client.rawValue, "--scope", "user", "--remove", "--write"],
            success: "Removed iProteinStudio from \(client.label). Unrelated client settings were preserved."
        )
    }

    func open(_ client: AIIntegrationClient) {
        let roots = [URL(fileURLWithPath: "/Applications", isDirectory: true),
                     FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Applications", isDirectory: true)]
        for root in roots {
            for name in client.applicationNames {
                let candidate = root.appendingPathComponent(name, isDirectory: true)
                if FileManager.default.fileExists(atPath: candidate.path) {
                    NSWorkspace.shared.open(candidate)
                    return
                }
            }
        }
        failure = "\(client.label) was not found in an Applications folder. Its integration is still installed and will be available when the client is installed or restarted."
    }

    func testBridge() async {
        guard !isWorking else { return }
        isWorking = true
        failure = nil
        do {
            try AppPaths.stagePipelineAssets()
            let output = try await Self.runHelper(name: "studioctl.py", arguments: ["doctor"])
            guard let report = try JSONSerialization.jsonObject(with: Data(output.utf8)) as? [String: Any],
                  report["ok"] as? Bool == true else {
                throw NHError.message("The Studio bridge returned an invalid health report.")
            }
            message = "Studio's MCP bridge and versioned schemas are healthy. Restart the assistant after changing access."
        } catch {
            failure = error.localizedDescription
        }
        isWorking = false
    }

    func startRemote(access: AIIntegrationAccess) async {
        guard !isWorking else { return }
        isWorking = true
        failure = nil
        message = nil
        do {
            try AppPaths.stagePipelineAssets()
            let profile = access == .readOnly ? "read" : "run"
            let output = try await Self.runHelper(name: "remote_gateway.py", arguments: ["start", "--profile", profile])
            remote = try JSONDecoder().decode(AIRemoteGateway.self, from: Data(output.utf8))
            message = "Private gateway started. This Mac will remain awake until you stop it."
        } catch {
            failure = error.localizedDescription
        }
        isWorking = false
    }

    func stopRemote() async {
        guard !isWorking else { return }
        isWorking = true
        failure = nil
        do {
            let output = try await Self.runHelper(name: "remote_gateway.py", arguments: ["stop"])
            remote = try JSONDecoder().decode(AIRemoteGateway.self, from: Data(output.utf8))
            message = "Remote gateway stopped; its previous endpoint is no longer usable."
        } catch {
            failure = error.localizedDescription
        }
        isWorking = false
    }

    func chatGPTEndpoint(publicBase: String) -> String? {
        guard let base = URL(string: publicBase.trimmingCharacters(in: .whitespacesAndNewlines)),
              base.scheme == "https", base.host != nil,
              let local = remote.local_endpoint.flatMap(URL.init(string:)) else { return nil }
        let components = local.pathComponents.suffix(2)
        guard components.count == 2 else { return nil }
        return base.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/" + components.joined(separator: "/")
    }

    func copyChatGPTEndpoint(publicBase: String) {
        guard let endpoint = chatGPTEndpoint(publicBase: publicBase) else {
            failure = "Enter the public HTTPS address of a trusted tunnel or relay first."
            return
        }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(endpoint, forType: .string)
        message = "Copied the secret ChatGPT MCP endpoint. Treat it like a password."
    }

    private func refreshRemote() async {
        do {
            let output = try await Self.runHelper(name: "remote_gateway.py", arguments: ["status"])
            remote = try JSONDecoder().decode(AIRemoteGateway.self, from: Data(output.utf8))
        } catch {
            failure = error.localizedDescription
        }
    }

    private func perform(arguments: [String], success: String?) async {
        guard !isWorking else { return }
        isWorking = true
        failure = nil
        message = nil
        do {
            try AppPaths.stagePipelineAssets()
            let output = try await Self.runConfigure(arguments: arguments)
            if arguments.contains("--status") {
                let report = try JSONDecoder().decode(StatusReport.self, from: Data(output.utf8))
                if let value = report.codex {
                    clients[.codex] = AIClientConfiguration(configured: value.configured, profiles: value.profiles, path: value.path, invalid: value.invalid ?? false)
                }
                if let value = report.claude_desktop {
                    clients[.claudeDesktop] = AIClientConfiguration(configured: value.configured, profiles: value.profiles, path: value.path, invalid: value.invalid ?? false)
                }
            } else {
                message = success
                await refreshAfterMutation()
            }
        } catch {
            failure = error.localizedDescription
        }
        isWorking = false
    }

    private func refreshAfterMutation() async {
        do {
            let output = try await Self.runConfigure(arguments: ["--client", "local-desktops", "--scope", "user", "--status"])
            let report = try JSONDecoder().decode(StatusReport.self, from: Data(output.utf8))
            if let value = report.codex {
                clients[.codex] = AIClientConfiguration(configured: value.configured, profiles: value.profiles, path: value.path, invalid: value.invalid ?? false)
            }
            if let value = report.claude_desktop {
                clients[.claudeDesktop] = AIClientConfiguration(configured: value.configured, profiles: value.profiles, path: value.path, invalid: value.invalid ?? false)
            }
        } catch {
            failure = error.localizedDescription
        }
    }

    nonisolated private static func runConfigure(arguments: [String]) async throws -> String {
        try await runHelper(name: "configure.py", arguments: arguments)
    }

    nonisolated private static func runHelper(name: String, arguments: [String]) async throws -> String {
        try await Task.detached(priority: .utility) {
            let script = AppPaths.pipeline.appendingPathComponent("mcp/\(name)")
            guard FileManager.default.fileExists(atPath: script.path) else {
                throw NHError.message("The staged AI integration helper is missing. Reinstall iProteinStudio.")
            }
            let process = Process()
            let standardOutput = Pipe()
            let standardError = Pipe()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
            process.arguments = [script.path] + arguments
            var environment = ProcessInfo.processInfo.environment
            environment["NANOHUNTER_ROOT"] = AppPaths.support.path
            process.environment = environment
            process.standardOutput = standardOutput
            process.standardError = standardError
            try process.run()
            let outputData = standardOutput.fileHandleForReading.readDataToEndOfFile()
            let errorData = standardError.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            let output = String(decoding: outputData, as: UTF8.self)
            if process.terminationStatus != 0 {
                let detail = String(decoding: errorData, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
                throw NHError.message(detail.isEmpty ? "AI integration helper failed with status \(process.terminationStatus)." : detail)
            }
            return output
        }.value
    }
}

struct AIIntegrationsView: View {
    @StateObject private var service = AIIntegrationService()
    @State private var access: AIIntegrationAccess = .readOnly
    @State private var publicHTTPSBase = ""

    var body: some View {
        Form {
            Section {
                Text("Let an AI assistant inspect your installed engines and workspaces through typed tools. You decide whether it may also prepare and run workflows; engine administration is never enabled here.")
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Picker("Access", selection: $access) {
                    ForEach(AIIntegrationAccess.allCases) { option in
                        Text(option.label).tag(option)
                    }
                }
                Label("Enabling an assistant changes only its user MCP configuration. It does not share model weights or publish this Mac on the internet.", systemImage: "checkmark.shield")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Button("Test Studio bridge") { Task { await service.testBridge() } }
                    .controlSize(.small)
            } header: {
                Text("Local AI control")
            }

            Section("Desktop clients") {
                ForEach(AIIntegrationClient.allCases) { client in
                    clientRow(client)
                }
            }

            Section("ChatGPT and phone access") {
                Label(service.remote.running ? "Private gateway running" : "Secure remote gateway required",
                      systemImage: service.remote.running ? "network.badge.shield.half.filled" : "iphone.and.arrow.forward")
                    .font(.headline)
                Text("ChatGPT cannot invoke a local stdio process on your laptop from OpenAI's servers. Phone delegation requires an authenticated HTTPS MCP endpoint while this Mac is awake and reachable. iProteinStudio does not silently expose the gateway or your scientific tools.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                if service.remote.running {
                    LabeledContent("Gateway access") {
                        Text(service.remote.profile == "run" ? "read + run" : "read only")
                            .foregroundStyle(.green)
                    }
                    Text("The gateway currently listens only on this Mac. Forward local port \(service.remote.port ?? 8765) through a trusted HTTPS tunnel or hosted relay; never expose that port directly.")
                        .font(.caption).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    TextField("Public HTTPS address, for example https://studio.example.org", text: $publicHTTPSBase)
                    HStack {
                        Button("Copy ChatGPT endpoint") { service.copyChatGPTEndpoint(publicBase: publicHTTPSBase) }
                            .disabled(service.chatGPTEndpoint(publicBase: publicHTTPSBase) == nil)
                        Button("Stop gateway", role: .destructive) { Task { await service.stopRemote() } }
                    }
                    .controlSize(.small)
                } else {
                    Button(access == .readOnly ? "Start read-only private gateway" : "Start private run gateway") {
                        Task { await service.startRemote(access: access) }
                    }
                    .buttonStyle(.borderedProminent)
                    Text("Starting it keeps this Mac awake but does not make it internet-accessible. A public HTTPS relay/tunnel and ChatGPT-side approval are still required.")
                        .font(.caption2).foregroundStyle(.secondary)
                }
                Link("Open the ChatGPT app connection guide", destination: URL(string: "https://developers.openai.com/apps-sdk/deploy/connect-chatgpt")!)
            }

            if service.isWorking {
                HStack { ProgressView().controlSize(.small); Text("Updating integration…") }
            }
            if let message = service.message {
                Label(message, systemImage: "checkmark.circle.fill")
                    .font(.caption).foregroundStyle(.green)
            }
            if let failure = service.failure {
                Label(failure, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption).foregroundStyle(.orange)
                    .textSelection(.enabled)
            }
        }
        .formStyle(.grouped)
        .padding(12)
        .frame(width: 660, height: 590)
        .task { await service.refresh() }
    }

    @ViewBuilder
    private func clientRow(_ client: AIIntegrationClient) -> some View {
        let state = service.clients[client] ?? AIClientConfiguration()
        VStack(alignment: .leading, spacing: 7) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(client.label).font(.headline)
                    Text(client.detail).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if state.configured {
                    Text(state.profiles.contains("run") ? "read + run" : "read only")
                        .font(.caption.weight(.medium)).foregroundStyle(.green)
                } else {
                    Text(state.invalid ? "config needs repair" : "not enabled")
                        .font(.caption).foregroundStyle(state.invalid ? .orange : .secondary)
                }
            }
            HStack {
                if state.configured {
                    Button("Update access") { Task { await service.enable(client, access: access) } }
                    Button("Open client") { service.open(client) }
                    Button("Remove", role: .destructive) { Task { await service.remove(client) } }
                } else {
                    Button("Enable \(client.label)") { Task { await service.enable(client, access: access) } }
                        .buttonStyle(.borderedProminent)
                }
            }
            .controlSize(.small)
        }
        .padding(.vertical, 4)
    }
}
