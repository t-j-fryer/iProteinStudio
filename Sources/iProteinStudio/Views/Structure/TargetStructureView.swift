import SwiftUI
import WebKit

/// py2Dmol is the normal target viewer and supports direct residue selection.
/// The specialised hydrophobic surface remains available as an explicit 3D
/// mode because py2Dmol does not calculate solvent-accessible surfaces.
struct TargetStructureView: View {
    let structurePath: String?
    @Binding var selected: [String]
    var showSurface: Bool
    var ligand: Bool = false

    var body: some View {
        if showSurface && !ligand {
            LegacyTargetStructureView(structurePath: structurePath, selected: $selected,
                                      showSurface: true, ligand: false)
        } else {
            Py2DmolViewer(structurePath: structurePath, selection: ligand ? nil : $selected,
                          showsControls: true)
        }
    }
}

/// The previous 3Dmol target viewer, retained only for hydrophobic surfaces.
private struct LegacyTargetStructureView: NSViewRepresentable {
    let structurePath: String?
    @Binding var selected: [String]
    var showSurface: Bool
    var ligand: Bool = false          // ball-and-stick view, no hotspot picking

    func makeCoordinator() -> Coordinator { Coordinator(selected: $selected, ligand: ligand) }

    func makeNSView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        cfg.userContentController.add(context.coordinator, name: "hotspots")
        let web = WKWebView(frame: .zero, configuration: cfg)
        web.navigationDelegate = context.coordinator
        context.coordinator.web = web
        if let html = AppPaths.webRoot?.appendingPathComponent("mol/targetprep.html"),
           let dir = AppPaths.webRoot?.appendingPathComponent("mol") {
            web.loadFileURL(html, allowingReadAccessTo: dir)
        }
        return web
    }

    func updateNSView(_ web: WKWebView, context: Context) {
        context.coordinator.apply(structurePath: structurePath, showSurface: showSurface,
                                  selection: selected)
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        let selected: Binding<[String]>
        let ligand: Bool
        weak var web: WKWebView?
        private var ready = false
        private var loadedPath: String?
        private var surface = false
        private var lastPushed = Set<String>()
        private var pendingPath: String?
        private var pendingSurface = false
        private var pendingSelection: [String] = []

        init(selected: Binding<[String]>, ligand: Bool) { self.selected = selected; self.ligand = ligand }

        func webView(_ w: WKWebView, didFinish n: WKNavigation!) {
            ready = true
            apply(structurePath: pendingPath, showSurface: pendingSurface, selection: pendingSelection, force: true)
        }

        func apply(structurePath: String?, showSurface: Bool, selection: [String], force: Bool = false) {
            pendingPath = structurePath; pendingSurface = showSurface; pendingSelection = selection
            guard ready, let web else { return }
            if let path = structurePath, path != loadedPath,
               let data = FileManager.default.contents(atPath: path) {
                loadedPath = path
                lastPushed = []   // JS resets its selection on load
                let b64 = data.base64EncodedString()
                let fmt = path.lowercased().hasSuffix(".pdb") ? "pdb" : "cif"
                let fn = ligand ? "loadLigandB64" : "loadTargetB64"
                web.evaluateJavaScript("\(fn)(\"\(b64)\",\"\(fmt)\")", completionHandler: nil)
            }
            if ligand { return }   // no surface / hotspot selection for ligands
            if showSurface != surface || force {
                surface = showSurface
                web.evaluateJavaScript("setSurface(\(showSurface ? "true" : "false"))", completionHandler: nil)
            }
            // Push selection to JS only when Swift changed it (e.g. chip removal);
            // JS guards against redundant rebuilds and does not post back.
            if Set(selection) != lastPushed {
                lastPushed = Set(selection)
                guard let data = try? JSONEncoder().encode(selection),
                      let json = String(data: data, encoding: .utf8) else { return }
                web.evaluateJavaScript("setSelection(\(json))", completionHandler: nil)
            }
        }

        func clearSelection() { web?.evaluateJavaScript("clearSelection()", completionHandler: nil) }

        func userContentController(_ c: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "hotspots",
                  let s = message.body as? String,
                  let data = s.data(using: .utf8),
                  let arr = try? JSONDecoder().decode([String].self, from: data) else { return }
            DispatchQueue.main.async {
                self.lastPushed = Set(arr)      // JS is already in this state
                self.selected.wrappedValue = arr
            }
        }
    }
}
