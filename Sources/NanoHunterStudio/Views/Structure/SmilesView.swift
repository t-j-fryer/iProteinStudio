import SwiftUI
import WebKit

/// Live 2D depiction of a SMILES string using the bundled (offline) SmilesDrawer.
/// Redraws as the string changes; shows "Invalid SMILES" for unparseable input.
struct SmilesView: NSViewRepresentable {
    let smiles: String

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> WKWebView {
        let web = WKWebView(frame: .zero)
        web.navigationDelegate = context.coordinator
        context.coordinator.web = web
        if let html = AppPaths.webRoot?.appendingPathComponent("mol/smiles2d.html"),
           let dir = AppPaths.webRoot?.appendingPathComponent("mol") {
            web.loadFileURL(html, allowingReadAccessTo: dir)
        }
        return web
    }

    func updateNSView(_ web: WKWebView, context: Context) {
        context.coordinator.draw(smiles)
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        weak var web: WKWebView?
        private var ready = false
        private var pending: String = ""
        private var lastDrawn: String?

        func webView(_ w: WKWebView, didFinish n: WKNavigation!) {
            // Inject the RDKit WASM bytes (fetch is blocked on file://).
            if let wasm = AppPaths.webRoot?.appendingPathComponent("mol/RDKit_minimal.wasm"),
               let data = try? Data(contentsOf: wasm) {
                let b64 = data.base64EncodedString()
                w.evaluateJavaScript("initRDKitWithWasm(\"\(b64)\")", completionHandler: nil)
            }
            ready = true
            draw(pending, force: true)
        }

        func draw(_ smiles: String, force: Bool = false) {
            pending = smiles
            guard ready, let web, force || smiles != lastDrawn else { return }
            lastDrawn = smiles
            let b64 = Data(smiles.utf8).base64EncodedString()
            web.evaluateJavaScript("drawSmilesB64(\"\(b64)\")", completionHandler: nil)
        }
    }
}
