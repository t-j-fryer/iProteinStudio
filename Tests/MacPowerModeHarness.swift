import Foundation

@MainActor final class PowerFixture {
    var current: MacPowerSnapshot
    var commands: [PowerModeCommand] = []
    var failure: PowerModeError?
    var confirms = true
    var reportsAfterChange: Bool?
    init(_ snapshot: MacPowerSnapshot) { current = snapshot }
    func read() async throws -> MacPowerSnapshot { current }
    func apply(_ command: PowerModeCommand) async throws {
        commands.append(command)
        if let failure { throw failure }
        if confirms {
            current = MacPowerSnapshot(source: current.source, adapterMode: command.mode,
                batteryMode: current.batteryMode, highPowerReported: reportsAfterChange ?? current.highPowerReported, hasBattery: current.hasBattery)
        }
    }
    var client: MacPowerModeClient {
        MacPowerModeClient(read: { try await self.read() }, apply: { try await self.apply($0) })
    }
}

@main struct MacPowerModeHarness {
    @MainActor static func main() async throws {
        if CommandLine.arguments.contains("--read-only-host") {
            let state = try await MacPowerModeClient.live.read()
            print("READ ONLY: \(state.summary); High Power reported: \(state.highPowerReported)")
            return
        }
        let ac = "Now drawing from 'AC Power'\n -InternalBattery-0 100%"
        let battery = "Now drawing from 'Battery Power'\n -InternalBattery-0 75%"
        let modern = "Battery Power:\n powermode 1\nAC Power:\n powermode 0\n sleep 1\n displaysleep 10\n"
        let automatic = try MacPowerSnapshot.parse(custom: modern, battery: ac, capabilities: "lowpowermode\nhighpowermode")
        precondition(automatic.activeMode == .automatic && automatic.batteryMode == .low && automatic.canEnableHigh)
        let high = try MacPowerSnapshot.parse(custom: "AC Power:\n lowpowermode 2\n", battery: ac, capabilities: "lowpowermode")
        precondition(high.activeMode == .high && !high.canEnableHigh && high.highPowerReported)
        let onBattery = try MacPowerSnapshot.parse(custom: modern, battery: battery, capabilities: "highpowermode")
        precondition(onBattery.activeMode == .low && !onBattery.canEnableHigh)
        do { _ = try onBattery.command(for: .high); preconditionFailure("Battery mutation was allowed") } catch PowerModeError.connectAdapter { }
        let noHigh = try MacPowerSnapshot.parse(custom: "AC Power:\n lowpowermode 0\n", battery: ac, capabilities: "lowpowermode")
        precondition(!noHigh.highPowerReported && !noHigh.canEnableHigh)
        do { _ = try noHigh.command(for: .high); preconditionFailure("Unreported support was guessed") } catch PowerModeError.notReported { }
        let unknownSource = try MacPowerSnapshot.parse(custom: modern, battery: "unrecognized source", capabilities: "highpowermode")
        precondition(unknownSource.activeMode == nil && !unknownSource.canEnableHigh)
        let desktop = try MacPowerSnapshot.parse(custom: "AC Power:\n powermode 0\n", battery: "Now drawing from 'AC Power'", capabilities: "highpowermode")
        precondition(!desktop.hasBattery && desktop.canEnableHigh)
        for invalid in ["", "AC Power:\n powermode 7\n", "AC Power:\n powermode 0\n lowpowermode 2\n", "AC Power:\n powermode 0\n powermode 2\n"] {
            do { _ = try MacPowerSnapshot.parse(custom: invalid, battery: ac, capabilities: ""); preconditionFailure("Invalid state accepted") } catch PowerModeError.unreadable { }
        }
        let command = try automatic.command(for: .high)
        precondition(command.shell == "/usr/bin/pmset -c powermode 2")
        precondition(!command.shell.contains("-a") && !command.shell.contains("-b"))
        precondition(command.appleScript.contains("with administrator privileges") && command.appleScript.contains("whole Mac"))
        // Compile the production authorization script without executing it.
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("studio-power-\(UUID()).scpt")
        defer { try? FileManager.default.removeItem(at: file) }
        let compiler = Process(); compiler.executableURL = URL(fileURLWithPath: "/usr/bin/osacompile")
        compiler.arguments = ["-o", file.path, "-e", command.appleScript]
        try compiler.run(); compiler.waitUntilExit(); precondition(compiler.terminationStatus == 0)
        let fixture = PowerFixture(automatic), service = MacPowerModeService(client: PowerFixture(automatic).client)
        await service.refresh(force: true)
        precondition(service.snapshot == automatic && service.error == nil)
        let control = MacPowerModeService(client: fixture.client)
        await control.set(.high)
        precondition(control.snapshot?.adapterMode == .high && control.snapshot?.batteryMode == .low && control.error == nil)
        precondition(fixture.commands == [command])
        await control.set(.high)
        precondition(fixture.commands.count == 1, "Already-enabled mode requested authorization")
        await control.set(.automatic)
        precondition(fixture.commands.last?.shell == "/usr/bin/pmset -c powermode 0" && control.error == nil)
        let legacy = PowerFixture(high); legacy.reportsAfterChange = false
        let legacyControl = MacPowerModeService(client: legacy.client)
        await legacyControl.refresh(force: true)
        await legacyControl.set(.automatic)
        precondition(legacyControl.snapshot?.canEnableHigh == true, "Observed support was lost when Automatic was chosen")
        await legacyControl.set(.high)
        precondition(legacyControl.snapshot?.adapterMode == .high && legacyControl.error == nil)
        let cancelled = PowerFixture(automatic); cancelled.failure = .cancelled
        let cancelledControl = MacPowerModeService(client: cancelled.client)
        await cancelledControl.set(.high)
        precondition(cancelledControl.snapshot?.adapterMode == .automatic && cancelledControl.error == PowerModeError.cancelled.localizedDescription)
        let failed = PowerFixture(automatic); failed.failure = .authorizationFailed
        let failedControl = MacPowerModeService(client: failed.client)
        await failedControl.set(.high)
        precondition(failedControl.error != nil && failedControl.snapshot?.adapterMode == .automatic)
        let unconfirmed = PowerFixture(automatic); unconfirmed.confirms = false
        let unconfirmedControl = MacPowerModeService(client: unconfirmed.client)
        await unconfirmedControl.set(.high)
        precondition(unconfirmedControl.error == PowerModeError.notConfirmed.localizedDescription && unconfirmedControl.snapshot?.adapterMode != .high)
        let unplugged = PowerFixture(onBattery); let unpluggedControl = MacPowerModeService(client: unplugged.client)
        await unpluggedControl.set(.high)
        precondition(unplugged.commands.isEmpty && unpluggedControl.error != nil)
        let unknown = MacPowerModeService(client: .init(read: { throw PowerModeError.unreadable }, apply: { _ in preconditionFailure("Unexpected privileged call") }))
        await unknown.refresh(force: true)
        precondition(unknown.snapshot == nil && unknown.error != nil)
        print("PASS power-mode parsing, AC-only commands, AppleScript compilation, readback, no-op, cancellation, denial, unsupported/unknown states and Automatic control; no host setting changed")
    }
}
