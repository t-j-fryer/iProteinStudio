import AppKit
import SwiftUI
import CryptoKit

enum StudioWorkflow: String, Codable { case iterative, prediction, nise, rfd4, rfdiffusion3; var label: String { rawValue } }

// Minimal group-only loader adapter for an isolated UI build with
// Core/Results/ResultPresentationModel.swift and Models/ResultPage.swift.
enum RunResultsLoader {
    static func groups(from items: [StudioResultItem]) -> [StudioResultGroup] {
        Dictionary(grouping: items, by: \.groupID).map {
            StudioResultGroup(id: $0.key, title: $0.value.first?.groupTitle ?? $0.key, items: $0.value)
        }
    }
}

// This display-only adapter deliberately starts no analysis process.
@MainActor final class ResultSpatialController: ObservableObject {
    @Published var rows: [String: ResultSpatialRow] = [:]
    @Published var samples: [ResultSpatialRow] = []
    @Published var failures: [String] = []
    @Published var busy = false
    @Published var message: String?
    @Published var inventory: String?
    func inspect(_ source: URL) {}
    func run(candidates: [ResultCandidate], policy: ResultSpatialPolicy) {}
    func cancel() {}
}

// Render the production review controls without any real structure or WebKit.
struct StudioResultGroupDetail: View {
    let group: StudioResultGroup
    let hitsOnly: Bool
    var body: some View {
        VStack(alignment: .leading) {
            Text(group.title).font(.headline)
            Text("Synthetic structure detail placeholder").foregroundStyle(.secondary)
            Spacer()
        }.padding().frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

@main
struct ResultReviewPreviewHarness {
    @MainActor static var retainedWindow: NSWindow?
    @MainActor static func main() throws {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        let root = URL(fileURLWithPath: "/synthetic-review/" + UUID().uuidString)
        let key = "results.hitReview." + SHA256.hash(data: Data(root.standardizedFileURL.path.utf8)).map { String(format: "%02x", $0) }.joined()
        defer { UserDefaults.standard.removeObject(forKey: key) }
        var policy = ResultHitPolicy()
        policy.mode = .custom
        policy.rules = [.init(metric: .ipsaeMinimum, threshold: "0.3"), .init(metric: .complexRMSD, comparison: .maximum, threshold: "2.0")]
        policy.maxPerFamily = "2"
        UserDefaults.standard.set(try JSONEncoder().encode(policy), forKey: key)
        let items = (1...9).map { n in
            StudioResultItem(id: "candidate-\(n)", title: "Candidate \(n)", subtitle: "Synthetic fixture", structureURL: root,
                sequence: "GASGAS", metrics: [.init(kind: .ipsaeMinimum, value: Double(n) / 10), .init(kind: .complexRMSD, value: 1.5)],
                confidenceURL: nil, stage: .design, scoreSource: "Boltz 2", isHit: n > 6,
                groupID: "family-\((n-1)/3)", groupTitle: "Family \((n-1)/3 + 1)", variantID: "candidate-\(n)",
                variantTitle: "Candidate \(n)", artifactRole: .designedComplex, cycle: (n-1)/3 + 1)
        }
        let content = VStack(spacing: 0) {
            ResultCycleMedianChart(items: items, metric: .ipsaeMinimum).frame(height: 320)
            Divider()
            ResultHitReviewView(items: items, root: root)
        }.frame(width: 1120, height: 900)
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1120, height: 900),
            styleMask: [.titled], backing: .buffered, defer: false)
        retainedWindow = window
        window.title = "Results review — synthetic fixtures"
        let host = NSHostingView(rootView: content)
        window.contentView = host
        window.center()
        window.orderFrontRegardless()
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            let number = window.windowNumber
            DispatchQueue.global().async {
                let capture = Process()
                capture.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
                capture.arguments = ["-x", "-o", "-l", String(number), CommandLine.arguments[1]]
                do {
                    try capture.run(); capture.waitUntilExit()
                    UserDefaults.standard.removeObject(forKey: key)
                    if capture.terminationStatus == 0 {
                        print("PASS rendered production review controls and cycle chart using synthetic fixtures")
                    }
                    exit(capture.terminationStatus)
                } catch {
                    UserDefaults.standard.removeObject(forKey: key)
                    fputs("Synthetic-window capture failed: \(error)\n", stderr)
                    exit(1)
                }
            }
        }
        app.run()
    }
}
