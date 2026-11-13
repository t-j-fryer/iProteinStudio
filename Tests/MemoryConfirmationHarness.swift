import AppKit

/// Render this app-owned alert offscreen with a synthetic report; no workspace capture.
@main struct MemoryConfirmationHarness {
    @MainActor static func main() throws {
        _ = NSApplication.shared
        NSApp.setActivationPolicy(.prohibited)
        let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
        let review = try JSONDecoder().decode(PreparedMemoryRun.self, from: data)
        let alert = review.makeAlert()
        alert.layout()
        guard let view = alert.window.contentView,
              let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else {
            fatalError("Could not render memory confirmation")
        }
        view.cacheDisplay(in: view.bounds, to: bitmap)
        guard let png = bitmap.representation(using: .png, properties: [:]) else {
            fatalError("Could not encode memory confirmation")
        }
        try png.write(to: URL(fileURLWithPath: CommandLine.arguments[2]))
        precondition(alert.buttons.count == 2)
        precondition(alert.accessoryView is NSScrollView)
        precondition(view.bounds.width <= 700 && view.bounds.height <= 650)
        print("Rendered bounded memory confirmation with Proceed/Cancel; no dialog accepted or job submitted.")
    }
}
