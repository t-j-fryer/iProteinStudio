import Foundation
import Combine

struct MacPowerModeClient {
    var read: () async throws -> MacPowerSnapshot
    var apply: (PowerModeCommand) async throws -> Void

    static let live = Self(read: {
        try await Task.detached(priority: .utility) {
            let custom = try output(["-g", "custom"])
            let battery = try output(["-g", "batt"])
            let capabilities = try output(["-g", "cap"])
            return try MacPowerSnapshot.parse(custom: custom, battery: battery, capabilities: capabilities)
        }.value
    }, apply: { command in
        try await Task.detached(priority: .userInitiated) {
            let process = Process(); let pipe = Pipe()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
            process.arguments = ["-e", command.appleScript]
            process.standardOutput = FileHandle.nullDevice; process.standardError = pipe
            try process.run()
            let error = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
            process.waitUntilExit()
            guard process.terminationStatus == 0 else {
                throw error.contains("(-128)") ? PowerModeError.cancelled : PowerModeError.authorizationFailed
            }
        }.value
    })

    private static func output(_ arguments: [String]) throws -> String {
        let process = Process(); let pipe = Pipe()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/pmset")
        process.arguments = arguments
        process.standardOutput = pipe; process.standardError = FileHandle.nullDevice
        try process.run()
        let data = pipe.fileHandleForReading.readDataToEndOfFile(); process.waitUntilExit()
        guard process.terminationStatus == 0 else { throw PowerModeError.unreadable }
        return String(decoding: data, as: UTF8.self)
    }
}

@MainActor final class MacPowerModeService: ObservableObject {
    static let shared = MacPowerModeService(client: .live)
    @Published private(set) var snapshot: MacPowerSnapshot?
    @Published private(set) var busy = false
    @Published private(set) var changing = false
    @Published private(set) var error: String?
    private let client: MacPowerModeClient
    private var checkedAt = Date.distantPast
    private var observedHighSupport = false

    private func remember(_ state: MacPowerSnapshot) -> MacPowerSnapshot {
        observedHighSupport = observedHighSupport || state.highPowerReported
        return MacPowerSnapshot(source: state.source, adapterMode: state.adapterMode,
            batteryMode: state.batteryMode, highPowerReported: observedHighSupport, hasBattery: state.hasBattery)
    }

    init(client: MacPowerModeClient) { self.client = client }

    func refresh(force: Bool = false) async {
        guard !busy, !changing, force || Date().timeIntervalSince(checkedAt) > 5 else { return }
        busy = true; defer { busy = false }
        do { snapshot = remember(try await client.read()); error = nil; checkedAt = Date() }
        catch { snapshot = nil; self.error = error.localizedDescription }
    }

    func set(_ mode: MacEnergyMode) async {
        guard !changing, !busy else { return }
        changing = true; error = nil; snapshot = nil; defer { changing = false }
        do {
            let before = remember(try await client.read()); snapshot = before
            let command = try before.command(for: mode)
            guard before.adapterMode != mode else { return }
            try await client.apply(command)
            // A successful exit alone is not proof that the requested mode stuck.
            snapshot = nil
            let after = remember(try await client.read()); snapshot = after; checkedAt = Date()
            guard after.adapterMode == mode else { throw PowerModeError.notConfirmed }
        } catch { self.error = error.localizedDescription }
    }
}
