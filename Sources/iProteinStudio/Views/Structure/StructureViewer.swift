import SwiftUI
import WebKit

/// Renders an mmCIF structure with the bundled offline 3Dmol.js.
struct StructureViewer: NSViewRepresentable {
    /// Path to a .cif/.pdb file to display (nil shows an empty viewer).
    let structurePath: String?

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> WKWebView {
        let web = WKWebView(frame: .zero)
        context.coordinator.web = web
        if let viewerURL = AppPaths.webRoot?.appendingPathComponent("mol/viewer.html"),
           let dir = AppPaths.webRoot?.appendingPathComponent("mol") {
            web.loadFileURL(viewerURL, allowingReadAccessTo: dir)
        }
        web.navigationDelegate = context.coordinator
        return web
    }

    func updateNSView(_ web: WKWebView, context: Context) {
        context.coordinator.pending = structurePath
        context.coordinator.loadIfReady()
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        weak var web: WKWebView?
        var pending: String?
        private var ready = false

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            ready = true
            loadIfReady()
        }

        func loadIfReady() {
            guard ready, let web, let path = pending,
                  let data = FileManager.default.contents(atPath: path) else { return }
            let b64 = data.base64EncodedString()
            let fmt = path.lowercased().hasSuffix(".pdb") ? "pdb" : "cif"
            web.evaluateJavaScript("loadStructureB64(\"\(b64)\", \"\(fmt)\");", completionHandler: nil)
        }
    }
}
