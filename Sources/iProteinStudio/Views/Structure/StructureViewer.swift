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

/// A control-free structure preview for comparison grids. The full py2Dmol
/// controls remain available in the large selected viewer; hiding the fixed
/// 190-point panel here prevents it from covering most of a compact card.
struct StructurePreview: View {
    let structurePath: String?

    var body: some View {
        Py2DmolViewer(structurePath: structurePath, selection: nil, showsControls: false)
    }
}

struct StructureTrajectoryFrame: Identifiable, Hashable {
    let id: String
    let label: String
    let structurePath: String
}

/// Multi-frame result viewer. The browser supplies complete design-stage
/// complexes; the WebKit adapter aligns target chains B onward onto frame zero
/// before exposing py2Dmol's scrubber, playback and speed controls.
struct StructureTrajectoryViewer: View {
    let frames: [StructureTrajectoryFrame]

    var body: some View {
        Py2DmolViewer(structurePath: nil, trajectoryFrames: frames,
                      selection: nil, showsControls: true)
    }
}

/// WebKit bridge for the vendored py2Dmol canvas renderer.
struct Py2DmolViewer: NSViewRepresentable {
    let structurePath: String?
    var trajectoryFrames: [StructureTrajectoryFrame] = []
    var selection: Binding<[String]>?
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
        context.coordinator.apply(structurePath: structurePath,
                                  trajectoryFrames: trajectoryFrames,
                                  showsControls: showsControls)
    }

    static func dismantleNSView(_ web: WKWebView, coordinator: Coordinator) {
        web.configuration.userContentController.removeScriptMessageHandler(forName: "hotspots")
        web.configuration.userContentController.removeScriptMessageHandler(forName: "viewerStatus")
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var selection: Binding<[String]>?
        weak var web: WKWebView?
        private var ready = false
        private var loadedIdentity: String?
        private var pendingPath: String?
        private var pendingTrajectory: [StructureTrajectoryFrame] = []
        private var pendingControls = true
        private var lastPushed = Set<String>()

        init(selection: Binding<[String]>?) {
            self.selection = selection
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            ready = true
            apply(structurePath: pendingPath, trajectoryFrames: pendingTrajectory,
                  showsControls: pendingControls, force: true)
        }

        func apply(structurePath: String?,
                   trajectoryFrames: [StructureTrajectoryFrame] = [],
                   showsControls: Bool, force: Bool = false) {
            pendingPath = structurePath
            pendingTrajectory = trajectoryFrames
            pendingControls = showsControls
            guard ready, let web else { return }

            let trajectoryIdentity = trajectoryFrames.map {
                "\($0.id)|\($0.structurePath)"
            }.joined(separator: "||")
            if trajectoryFrames.count > 1,
               force || trajectoryIdentity != loadedIdentity {
                let payload: [[String: String]] = trajectoryFrames.compactMap { frame in
                    guard let data = FileManager.default.contents(atPath: frame.structurePath),
                          !data.isEmpty else { return nil }
                    return [
                        "encoded": data.base64EncodedString(),
                        "format": frame.structurePath.lowercased().hasSuffix(".pdb") ? "pdb" : "cif",
                        "name": frame.label,
                    ]
                }
                if payload.count == trajectoryFrames.count,
                   let data = try? JSONSerialization.data(withJSONObject: payload),
                   let json = String(data: data, encoding: .utf8) {
                    loadedIdentity = trajectoryIdentity
                    lastPushed = []
                    let script = "studioLoadTrajectoryB64(\(json),"
                        + "\(showsControls ? "true" : "false"))"
                    web.evaluateJavaScript(script, completionHandler: nil)
                }
            } else if let path = structurePath,
                      force || path != loadedIdentity,
               let data = FileManager.default.contents(atPath: path), !data.isEmpty {
                loadedIdentity = path
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
            guard let data = try? JSONEncoder().encode(values.sorted()),
                  let json = String(data: data, encoding: .utf8) else { return }
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
                  let values = try? JSONDecoder().decode([String].self, from: data) else { return }
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
