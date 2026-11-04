import SwiftUI
import WebKit

enum AppPaths {
    static var webRoot: URL? { URL(fileURLWithPath: CommandLine.arguments[1]).appendingPathComponent("Sources/iProteinStudio/Resources/web") }
}
struct Py2DmolViewer: View {
    let structurePath: String?
    var selection: Binding<[String]>?
    let showsControls: Bool
    var body: some View { Text("Unexpected viewer") }
}
@MainActor final class MotifFixture: ObservableObject {
    @Published var selected = ["A:10"]
    @Published var atoms = ["A:10": ["N", "CA"]]
}
struct MotifFixtureView: View {
    @ObservedObject var model: MotifFixture
    let path: String
    var body: some View { TargetStructureView(structurePath: path, selected: $model.selected, showSurface: false, selectedAtoms: model.atoms) }
}
@main struct RFD4MotifViewerHarness {
    @MainActor static func spin(_ seconds: Double) { RunLoop.main.run(until: Date().addingTimeInterval(seconds)) }
    @MainActor static func descendants(_ view: NSView) -> [NSView] { [view] + view.subviews.flatMap(descendants) }
    @MainActor static func evaluate(_ script: String, _ web: WKWebView) -> Any? {
        var finished = false; var result: Any?
        web.evaluateJavaScript(script) { value, error in
            if let error { print(error); exit(1) }; result = value; finished = true
        }
        let deadline = Date().addingTimeInterval(5)
        while !finished && Date() < deadline { spin(0.05) }
        precondition(finished); return result
    }
    @MainActor static func main() {
        setbuf(stdout, nil); _ = NSApplication.shared; NSApp.setActivationPolicy(.accessory)
        let model = MotifFixture()
        let host = NSHostingView(rootView: MotifFixtureView(model: model, path: CommandLine.arguments[2]))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 800, height: 600), styleMask: [.titled], backing: .buffered, defer: false)
        window.contentView = host; window.orderFront(nil); spin(2)
        let web = descendants(host).compactMap { $0 as? WKWebView }.first!
        let deadline = Date().addingTimeInterval(20)
        while (evaluate("typeof viewer !== 'undefined' && viewer.getModel() ? viewer.getModel().selectedAtoms({}).length : 0", web) as? Int ?? 0) == 0 && Date() < deadline { spin(0.2) }
        precondition(model.selected == ["A:10"], "Loading must preserve the saved selection")
        precondition(evaluate("viewer.getModel().selectedAtoms({}).filter(a=>a.style.sphere).length", web) as! Int == 2)
        precondition(evaluate("viewer.getModel().selectedAtoms({chain:'A',resi:10}).filter(a=>a.style.sphere).map(a=>a.atom).sort().join(',')", web) as! String == "CA,N")
        _ = evaluate("(()=>{let a=viewer.getModel().selectedAtoms({chain:'A',resi:20,atom:'CA'})[0];a.callback(a,viewer);return true;})()", web)
        spin(0.3); precondition(Set(model.selected) == Set(["A:10", "A:20"]))
        model.atoms = ["A:20": ["CA", "C", "O"]]; spin(0.3)
        precondition(evaluate("viewer.getModel().selectedAtoms({}).filter(a=>a.style.sphere).length", web) as! Int == 3)
        precondition(evaluate("viewer.getModel().selectedAtoms({chain:'A',resi:10}).some(a=>a.style.sphere)", web) as! Bool == false)
        model.selected = []; model.atoms = [:]; spin(0.3)
        precondition(evaluate("viewer.getModel().selectedAtoms({}).some(a=>a.style.sphere || a.style.stick)", web) as! Bool == false)
        print("PASS actual 3Dmol atom overlays, residue-click bridge, saved selection and clearing")
        window.orderOut(nil)
    }
}
