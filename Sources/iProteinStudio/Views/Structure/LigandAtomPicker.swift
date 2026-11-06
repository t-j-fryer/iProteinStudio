import SwiftUI
import AppKit
import WebKit

/// Shared atom picker with an input-order 2D drawing and rotatable 3D conformer.
struct LigandAtomPicker: View {
    let smiles: String
    @Binding var attachmentAtom: Int?
    @Binding var attachmentLinkerAtom: Int?
    var coreAtoms: [Int] = []
    var presentationAtoms: [Int] = []
    var atomLabels: [String] = []
    var atomConditions: [String: [String]] = [:]
    var allowsAttachmentPicking = true
    var onAtomsResolved: (([String]) -> Void)?
    var onAttachmentChanged: ((Int?, Int?) -> Void)?
    @State private var threeD = false
    @StateObject private var preview = LigandPreview()
    @AppStorage("moleculeViewer.width") private var savedWidth = 0.0
    @AppStorage("moleculeViewer.height") private var savedHeight = 320.0
    @State private var draggingSize: CGSize?
    @State private var dragOrigin: CGSize?

    private var height: CGFloat { min(1000, max(240, draggingSize?.height ?? CGFloat(savedHeight))) }

    var body: some View {
        GeometryReader { available in
            let maximumWidth = available.size.width
            let minimumWidth = min(320, maximumWidth)
            let requestedWidth = draggingSize?.width ?? (savedWidth > 0 ? CGFloat(savedWidth) : maximumWidth)
            let width = min(maximumWidth, max(minimumWidth, requestedWidth))
            VStack(spacing: 6) {
                HStack {
                    Text("Molecule view").font(.callout.weight(.medium))
                        .lineLimit(1).fixedSize(horizontal: true, vertical: false)
                    Spacer(minLength: 12)
                    Picker("Molecule view", selection: $threeD) {
                        Text("2D").tag(false)
                        Text("3D").tag(true)
                    }.labelsHidden().pickerStyle(.segmented).frame(width: 140)
                }.padding(.horizontal, 8).padding(.top, 6)
                molecule
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .frame(width: width, height: height)
            .background(.white, in: RoundedRectangle(cornerRadius: 8))
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
            .overlay(alignment: .bottomTrailing) {
                Image(systemName: "arrow.up.left.and.arrow.down.right")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .frame(width: 30, height: 30)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 6))
                    .contentShape(Rectangle())
                    .help("Drag to resize the viewer’s width and height. Double-click to reset its size.")
                    .accessibilityLabel("Resize molecule viewer")
                    .accessibilityValue("Width \(Int(width)), height \(Int(height))")
                    .onHover { inside in
                        if inside {
                            if #available(macOS 15, *) { NSCursor.frameResize(position: .bottomRight, directions: .all).set() }
                            else { NSCursor.crosshair.set() }
                        } else { NSCursor.arrow.set() }
                    }
                    .gesture(DragGesture(minimumDistance: 2, coordinateSpace: .global)
                        .onChanged { value in
                            let origin = dragOrigin ?? CGSize(width: width, height: height)
                            dragOrigin = origin
                            draggingSize = CGSize(
                                width: min(maximumWidth, max(minimumWidth, origin.width + value.translation.width)),
                                height: min(1000, max(240, origin.height + value.translation.height)))
                        }
                        .onEnded { _ in
                            if let size = draggingSize { savedWidth = Double(size.width); savedHeight = Double(size.height) }
                            draggingSize = nil; dragOrigin = nil
                        })
                    .onTapGesture(count: 2) { resetSize() }
                    .accessibilityAction(named: "Reset viewer size") { resetSize() }
                    .padding(5)
            }
        }
        .frame(height: height)
        .onChange(of: threeD) { _, enabled in if enabled { preview.load(smiles: smiles) } }
        .onChange(of: smiles) { _, value in if threeD { preview.load(smiles: value) } }
    }

    @ViewBuilder private var molecule: some View {
        if threeD {
            if let payload = preview.payload {
                LigandSpatialViewer(payload: payload, labels: atomLabels, conditions: atomConditions,
                    attachment: attachmentAtom, linker: attachmentLinkerAtom, core: coreAtoms, presentation: presentationAtoms,
                    allowsPicking: allowsAttachmentPicking, onPick: { first, second in
                        if let changed = onAttachmentChanged { changed(first, second) }
                        else { attachmentAtom = first; attachmentLinkerAtom = second }
                    })
            } else if preview.busy { ProgressView("Preparing 3D conformer…").frame(maxHeight: .infinity) }
            else { Text(preview.error ?? "No 3D conformer available.").font(.caption).frame(maxHeight: .infinity) }
        } else {
            LigandAtomWebView(smiles: smiles, attachmentAtom: $attachmentAtom, attachmentLinkerAtom: $attachmentLinkerAtom,
                coreAtoms: coreAtoms, presentationAtoms: presentationAtoms, atomLabels: atomLabels,
                atomConditions: atomConditions, allowsAttachmentPicking: allowsAttachmentPicking,
                onAtomsResolved: onAtomsResolved, onAttachmentChanged: onAttachmentChanged)
        }
    }

    private func resetSize() {
        savedWidth = 0; savedHeight = 320; draggingSize = nil; dragOrigin = nil
    }
}

