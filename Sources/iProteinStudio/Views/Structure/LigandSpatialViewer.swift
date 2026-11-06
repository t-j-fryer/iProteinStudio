import SwiftUI
import WebKit

/// Shared WebGL view for input conformers and recorded linker-exit samples.
struct LigandSpatialViewer: NSViewRepresentable {
    var payload: String
    var labels: [String] = []
    var conditions: [String: [String]] = [:]
    var attachment: Int?
    var linker: Int?
    var core: [Int] = []
    var presentation: [Int] = []
    var allowsPicking = false
    var onPick: ((Int?, Int?) -> Void)?

    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.userContentController.add(context.coordinator, name: "ligand3d")
        let web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = context.coordinator; context.coordinator.web = web
        if let root = AppPaths.webRoot?.appendingPathComponent("mol") {
            web.loadFileURL(root.appendingPathComponent("ligand3d.html"), allowingReadAccessTo: root)
        }
        return web
    }
    func updateNSView(_ web: WKWebView, context: Context) { context.coordinator.parent = self; context.coordinator.apply() }
    static func dismantleNSView(_ web: WKWebView, coordinator: Coordinator) { web.configuration.userContentController.removeScriptMessageHandler(forName: "ligand3d") }
    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var parent: LigandSpatialViewer
        weak var web: WKWebView?
        var ready = false
        var lastPayload: String?
        var lastState: String?
        init(_ parent: LigandSpatialViewer) { self.parent = parent }
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { ready = true; apply() }
        func apply() {
            guard ready, let web else { return }
            if parent.payload != lastPayload {
                lastPayload = parent.payload; lastState = nil
                web.evaluateJavaScript("loadPayloadB64(\"\(parent.payload)\")", completionHandler: nil)
            }
            let state: [String: Any] = ["labels": parent.labels, "conditions": parent.conditions,
                "attachment": parent.attachment ?? -1, "linker": parent.linker ?? -1,
                "core": parent.core, "presentation": parent.presentation, "picking": parent.allowsPicking]
            guard let data = try? JSONSerialization.data(withJSONObject: state, options: .sortedKeys) else { return }
            let b64 = data.base64EncodedString()
            guard b64 != lastState else { return }; lastState = b64
            web.evaluateJavaScript("setStateB64(\"\(b64)\")", completionHandler: nil)
        }
        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard let value = message.body as? [String: Int], let core = value["core"], let linker = value["linker"] else { return }
            DispatchQueue.main.async { self.parent.onPick?(core < 0 ? nil : core, linker < 0 ? nil : linker) }
        }
    }
}
