import AppKit
import SwiftUI

@main struct MacPowerModePreviewHarness {
    @MainActor static func main() {
        let mode: MacEnergyMode = CommandLine.arguments.contains("--high") ? .high : .automatic
        let snapshot = MacPowerSnapshot(source: .adapter, adapterMode: mode, batteryMode: .low, highPowerReported: true, hasBattery: true)
        let client = MacPowerModeClient(read: { snapshot }, apply: { _ in fatalError("Preview must never request authorization") })
        let power = MacPowerModeService(client: client)
        let app = NSApplication.shared; app.setActivationPolicy(.accessory)
        let root = NSHostingView(rootView: MacPowerModeControl(power: power).padding(18).background(Color.white).preferredColorScheme(.light).frame(width: 580, height: 360, alignment: .topLeading))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 580, height: 370),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.contentView = root; window.title = "Mac power controls — fixture only"
        window.makeKeyAndOrderFront(nil)
        Task {
            await power.refresh(force: true)
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                precondition(power.snapshot == snapshot)
                root.layoutSubtreeIfNeeded()
                let number = window.windowNumber
                DispatchQueue.global().async {
                    let capture = Process()
                    capture.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
                    // Capture only this synthetic window, never another app or the desktop.
                    capture.arguments = ["-x", "-o", "-l", String(number), CommandLine.arguments[1]]
                    try! capture.run(); capture.waitUntilExit()
                    print("Native fixture capture exit: \(capture.terminationStatus); no host or authorization action")
                    exit(capture.terminationStatus)
                }
            }
        }
        app.run()
    }
}
