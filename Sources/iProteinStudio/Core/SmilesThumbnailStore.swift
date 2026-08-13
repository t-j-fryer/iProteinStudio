import SwiftUI
import WebKit
import AppKit

/// Renders 2D molecule depictions (from SMILES) once to cached PNGs using a
/// single hidden RDKit-backed WKWebView, so ligand projects can show a static
/// thumbnail without spawning a WebGL/WASM instance per row.
@MainActor
final class SmilesThumbnailStore: ObservableObject {
    @Published private(set) var version = 0

    private let cacheDir: URL
    private var memCache: [String: NSImage] = [:]

    private var window: NSWindow?
    private var web: WKWebView?
    private var coord: Coord?
    private var rdkitReady = false

    private var pending: [String] = []
    private var queued = Set<String>()
    private var rendering = false

    init() {
        cacheDir = AppPaths.support.appendingPathComponent("smiles_thumbs", isDirectory: true)
        try? FileManager.default.createDirectory(at: cacheDir, withIntermediateDirectories: true)
    }

    /// Cached depiction if ready; otherwise enqueues a render and returns nil.
    func image(for smiles: String) -> NSImage? {
        let key = smiles.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else { return nil }
        if let img = memCache[key] { return img }
        let url = cacheURL(key)
        if let img = NSImage(contentsOf: url) { memCache[key] = img; return img }
        enqueue(key)
        return nil
    }

    private func enqueue(_ smiles: String) {
        guard !queued.contains(smiles) else { return }
        queued.insert(smiles)
        pending.append(smiles)
        ensureWeb()
        pump()
    }

    private func ensureWeb() {
        guard web == nil else { return }
        guard let page = AppPaths.webRoot?.appendingPathComponent("mol/smiles2d.html"),
              let dir = AppPaths.webRoot?.appendingPathComponent("mol") else { return }
        let w = WKWebView(frame: NSRect(x: 0, y: 0, width: 360, height: 260))
        let win = NSWindow(contentRect: NSRect(x: -30000, y: -30000, width: 360, height: 260),
                           styleMask: [.borderless], backing: .buffered, defer: false)
        win.contentView = w
        win.orderFrontRegardless()
        let c = Coord(onLoad: { [weak self] in self?.injectRDKit() })
        w.navigationDelegate = c
        w.loadFileURL(page, allowingReadAccessTo: dir)
        self.web = w; self.window = win; self.coord = c
    }

    private func injectRDKit() {
        guard let web,
              let wasm = AppPaths.webRoot?.appendingPathComponent("mol/RDKit_minimal.wasm"),
              let data = try? Data(contentsOf: wasm) else { return }
        web.evaluateJavaScript("initRDKitWithWasm(\"\(data.base64EncodedString())\")", completionHandler: nil)
        waitForRDKit(tries: 40)
    }

    private func waitForRDKit(tries: Int) {
        guard let web, tries > 0 else { return }
        web.evaluateJavaScript("(typeof window.RDKit !== 'undefined')") { [weak self] r, _ in
            guard let self else { return }
            if (r as? Bool) == true { self.rdkitReady = true; self.pump() }
            else { DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { self.waitForRDKit(tries: tries - 1) } }
        }
    }

    private func pump() {
        guard rdkitReady, !rendering, let web, !pending.isEmpty else { return }
        let smiles = pending.removeFirst()
        rendering = true
        let b64 = Data(smiles.utf8).base64EncodedString()
        web.evaluateJavaScript("drawSmilesB64(\"\(b64)\")") { [weak self] _, _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                web.takeSnapshot(with: WKSnapshotConfiguration()) { img, _ in
                    self?.finish(smiles: smiles, image: img)
                }
            }
        }
    }

    private func finish(smiles: String, image: NSImage?) {
        defer { rendering = false; pump() }
        guard let image,
              let tiff = image.tiffRepresentation,
              let rep = NSBitmapImageRep(data: tiff),
              let png = rep.representation(using: .png, properties: [:]) else {
            queued.remove(smiles); return
        }
        try? png.write(to: cacheURL(smiles))
        memCache[smiles] = image
        version += 1
    }

    private func cacheURL(_ s: String) -> URL {
        var h: UInt64 = 1469598103934665603
        for b in s.utf8 { h = (h ^ UInt64(b)) &* 1099511628211 }
        return cacheDir.appendingPathComponent(String(h, radix: 16) + ".png")
    }

    final class Coord: NSObject, WKNavigationDelegate {
        let onLoad: () -> Void
        init(onLoad: @escaping () -> Void) { self.onLoad = onLoad }
        func webView(_ w: WKWebView, didFinish n: WKNavigation!) { onLoad() }
    }
}
