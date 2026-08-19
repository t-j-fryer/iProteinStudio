import SwiftUI
import WebKit

/// A clickable 2D depiction: the user points at both ends of the directed
/// core-to-linker bond instead of typing ambiguous indices.
///
/// This matters more than it looks. Getting the attachment point wrong makes the
/// linker count as recognition core, so its flexibility dominates the conformer
/// analysis and the design budget gets spread across shapes that differ only in
/// a floppy tail. A typed index gives the user no way to tell they got it wrong;
/// a picture they clicked, shaded afterwards with the split that was actually
/// used, does.
struct LigandAtomPicker: NSViewRepresentable {
    let smiles: String
    /// Core-side endpoint of the selected acyclic core-to-linker bond.
    @Binding var attachmentAtom: Int?
    /// Linker-side endpoint directly bonded to `attachmentAtom`.
    @Binding var attachmentLinkerAtom: Int?
    /// Atoms the analysis treated as recognition core / presentation region.
    var coreAtoms: [Int] = []
    var presentationAtoms: [Int] = []
    /// RFD3 atom names in original SMILES order. When unavailable, the drawing
    /// shows zero-based indices rather than inventing a mapping.
    var atomLabels: [String] = []
    var allowsAttachmentPicking = true
    /// Reports the atom symbols in index order, so a mismatch between the
    /// depiction's atom numbering and the analysis's can be caught rather than
    /// silently producing a nonsense split.
    var onAtomsResolved: (([String]) -> Void)?

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.userContentController.add(context.coordinator, name: "ligand")
        let web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = context.coordinator
        web.setValue(false, forKey: "drawsBackground")
        context.coordinator.web = web
        if let html = AppPaths.webRoot?.appendingPathComponent("mol/ligandpicker.html"),
           let dir = AppPaths.webRoot?.appendingPathComponent("mol") {
            web.loadFileURL(html, allowingReadAccessTo: dir)
        }
        return web
    }

    func updateNSView(_ web: WKWebView, context: Context) {
        context.coordinator.parent = self
        context.coordinator.draw(smiles)
        context.coordinator.apply(attachment: attachmentAtom,
                                  linker: attachmentLinkerAtom,
                                  core: coreAtoms, presentation: presentationAtoms,
                                  labels: atomLabels, picking: allowsAttachmentPicking)
    }

    static func dismantleNSView(_ web: WKWebView, coordinator: Coordinator) {
        web.configuration.userContentController.removeScriptMessageHandler(forName: "ligand")
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var parent: LigandAtomPicker
        weak var web: WKWebView?
        private var ready = false
        private var pending: String = ""
        private var lastDrawn: String?
        private var lastState: String = ""

        init(_ parent: LigandAtomPicker) { self.parent = parent }

        func webView(_ w: WKWebView, didFinish n: WKNavigation!) {
            // Inject the RDKit WASM bytes — fetch() is blocked on file:// URLs.
            if let wasm = AppPaths.webRoot?.appendingPathComponent("mol/RDKit_minimal.wasm"),
               let data = try? Data(contentsOf: wasm) {
                w.evaluateJavaScript("initRDKitWithWasm(\"\(data.base64EncodedString())\")",
                                     completionHandler: nil)
            }
        }

        func draw(_ smiles: String, force: Bool = false) {
            pending = smiles
            guard ready, let web, force || smiles != lastDrawn else { return }
            lastDrawn = smiles
            lastState = ""      // a new molecule invalidates any shading
            let b64 = Data(smiles.utf8).base64EncodedString()
            web.evaluateJavaScript("drawSmilesB64(\"\(b64)\")", completionHandler: nil)
        }

        func apply(attachment: Int?, linker: Int?, core: [Int], presentation: [Int],
                   labels: [String], picking: Bool) {
            guard ready, let web else { return }
            // Cheap change detection: these fire on every SwiftUI update, and
            // re-running the JS would fight the user's own clicks.
            let signature = "\(attachment ?? -1)|\(linker ?? -1)|\(core)|\(presentation)|\(labels)|\(picking)"
            guard signature != lastState else { return }
            lastState = signature

            web.evaluateJavaScript("setAttachment(\(attachment ?? -1), \(linker ?? -1))",
                                   completionHandler: nil)
            web.evaluateJavaScript("setPickingEnabled(\(picking ? "true" : "false"))",
                                   completionHandler: nil)
            let coreJSON = (try? String(data: JSONEncoder().encode(core), encoding: .utf8)) ?? "[]"
            let presJSON = (try? String(data: JSONEncoder().encode(presentation), encoding: .utf8)) ?? "[]"
            let labelsJSON = (try? String(data: JSONEncoder().encode(labels), encoding: .utf8)) ?? "[]"
            web.evaluateJavaScript("setAtomLabels('\(labelsJSON)')", completionHandler: nil)
            if core.isEmpty && presentation.isEmpty {
                web.evaluateJavaScript("setRegions(null, null)", completionHandler: nil)
            } else {
                web.evaluateJavaScript("setRegions('\(coreJSON)', '\(presJSON)')",
                                       completionHandler: nil)
            }
        }

        func userContentController(_ controller: WKUserContentController,
                                   didReceive message: WKScriptMessage) {
            guard let payload = message.body as? [String: Any],
                  let type = payload["type"] as? String else { return }
            switch type {
            case "ready":
                // Loading the HTML document and initialising RDKit's WASM are
                // separate asynchronous steps. Applying state at didFinish can
                // otherwise lose labels, linker endpoints and read-only mode on
                // the first render. The page explicitly acknowledges WASM
                // readiness before we send any molecule state.
                ready = true
                lastDrawn = nil
                lastState = ""
                draw(pending, force: true)
                apply(attachment: parent.attachmentAtom,
                      linker: parent.attachmentLinkerAtom,
                      core: parent.coreAtoms,
                      presentation: parent.presentationAtoms,
                      labels: parent.atomLabels,
                      picking: parent.allowsAttachmentPicking)
            case "pick":
                let core = payload["core"] as? Int ?? -1
                let linker = payload["linker"] as? Int ?? -1
                DispatchQueue.main.async {
                    self.parent.attachmentAtom = core < 0 ? nil : core
                    self.parent.attachmentLinkerAtom = linker < 0 ? nil : linker
                }
            case "atoms":
                if let symbols = payload["symbols"] as? [String] {
                    DispatchQueue.main.async { self.parent.onAtomsResolved?(symbols) }
                }
            default:
                break
            }
        }
    }
}