/// A clickable 2D depiction: the user points at both ends of the directed
/// core-to-linker bond instead of typing ambiguous indices.
///
/// This matters more than it looks. Getting the attachment point wrong makes the
/// linker count as recognition core, so its flexibility dominates the conformer
/// analysis and the design budget gets spread across shapes that differ only in
/// a floppy tail. A typed index gives the user no way to tell they got it wrong;
/// a picture they clicked, shaded afterwards with the split that was actually
/// used, does.
private struct LigandAtomWebView: NSViewRepresentable {
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
    /// Canonical atom names mapped to the active binding-site conditions.
    var atomConditions: [String: [String]] = [:]
    var allowsAttachmentPicking = true
    /// Reports the atom symbols in index order, so a mismatch between the
    /// depiction's atom numbering and the analysis's can be caught rather than
    /// silently producing a nonsense split.
    var onAtomsResolved: (([String]) -> Void)?
    /// Commit both endpoints together when they share one request binding.
    var onAttachmentChanged: ((Int?, Int?) -> Void)?

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
                                  labels: atomLabels, conditions: atomConditions, picking: allowsAttachmentPicking)
    }

    static func dismantleNSView(_ web: WKWebView, coordinator: Coordinator) {
        web.configuration.userContentController.removeScriptMessageHandler(forName: "ligand")
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var parent: LigandAtomWebView
        weak var web: WKWebView?
        private var ready = false
        private var pending: String = ""
        private var lastDrawn: String?
        private var lastState: String = ""

        init(_ parent: LigandAtomWebView) { self.parent = parent }

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
                   labels: [String], conditions: [String: [String]], picking: Bool) {
            guard ready, let web else { return }
            // Cheap change detection: these fire on every SwiftUI update, and
            // re-running the JS would fight the user's own clicks.
            let conditionData = (try? JSONEncoder().encode(conditions)) ?? Data("{}".utf8)
            let signature = "\(conditionData.base64EncodedString())|\(attachment ?? -1)|\(linker ?? -1)|\(core)|\(presentation)|\(labels)|\(picking)"
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
            web.evaluateJavaScript("setAtomConditionsB64(\"\(conditionData.base64EncodedString())\")", completionHandler: nil)
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
                      conditions: parent.atomConditions,
                      picking: parent.allowsAttachmentPicking)
            case "pick":
                let core = payload["core"] as? Int ?? -1
                let linker = payload["linker"] as? Int ?? -1
                DispatchQueue.main.async {
                    if let changed = self.parent.onAttachmentChanged {
                        changed(core < 0 ? nil : core, linker < 0 ? nil : linker)
                    } else {
                        self.parent.attachmentAtom = core < 0 ? nil : core
                        self.parent.attachmentLinkerAtom = linker < 0 ? nil : linker
                    }
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
