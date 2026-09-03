import AppKit
import Foundation
import WebKit

private final class NavigationWaiter: NSObject, WKNavigationDelegate {
    var loaded = false
    var failure: Error?

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        loaded = true
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!,
                 withError error: Error) {
        failure = error
        loaded = true
    }
}

@main
struct Py2DmolTrajectoryHarness {
    static func main() throws {
        guard CommandLine.arguments.count == 4 else {
            throw NSError(domain: "Py2DmolTrajectoryHarness", code: 1,
                          userInfo: [NSLocalizedDescriptionKey:
                            "usage: harness VIEWER_HTML CYCLE_0_STRUCTURE CYCLE_1_STRUCTURE"])
        }
        _ = NSApplication.shared
        NSApplication.shared.setActivationPolicy(.prohibited)

        let html = URL(fileURLWithPath: CommandLine.arguments[1])
        let paths = Array(CommandLine.arguments[2...3])
        let payload = try paths.enumerated().map { index, path -> [String: String] in
            let data = try Data(contentsOf: URL(fileURLWithPath: path))
            return [
                "encoded": data.base64EncodedString(),
                "format": path.lowercased().hasSuffix(".pdb") ? "pdb" : "cif",
                "name": index == 0 ? "Starting structure" : "Cycle 01",
            ]
        }
        let payloadData = try JSONSerialization.data(withJSONObject: payload)
        let payloadJSON = String(decoding: payloadData, as: UTF8.self)

        let configuration = WKWebViewConfiguration()
        let web = WKWebView(frame: NSRect(x: 0, y: 0, width: 900, height: 650),
                            configuration: configuration)
        let waiter = NavigationWaiter()
        web.navigationDelegate = waiter
        web.loadFileURL(html, allowingReadAccessTo: html.deletingLastPathComponent())
        try wait(until: { waiter.loaded }, timeout: 15)
        if let failure = waiter.failure { throw failure }

        let rigidFit = try evaluate(
            "studioRigidFitMaximumDeviation([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],"
                + "[[5,2,3],[5,3,3],[4,2,3],[5,2,4]])",
            in: web, timeout: 5)
        guard let rigidDeviation = (rigidFit as? NSNumber)?.doubleValue,
              rigidDeviation < 1e-8 else {
            throw NSError(domain: "Py2DmolTrajectoryHarness", code: 5,
                          userInfo: [NSLocalizedDescriptionKey:
                            "dependency-free rigid fit failed its rotated synthetic case: \(String(describing: rigidFit))"])
        }

        let loadResult = try evaluate(
            "studioLoadTrajectoryB64(\(payloadJSON), true)", in: web, timeout: 15)
        guard let result = loadResult as? [String: Any],
              result["ok"] as? Bool == true,
              (result["frames"] as? NSNumber)?.intValue == 2,
              ((result["targetPositions"] as? NSNumber)?.intValue ?? 0) >= 3,
              result["alignmentImproved"] as? Bool == true,
              ((result["maximumTargetDeviation"] as? NSNumber)?.doubleValue ?? .infinity).isFinite else {
            throw NSError(domain: "Py2DmolTrajectoryHarness", code: 2,
                          userInfo: [NSLocalizedDescriptionKey:
                            "trajectory did not load or target alignment was not exact: \(String(describing: loadResult))"])
        }

        // Let the adapter's microtask update the human-readable cycle label.
        RunLoop.current.run(until: Date().addingTimeInterval(0.1))
        let controls = try evaluate(
            "({max:document.getElementById('frameSlider').max,"
                + "counter:document.getElementById('frameCounter').textContent})",
            in: web, timeout: 5)
        guard let values = controls as? [String: Any],
              String(describing: values["max"] ?? "") == "1",
              String(describing: values["counter"] ?? "").contains("Starting structure") else {
            throw NSError(domain: "Py2DmolTrajectoryHarness", code: 3,
                          userInfo: [NSLocalizedDescriptionKey:
                            "trajectory scrubber was not labelled by cycle: \(String(describing: controls))"])
        }
        print("PASS py2Dmol target-aligned iterative trajectory")
    }

    private static func evaluate(_ script: String, in web: WKWebView,
                                 timeout: TimeInterval) throws -> Any? {
        var finished = false
        var value: Any?
        var failure: Error?
        web.evaluateJavaScript(script) { result, error in
            value = result
            failure = error
            finished = true
        }
        try wait(until: { finished }, timeout: timeout)
        if let failure { throw failure }
        return value
    }

    private static func wait(until predicate: () -> Bool,
                             timeout: TimeInterval) throws {
        let deadline = Date().addingTimeInterval(timeout)
        while !predicate(), Date() < deadline {
            RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.02))
        }
        if !predicate() {
            throw NSError(domain: "Py2DmolTrajectoryHarness", code: 4,
                          userInfo: [NSLocalizedDescriptionKey: "timed out waiting for WebKit"])
        }
    }
}
