import SwiftUI
import WebKit

enum AppPaths {
    static var webRoot: URL? { URL(fileURLWithPath: CommandLine.arguments[1]).appendingPathComponent("Sources/iProteinStudio/Resources/web") }
}
@main struct LigandSpatialViewerHarness {
    @MainActor static func spin(_ seconds: Double) { RunLoop.main.run(until: Date().addingTimeInterval(seconds)) }
    @MainActor static func descendants(_ view: NSView) -> [NSView] { [view] + view.subviews.flatMap(descendants) }
    @MainActor static func evaluate(_ script: String, in web: WKWebView) -> Any? {
        var finished = false; var result: Any?
        web.evaluateJavaScript(script) { value,error in
            if let error { print("JavaScript error in \(script): \(error)"); exit(1) }
            result=value;finished=true
        }
        while !finished { spin(0.05) };return result
    }
    @MainActor static func main() {
        setbuf(stdout,nil);_=NSApplication.shared;NSApp.setActivationPolicy(.accessory)
        let payload=try! Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[2])).base64EncodedString()
        let host=NSHostingView(rootView: LigandSpatialViewer(payload:payload,labels:["C1","C2","O3"],conditions:["O3":["exposed"]],allowsPicking:true))
        let window=NSWindow(contentRect:NSRect(x:0,y:0,width:850,height:600),styleMask:[.titled],backing:.buffered,defer:false)
        window.contentView=host;window.orderFront(nil)
        spin(3)
        let web=descendants(host).compactMap { $0 as? WKWebView }.first!
        precondition(evaluate("!!model && model.selectedAtoms({}).length > 0",in:web) as? Bool == true)
        let before=evaluate("JSON.stringify(viewer.getView())",in:web) as! String
        let coordinates=evaluate("JSON.stringify(model.selectedAtoms({}).map(a=>[a.x,a.y,a.z]))",in:web) as! String
        _=evaluate("document.getElementById('plus').click();true",in:web)
        precondition(evaluate("JSON.stringify(viewer.getView())",in:web) as! String != before)
        _=evaluate("document.getElementById('minus').click();document.getElementById('fit').click();true",in:web)
        let fitted=evaluate("JSON.stringify(viewer.getView())",in:web) as! String
        // Exercise 3Dmol's real mouse handlers, not just the rotate API.
        _=evaluate("(()=>{let testCanvas=document.querySelector('canvas'); let r=testCanvas.getBoundingClientRect(); testCanvas.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0,buttons:1,clientX:r.x+200,clientY:r.y+200})); testCanvas.dispatchEvent(new MouseEvent('mousemove',{bubbles:true,button:0,buttons:1,clientX:r.x+300,clientY:r.y+240})); testCanvas.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,button:0,clientX:r.x+300,clientY:r.y+240}));return true;})()",in:web)
        precondition(evaluate("JSON.stringify(viewer.getView())",in:web) as! String != fitted)
        precondition(evaluate("JSON.stringify(model.selectedAtoms({}).map(a=>[a.x,a.y,a.z]))",in:web) as! String == coordinates)
        print("PASS: real WebGL load, toolbar zoom/reset, drag rotation; model coordinates unchanged")
        let config=WKSnapshotConfiguration()
        var done=false
        web.takeSnapshot(with:config) { image,error in
            guard let image,let tiff=image.tiffRepresentation,let bitmap=NSBitmapImageRep(data:tiff),let png=bitmap.representation(using:.png,properties:[:]) else { print("Snapshot failed \(String(describing:error))");exit(1) }
            try! png.write(to:URL(fileURLWithPath:CommandLine.arguments[3]));done=true
        }
        while !done { spin(0.05) }
    }
}
