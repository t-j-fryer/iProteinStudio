import SwiftUI
import WebKit

// Pre-resolved ethanol fixture: no installed engines or user workspaces.
enum AppPaths {
    static var webRoot: URL? { URL(fileURLWithPath: CommandLine.arguments[1]).appendingPathComponent("Sources/iProteinStudio/Resources/web") }
}
@MainActor final class BoltzLigandAtoms: ObservableObject {
    struct Atom: Identifiable { var name: String; var element: String; var id: String { name } }
    @Published var atoms = [Atom(name: "C1", element: "C"), Atom(name: "C2", element: "C"), Atom(name: "O3", element: "O")]
    var namesByInputIndex = ["C1", "C2", "O3"]
    var generatedFor = "CCO|1|nise"
    var signature = String(repeating: "a", count: 64)
    var hasAtoms: Bool { !atoms.isEmpty }
    var isResolving = false
    var error: String?
    var displaySmiles = "CCO"
    var chemicalStateChanged = false
    func resolve(smiles: String, affinityHead: Bool, nise: Bool) {}
    func reset() {}
}
@MainActor final class SelectionFixture: ObservableObject {
    @Published var request: NISERequest = { var r = NISERequest(); r.smiles = "CCO"; return r }()
    @Published var verified = false
    let atoms = BoltzLigandAtoms()
}
struct SelectionFixtureView: View {
    @ObservedObject var model: SelectionFixture
    var body: some View {
        NISEAtomTargetingView(request: Binding(get: { model.request }, set: { model.request = $0 }),
                             atoms: model.atoms, verified: $model.verified).padding()
    }
}
@MainActor final class ConditionFixture: ObservableObject {
    @Published var conditions: [String: [String]] = ["C1": ["buried"], "C2": ["exposed"], "O3": ["hbondDonor", "hbondAcceptor", "hotspot"]]
}
struct ConditionFixtureView: View {
    @ObservedObject var model: ConditionFixture
    var body: some View {
        VStack {
            Text("Binding-site conditions").font(.title2)
            LigandAtomPicker(smiles: "CCO", attachmentAtom: .constant(nil), attachmentLinkerAtom: .constant(nil),
                             atomLabels: ["C1", "C2", "O3"], atomConditions: model.conditions, allowsAttachmentPicking: false)
            Text("B · Buried     E · Exposed     D · Ligand donor     A · Ligand acceptor     H · Hotspot")
            Button("Clear all atom conditions") { model.conditions = [:] }
        }.padding()
    }
}
@main struct LigandAtomSelectionHarness {
    @MainActor static func spin(_ seconds: Double) { RunLoop.main.run(until: Date().addingTimeInterval(seconds)) }
    @MainActor static func descendants(_ view: NSView) -> [NSView] {
        [view] + view.subviews.flatMap(descendants)
    }
    @MainActor static func evaluate(_ script: String, in web: WKWebView) -> Any? {
        var finished = false
        var result: Any?
        web.evaluateJavaScript(script) { value, error in
            if let error { print(error); exit(1) }
            result = value; finished = true
        }
        let deadline = Date().addingTimeInterval(5)
        while !finished && Date() < deadline { spin(0.05) }
        precondition(finished)
        return result
    }
    @MainActor static func main() {
        setbuf(stdout, nil)
        _ = NSApplication.shared
        NSApp.setActivationPolicy(.accessory)
        let model = SelectionFixture()
        let host = NSHostingView(rootView: SelectionFixtureView(model: model))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 800, height: 1000),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.contentView = host
        window.orderFront(nil)
        let deadline = Date().addingTimeInterval(20)
        while !model.verified && Date() < deadline { spin(0.1) }
        let controls = descendants(host).compactMap { $0 as? NSSegmentedControl }
        print("verified=\(model.verified), segmented controls=\(controls.count)")
        guard model.verified, let control = controls.first else {
            print(descendants(host).map { String(describing: type(of: $0)) }.joined(separator: "\n"))
            exit(1)
        }
        let web = descendants(host).compactMap { $0 as? WKWebView }.first!
        for (segment, expected) in [(1, "bind"), (2, "expose"), (0, "none")] {
            precondition(control.isEnabled)
            control.selectedSegment = segment
            control.sendAction(control.action, to: control.target)
            spin(0.3)
            print("\(expected): hotspots=\(model.request.hotspot_atoms), exposed=\(model.request.exposed_atoms)")
            let name = "C1"
            precondition(model.request.hotspot_atoms.contains(name) == (expected == "bind"))
            precondition(model.request.exposed_atoms.contains(name) == (expected == "expose"))
            let shadeCount = evaluate("document.querySelectorAll('#nh-shade circle').length", in: web) as! Int
            precondition(shadeCount == (expected == "none" ? 0 : 1))
            let visible = evaluate("Boolean(document.querySelector('svg > rect').compareDocumentPosition(document.querySelector('#nh-shade')) & Node.DOCUMENT_POSITION_FOLLOWING)", in: web) as! Bool
            precondition(visible, "Atom shading must be above RDKit's opaque background")
        }
        control.selectedSegment = 1; control.sendAction(control.action, to: control.target); spin(0.2)
        let second = descendants(host).compactMap { $0 as? NSSegmentedControl }[1]
        second.selectedSegment = 2; second.sendAction(second.action, to: second.target); spin(0.2)
        precondition(model.request.hotspot_atoms == ["C1"] && model.request.exposed_atoms == ["C2"])
        precondition(model.request.ligand_atom_signature == model.atoms.signature)
        precondition(model.request.ligand_atoms_generated_for == "CCO")
        let restored = try! JSONDecoder().decode(NISERequest.self, from: JSONEncoder().encode(model.request))
        precondition(restored == model.request)
        model.request.ligand_atom_signature = "stale"; spin(0.2)
        precondition(descendants(host).compactMap { $0 as? NSSegmentedControl }.allSatisfy { !$0.isEnabled })
        model.request.clearAtomSelections(); spin(0.2)
        precondition(descendants(host).compactMap { $0 as? NSSegmentedControl }.allSatisfy(\.isEnabled))
        print("PASS native None/Bind/Expose selection, visible shading, independent atoms, saved map and stale-map guards")
        let conditions = ConditionFixture()
        let conditionHost = NSHostingView(rootView: ConditionFixtureView(model: conditions))
        window.setContentSize(NSSize(width: 850, height: 420)); window.contentView = conditionHost
        spin(0.5)
        let conditionWeb = descendants(conditionHost).compactMap { $0 as? WKWebView }.first!
        let conditionDeadline = Date().addingTimeInterval(20)
        while (evaluate("document.querySelectorAll('[data-condition]').length", in: conditionWeb) as? Int ?? 0) != 5 && Date() < conditionDeadline { spin(0.2) }
        precondition(evaluate("document.querySelectorAll('[data-condition]').length", in: conditionWeb) as! Int == 5)
        precondition(evaluate("document.querySelectorAll('[data-atom=O3]').length", in: conditionWeb) as! Int == 3)
        precondition(evaluate("(() => {const path=document.querySelector('path.bond-0'); const points=Array.from(path.getAttribute('d').matchAll(/(-?[0-9.]+),(-?[0-9.]+)/g)).map(m=>[+m[1],+m[2]]); return ['C1','C2'].every(name=>{const ring=document.querySelector('[data-atom='+name+']');return points.some(p=>Math.hypot(p[0]-Number(ring.getAttribute('cx')),p[1]-Number(ring.getAttribute('cy')))<0.2);});})()", in: conditionWeb) as! Bool, "Carbon rings must meet the actual bond endpoints")
        precondition(evaluate("document.querySelector('#nh-labels').textContent.includes('D/A/H')", in: conditionWeb) as! Bool)
        precondition(evaluate("new Set(Array.from(document.querySelectorAll('[data-condition]')).map(e=>e.getAttribute('stroke'))).size", in: conditionWeb) as! Int == 5)
        precondition(evaluate("Array.from(document.querySelectorAll('[data-atom=O3]')).every(e=>e.hasAttribute('stroke-dasharray'))", in: conditionWeb) as! Bool)
        window.setContentSize(NSSize(width: 900, height: 440)); spin(0.5)
        precondition(evaluate("document.querySelectorAll('[data-condition]').length", in: conditionWeb) as! Int == 5)
        if CommandLine.arguments.count > 2, let bitmap = conditionHost.bitmapImageRepForCachingDisplay(in: conditionHost.bounds) {
            conditionHost.cacheDisplay(in: conditionHost.bounds, to: bitmap)
            try! bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[2]))
        }
        // Exercise the host binding update, rather than clearing only JavaScript state.
        conditions.conditions = [:]; spin(0.3)
        precondition(evaluate("document.querySelectorAll('[data-condition]').length", in: conditionWeb) as! Int == 0)
        precondition(evaluate("document.querySelector('#nh-labels').textContent.includes('D/A/H')", in: conditionWeb) as! Bool == false)
        print("PASS five condition colours, simultaneous roles, labels, resize retention and clearing via host binding")
        window.orderOut(nil)
    }
}
