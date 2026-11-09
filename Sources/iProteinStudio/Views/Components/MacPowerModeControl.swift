import SwiftUI
import AppKit
import Combine

struct MacPowerModeControl: View {
    @ObservedObject var power = MacPowerModeService.shared
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(power.snapshot?.summary ?? (power.error == nil ? "Reading Mac power mode…" : "Mac power mode unavailable"), systemImage: "bolt.fill")
                .font(.callout.weight(.semibold))
            Text("High Power can improve sustained performance by allowing more cooling. It can increase fan noise and energy use. Availability depends on your Mac.")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            HStack {
                Button("Enable High Power on power adapter") { Task { await power.set(.high) } }
                    .disabled(power.changing || power.busy || power.snapshot?.canEnableHigh != true)
                    .accessibilityIdentifier("enable-mac-high-power")
                if power.snapshot?.source == .adapter, let mode = power.snapshot?.adapterMode, mode != .automatic {
                    Button("Use Automatic") { Task { await power.set(.automatic) } }
                        .disabled(power.changing || power.busy)
                }
            }
            if power.snapshot?.adapterMode == .high {
                Text(power.snapshot?.source == .adapter ? "High Power is already enabled for the active power adapter." : "High Power is configured for the power adapter; the Mac is currently using another power source.")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            } else if let snapshot = power.snapshot, !snapshot.highPowerReported {
                Text("High Power support is not reported to Studio. Check the modes available in Power Settings.").font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            } else if power.snapshot?.source != .adapter {
                Text("Connect the power adapter to enable the shortcut.").font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            Text("Changes apply to the whole Mac across all workflows and remain until changed. Battery settings stay unchanged. macOS may request administrator approval.")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            HStack {
                Button("Open Power Settings") { openSettings() }
                Button("Refresh") { Task { await power.refresh(force: true) } }.disabled(power.changing || power.busy)
                Link("Apple power-mode guidance", destination: URL(string: "https://support.apple.com/101613")!)
            }.font(.caption)
            if power.changing { ProgressView("Waiting for macOS and verifying the change…").font(.caption) }
            if let error = power.error { Text(error).font(.caption).foregroundStyle(.orange).fixedSize(horizontal: false, vertical: true) }
        }
        .accessibilityIdentifier("mac-power-mode-control")
        .task { await power.refresh() }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in Task { await power.refresh(force: true) } }
    }
    private func openSettings() {
        let pane = power.snapshot?.hasBattery == false ? "energysaver" : "battery"
        let url = URL(string: "x-apple.systempreferences:com.apple.preference.\(pane)")!
        if !NSWorkspace.shared.open(url) { NSWorkspace.shared.open(URL(fileURLWithPath: "/System/Applications/System Settings.app")) }
    }
}

struct MacPowerModeToolbar: View {
    @ObservedObject private var power = MacPowerModeService.shared
    @State private var showing = false
    private let timer = Timer.publish(every: 20, on: .main, in: .common).autoconnect()
    var body: some View {
        Button { showing.toggle() } label: {
            Label(power.snapshot?.activeMode?.label ?? "Power mode", systemImage: "bolt.fill")
        }
        .help("Mac power mode: \(power.snapshot?.summary ?? "not yet read")")
        .accessibilityIdentifier("mac-power-mode-toolbar")
        .popover(isPresented: $showing) { MacPowerModeControl().padding(18).frame(width: 520) }
        .task { await power.refresh() }
        .onReceive(timer) { _ in Task { await power.refresh() } }
    }
}
