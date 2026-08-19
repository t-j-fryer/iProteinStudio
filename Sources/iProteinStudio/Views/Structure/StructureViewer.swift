import SwiftUI
import WebKit

/// The shared offline py2Dmol structure view used everywhere Studio presents
/// a protein structure. Its built-in Style panel exposes rendering, colour,
/// projection, rotation and export controls without duplicating those settings
/// in SwiftUI.
struct StructureViewer: View {
    let structurePath: String?

    var body: some View {
        Py2DmolViewer(structurePath: structurePath, selection: nil, showsControls: true)
    }
}

/// WebKit bridge for the vendored py2Dmol canvas renderer.
struct Py2DmolViewer: NSViewRepresentable {
    let structurePath: String?
    var selection: Binding<[Int]>?
    var showsControls: Bool

    func makeCoordinator() -> Coordinator {
        Coordinator(selection: selection)
    }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.userContentController.add(context.coordinator, name: "hotspots")
        config.userContentController.add(context.coordinator, name: "viewerStatus")
        let web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = context.coordinator
        web.setValue(false, forKey: "drawsBackground")
        context.coordinator.web = web
        if let html = AppPaths.webRoot?.appendingPathComponent("py2dmol/viewer.html"),
           let dir = AppPaths.webRoot?.appendingPathComponent("py2dmol") {
            web.loadFileURL(html, allowingReadAccessTo: dir)
        }
        return web
    }

    func updateNSView(_ web: WKWebView, context: Context) {
        context.coordinator.selection = selection
        context.coordinator.apply(structurePath: structurePath, showsControls: showsControls)
    }

    static func dismantleNSView(_ web: WKWebView, coordinator: Coordinator) {
        web.configuration.userContentController.removeScriptMessageHandler(forName: "hotspots")
        web.configuration.userContentController.removeScriptMessageHandler(forName: "viewerStatus")
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var selection: Binding<[Int]>?
        weak var web: WKWebView?
        private var ready = false
        private var loadedPath: String?
        private var pendingPath: String?
        private var pendingControls = true
        private var lastPushed = Set<Int>()

        init(selection: Binding<[Int]>?) {
            self.selection = selection
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            ready = true
            apply(structurePath: pendingPath, showsControls: pendingControls, force: true)
        }

        func apply(structurePath: String?, showsControls: Bool, force: Bool = false) {
            pendingPath = structurePath
            pendingControls = showsControls
            guard ready, let web else { return }

            if let path = structurePath, force || path != loadedPath,
               let data = FileManager.default.contents(atPath: path), !data.isEmpty {
                loadedPath = path
                lastPushed = []
                let encoded = data.base64EncodedString()
                let format = path.lowercased().hasSuffix(".pdb") ? "pdb" : "cif"
                let name = (path as NSString).lastPathComponent
                let script = "studioLoadStructureB64(\(Self.js(encoded)),\(Self.js(format)),"
                    + "\(Self.js(name)),\(selection == nil ? "false" : "true"),"
                    + "\(showsControls ? "true" : "false"))"
                web.evaluateJavaScript(script, completionHandler: nil)
            }

            guard let selection else { return }
            let values = Set(selection.wrappedValue)
            guard force || values != lastPushed else { return }
            lastPushed = values
            let json = "[" + values.sorted().map(String.init).joined(separator: ",") + "]"
            web.evaluateJavaScript("studioSetSelection(\(json))", completionHandler: nil)
        }

        func userContentController(_ controller: WKUserContentController,
                                   didReceive message: WKScriptMessage) {
            if message.name == "viewerStatus" {
                if let text = message.body as? String { print("py2Dmol: \(text)") }
                return
            }
            guard message.name == "hotspots", let selection,
                  let text = message.body as? String,
                  let data = text.data(using: .utf8),
                  let values = try? JSONDecoder().decode([Int].self, from: data) else { return }
            DispatchQueue.main.async {
                self.lastPushed = Set(values)
                selection.wrappedValue = values
            }
        }

        private static func js(_ value: String) -> String {
            guard let data = try? JSONEncoder().encode(value),
                  let result = String(data: data, encoding: .utf8) else { return "\"\"" }
            return result
        }
    }
}
