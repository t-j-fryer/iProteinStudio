// Render the production view with inert fixtures; never load the app or broker.
import AppKit
import SwiftUI
import Combine

struct ManagedJob {
    let display_name: String? = "Example stopped calibration"
    let workflowLabel = "Protein Hunter"
    let displayStatus = "Failed"
    let message: String? = "The worker stopped before recording completion. Saved results were kept."
    let output: URL? = nil
    let id = "job-preview-fixture"
}

struct JobRecoveryReport {
    let action = "cleanup"
    let message = "2 leftover job processes can be stopped safely. Saved inputs, results and checkpoints will be kept."
    let process_ids = [101, 102]
    let execution_lock_busy = true
}

@MainActor final class JobDetailModel: ObservableObject {
    @Published var job: ManagedJob
    @Published var lines = [
        "Calibration: preparing the target alignment and template",
        "Model checkpoint loaded; inputs prepared",
        "IPROTEINSTUDIO_PROGRESS|engine=protenix|event=host_enter|stage=template_embedding|pid=101|utc=2026-09-25T10:09:37Z|call=1",
        "IPROTEINSTUDIO_PROGRESS|engine=protenix|event=heartbeat|stage=template_embedding|pid=101|utc=2026-09-25T10:10:07Z|call=1|elapsed_s=30|since_host_progress_s=30|compute_progress=unknown",
    ]
    @Published var workerLines = ["Synthetic preview; no engine process exists."]
    @Published var recovery: JobRecoveryReport? = JobRecoveryReport()
    @Published var error: String? = nil
    @Published var busy = false
    init(job: ManagedJob) { self.job = job }
    func refresh() async {}
    func checkRecovery() async {}
    func cleanUp() async {}
}

@main struct Preview {
    @MainActor static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        let view = NSHostingView(rootView: JobProgressView(job: ManagedJob()).preferredColorScheme(.light))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 880, height: 740),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.contentView = view
        window.title = "Studio viewer preview — synthetic data"
        window.center()
        window.orderFrontRegardless()
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
            let number = window.windowNumber
            DispatchQueue.global().async {
                let capture = Process()
                capture.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
                capture.arguments = ["-x", "-o", "-l", String(number), CommandLine.arguments[1]]
                try! capture.run()
                capture.waitUntilExit()
                exit(capture.terminationStatus)
            }
        }
        app.run()
    }
}
