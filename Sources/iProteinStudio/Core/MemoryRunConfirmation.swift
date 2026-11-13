import AppKit

/// A review belongs to one frozen plan and one estimate. No app-wide override.
struct PreparedMemoryRun: Decodable {
    let plan_id: String
    let plan_sha256: String
    let report_sha256: String
    let message: String
    let warning: Bool

    @MainActor
    func makeAlert() -> NSAlert {
        let alert = NSAlert()
        alert.messageText = "Review estimated memory use"
        alert.informativeText = "Review the estimated prediction peak and any stages with unknown memory use before continuing."
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 540, height: 320))
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder
        let text = NSTextView(frame: scroll.bounds)
        text.isEditable = false
        text.isSelectable = true
        text.font = .systemFont(ofSize: NSFont.systemFontSize)
        text.textContainerInset = NSSize(width: 8, height: 8)
        text.isVerticallyResizable = true
        text.isHorizontallyResizable = false
        text.autoresizingMask = [.width]
        text.textContainer?.widthTracksTextView = true
        text.string = message
        scroll.documentView = text
        alert.accessoryView = scroll
        alert.alertStyle = warning ? .warning : .informational
        alert.addButton(withTitle: "Proceed")
        alert.addButton(withTitle: "Cancel")
        alert.buttons.last?.keyEquivalent = "\u{1b}"
        return alert
    }

    @MainActor
    func confirm() -> Bool {
        makeAlert().runModal() == .alertFirstButtonReturn
    }
}
