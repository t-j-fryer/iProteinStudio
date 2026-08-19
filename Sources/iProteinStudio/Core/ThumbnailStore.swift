import SwiftUI
import WebKit
import AppKit

/// Renders structure thumbnails once to cached PNGs with the same bundled
/// py2Dmol renderer used by the interactive inspectors. Serves the grid static
/// images, so a result gallery does not create one live canvas per tile.
@MainActor
final class ThumbnailStore: ObservableObject {
    /// Bumps whenever a new thumbnail becomes available, so views re-query.
    @Published private(set) var version = 0

    private let cacheDir: URL
    private var memCache: [String: NSImage] = [:]

    private var window: NSWindow?
    private var web: WKWebView?
    private var coord: Coord?
    private var webReady = false

    private var pending: [String] = []
    private var queued = Set<String>()
    private var rendering = false

    init() {
        cacheDir = AppPaths.support.appendingPathComponent("thumbnails", isDirectory: true)
        try? FileManager.default.createDirectory(at: cacheDir, withIntermediateDirectories: true)
    }

    /// Returns a cached thumbnail if ready; otherwise enqueues a render and
    /// returns nil (the view shows a placeholder and refreshes on `version`).
    func image(for structurePath: String) -> NSImage? {
        if let img = memCache[structurePath] { return img }
        let url = cacheURL(structurePath)
        if let img = NSImage(contentsOf: url) { memCache[structurePath] = img; return img }
        enqueue(structurePath)
        return nil
    }

    // MARK: rendering pipeline

    private func enqueue(_ path: String) {
        guard !queued.contains(path) else { return }
        queued.insert(path)
        pending.append(path)
        ensureWeb()
        pump()
    }

    private func ensureWeb() {
        guard web == nil else { return }
        guard let viewer = AppPaths.webRoot?.appendingPathComponent("py2dmol/viewer.html"),
              let dir = AppPaths.webRoot?.appendingPathComponent("py2dmol") else { return }
        let w = WKWebView(frame: NSRect(x: 0, y: 0, width: 480, height: 340))
        let win = NSWindow(contentRect: NSRect(x: -30000, y: -30000, width: 480, height: 340),
                           styleMask: [.borderless], backing: .buffered, defer: false)
        win.contentView = w
        win.orderFrontRegardless()
        let c = Coord { [weak self] in self?.webReady = true; self?.pump() }
        w.navigationDelegate = c
        w.loadFileURL(viewer, allowingReadAccessTo: dir)
        self.web = w; self.window = win; self.coord = c
    }

    private func pump() {
        guard webReady, !rendering, let web, !pending.isEmpty else { return }
        let path = pending.removeFirst()
        guard let data = FileManager.default.contents(atPath: path), !data.isEmpty else {
            // File not ready yet — allow a later retry.
            queued.remove(path)
            return
        }
        rendering = true
        let b64 = data.base64EncodedString()
        let fmt = path.lowercased().hasSuffix(".pdb") ? "pdb" : "cif"
        let name = (path as NSString).lastPathComponent
        let quotedName = (try? String(data: JSONEncoder().encode(name), encoding: .utf8)) ?? "\"structure\""
        web.evaluateJavaScript("studioLoadStructureB64(\"\(b64)\",\"\(fmt)\",\(quotedName),false,false)") { [weak self] _, _ in
            // Give the canvas a beat to draw, then read its PNG.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                web.evaluateJavaScript("studioPNG()") { res, _ in
                    self?.finishRender(path: path, uri: res as? String)
                }
            }
        }
    }

    private func finishRender(path: String, uri: String?) {
        defer { rendering = false; pump() }
        guard let uri, let comma = uri.firstIndex(of: ","),
              let png = Data(base64Encoded: String(uri[uri.index(after: comma)...])),
              let img = NSImage(data: png) else {
            queued.remove(path)   // let it retry later
            return
        }
        try? png.write(to: cacheURL(path))
        memCache[path] = img
        version += 1
    }

    private func cacheURL(_ path: String) -> URL {
        // Version the renderer in the key so old 3Dmol thumbnails do not mask
        // the transition to py2Dmol.
        cacheDir.appendingPathComponent(fnv1a("py2dmol-v1|" + path) + ".png")
    }

    private func fnv1a(_ s: String) -> String {
        var h: UInt64 = 1469598103934665603
        for b in s.utf8 { h = (h ^ UInt64(b)) &* 1099511628211 }
        return String(h, radix: 16)
    }

    final class Coord: NSObject, WKNavigationDelegate {
        let onReady: () -> Void
        init(onReady: @escaping () -> Void) { self.onReady = onReady }
        func webView(_ w: WKWebView, didFinish n: WKNavigation!) { onReady() }
    }
}
