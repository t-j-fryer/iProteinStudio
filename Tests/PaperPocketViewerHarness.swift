import SwiftUI
import WebKit

enum AppPaths {
    static var webRoot: URL? {
        URL(fileURLWithPath: CommandLine.arguments[1]).appendingPathComponent("Sources/iProteinStudio/Resources/web")
    }
}

@main struct PaperPocketViewerHarness {
    @MainActor static func spin() { RunLoop.main.run(until: Date().addingTimeInterval(0.03)) }
    @MainActor static func evaluate(_ script: String, _ web: WKWebView) throws -> Any? {
        var done=false; var result: Any?; var failure: Error?
        web.evaluateJavaScript(script) { value,error in result=value;failure=error;done=true }
        let deadline=Date().addingTimeInterval(15)
        while !done && Date()<deadline { spin() }
        if let failure { throw failure }
        precondition(done,"JavaScript timed out")
        return result
    }
    @MainActor static func wait(_ expression: String, _ web: WKWebView) throws {
        let deadline=Date().addingTimeInterval(60)
        while Date()<deadline {
            if try evaluate(expression,web) as? Bool == true { return }
            spin()
        }
        let state=try evaluate("(()=>{const s=studioPocketState();delete s.coordinates;return JSON.stringify(s)})()",web)
        fatalError("Viewer wait failed: \(expression); \(String(describing:state))")
    }
    @MainActor static func descendants(_ view: NSView) -> [NSView] { [view]+view.subviews.flatMap(descendants) }
    static func check(_ value: Bool, line: UInt = #line) { precondition(value, "Contract failed at line \(line)") }
    static func js(_ value: String) -> String { String(decoding:try! JSONEncoder().encode(value),as:UTF8.self) }
    @MainActor static func main() throws {
        guard CommandLine.arguments.count==5 else { fatalError("usage: harness ROOT PUBLIC_PDB PUBLIC_CIF OUTPUT_PNG") }
        setbuf(stdout,nil);_=NSApplication.shared;NSApp.setActivationPolicy(.accessory)
        let pdbURL=URL(fileURLWithPath:CommandLine.arguments[2]), cifURL=URL(fileURLWithPath:CommandLine.arguments[3])
        let pdb=try Data(contentsOf:pdbURL), cif=try Data(contentsOf:cifURL)
        let host=NSHostingView(rootView:Py2DmolViewer(structurePath:pdbURL.path,selection:nil,showsControls:true))
        let window=NSWindow(contentRect:NSRect(x:0,y:0,width:1040,height:760),styleMask:[.titled],backing:.buffered,defer:false)
        window.contentView=host;window.orderFront(nil)
        while descendants(host).compactMap({$0 as? WKWebView}).isEmpty { spin() }
        let web=descendants(host).compactMap{$0 as? WKWebView}.first!
        try wait("typeof studioPocketState==='function' && studioSurfaceBridge.renderer.currentFrame>=0",web)
        _=try evaluate("document.getElementById('imageStyle').value='pocket';document.getElementById('imageStyle').dispatchEvent(new Event('change'));true",web)
        try wait("studioPocketState().ready && studioPocketState().surfaces>0",web)
        _=try evaluate("(()=>{const s=document.getElementById('pocketLigand');const o=[...s.options].find(o=>o.value&&JSON.parse(o.value)[3]==='BNZ');if(!o)throw Error('Public benzene fixture missing');s.value=o.value;s.dispatchEvent(new Event('change'));return true})()",web)
        try wait("studioPocketState().ready && studioPocketState().surfaces>0",web)
        let coordinates=try evaluate("JSON.stringify(studioPocketState().coordinates)",web) as! String
        let camera=try evaluate("JSON.stringify(studioPocketState().view)",web) as! String
        _=try evaluate("(()=>{const c=document.querySelector('#pocketCanvas canvas'),r=c.getBoundingClientRect();for(const [type,x,y,buttons] of [['mousedown',200,200,1],['mousemove',300,240,1],['mouseup',300,240,0]])c.dispatchEvent(new MouseEvent(type,{bubbles:true,button:0,buttons,clientX:r.x+x,clientY:r.y+y}));return true})()",web)
        try wait("studioPocketState().ready",web)
        check(try evaluate("JSON.stringify(studioPocketState().view)",web) as! String != camera)
        check(try evaluate("JSON.stringify(studioPocketState().coordinates)",web) as! String == coordinates)
        _=try evaluate("document.getElementById('pocketFit').click();true",web)
        try wait("studioPocketState().ready",web)
        let firstPNG=try evaluate("studioPNG()",web) as! String
        precondition(firstPNG.hasPrefix("data:image/png;base64,") && firstPNG.count>10000)
        _=try evaluate("document.getElementById('pocketOpacity').value='0.5';document.getElementById('pocketOpacity').dispatchEvent(new Event('input'));document.getElementById('pocketDepth').value='2';document.getElementById('pocketDepth').dispatchEvent(new Event('input'));true",web)
        try wait("studioPocketState().ready",web)
        check(try evaluate("JSON.stringify(studioPocketState().coordinates)",web) as! String == coordinates)
        check(try evaluate("studioPNG()",web) as! String != firstPNG)
        _=try evaluate("studioSetSelection(['A100']);true",web)
        check(try evaluate("studioPocketState().selected.includes('A100')",web) as? Bool == true)
        // Deliberately synthetic overlay for the display bridge only. This is
        // not a classifier result or evidence about this public ligand.
        _=try evaluate("(()=>{const [x,y,z]=studioPocketState().ligandCentre;const fixture={ligand_chain:'A',cone:{stem:[[x,y,z-1],[x,y,z],[x+1,y,z]],stubs:[[[x,y,z],[x+1,y,z],[x+2,y+1,z]],[[x,y,z],[x+1,y,z],[x+2,y-1,z]]],labels:['wide','clash']}};studioSetPocketGeometryB64(btoa(JSON.stringify(fixture)));return true})()",web)
        check(try evaluate("!document.getElementById('pocketConeRow').hidden",web) as? Bool == true)
        try wait("studioPocketState().ready",web)
        let conePNG=try evaluate("studioPNG()",web) as? String
        check(conePNG != nil)
        _=try evaluate("document.getElementById('pocketCone').checked=false;document.getElementById('pocketCone').dispatchEvent(new Event('change'));true",web)
        check(try evaluate("studioPNG()",web) as? String != conePNG)
        _=try evaluate("studioSetPocketGeometryB64('');true",web)
        try wait("studioPocketState().ready",web)
        _=try evaluate("document.getElementById('pocketOpacity').value='1';document.getElementById('pocketOpacity').dispatchEvent(new Event('input'));document.getElementById('pocketDepth').value='0.7';document.getElementById('pocketDepth').dispatchEvent(new Event('input'));studioSetSelection([]);true",web)
        try wait("studioPocketState().ready",web)
        // Export through the production PNG API as well as a UI-layout snapshot.
        let png=try evaluate("studioPNG()",web) as! String
        try Data(base64Encoded:String(png.dropFirst("data:image/png;base64,".count)))!.write(to:URL(fileURLWithPath:CommandLine.arguments[4]+".export.png"))
        var captured=false
        web.takeSnapshot(with:WKSnapshotConfiguration()) { image,error in
            guard let image,let tiff=image.tiffRepresentation,let bitmap=NSBitmapImageRep(data:tiff),let data=bitmap.representation(using:.png,properties:[:]) else { fatalError("Snapshot failed: \(String(describing:error))") }
            try! data.write(to:URL(fileURLWithPath:CommandLine.arguments[4]));captured=true
        }
        while !captured { spin() }
        _=try evaluate("studioSelectImageStyle('illustration');true",web)
        check(try evaluate("document.getElementById('overlayButton').disabled",web) as? Bool == true)
        check(try evaluate("!document.getElementById('studioViewerRoot').classList.contains('studio-pocket')",web) as? Bool == true)
        print("PASS paper pocket: real SES surface, explicit ligand choice, opacity/cutaway, selection, PNG and illustration return; coordinates unchanged")

        _=try evaluate("studioLoadStructureB64(\(js(cif.base64EncodedString())),'cif','Public 181L',false,true);studioSelectImageStyle('pocket');true",web)
        try wait("studioPocketState().ready && studioPocketState().ligandCount>0",web)
        let lines=String(decoding:pdb,as:UTF8.self).split(separator:"\n",omittingEmptySubsequences:false).map(String.init)
        let apo=lines.filter{!$0.hasPrefix("HETATM") && !$0.hasPrefix("CONECT")}.joined(separator:"\n")
        _=try evaluate("studioLoadStructureB64(\(js(pdb.base64EncodedString())),'pdb','Public fixture switch',false,true);studioLoadStructureB64(\(js(Data(apo.utf8).base64EncodedString())),'pdb','Synthetic apo display fixture',false,true);true",web)
        try wait("studioPocketState().ready && studioPocketState().ligandCount===0",web)
        check(try evaluate("document.getElementById('pocketRegion').disabled && document.getElementById('pocketNote').textContent.includes('whole polymer')",web) as? Bool == true)
        print("PASS PDB/mmCIF and explicit apo whole-surface behavior")

        // Display-only rigidly transformed copies of the same public structure.
        // B is the fixed target, matching Studio's existing trajectory contract.
        func trajectoryPDB(_ transformed: Bool) -> String {
            lines.map { line in
                guard line.hasPrefix("ATOM  ") || line.hasPrefix("HETATM"),line.count>=54 else { return line }
                var chars=Array(line)
                if line.hasPrefix("ATOM  ") { chars[21]="B" }
                if transformed {
                    let x=Double(String(chars[30..<38]).trimmingCharacters(in:.whitespaces))!,y=Double(String(chars[38..<46]).trimmingCharacters(in:.whitespaces))!,z=Double(String(chars[46..<54]).trimmingCharacters(in:.whitespaces))!
                    chars.replaceSubrange(30..<54,with:Array(String(format:"%8.3f%8.3f%8.3f",y+20,-x+7,z-4)))
                }
                return String(chars)
            }.joined(separator:"\n")
        }
        let frames=[false,true].enumerated().map { i,value in ["encoded":Data(trajectoryPDB(value).utf8).base64EncodedString(),"format":"pdb","name":"Public rigid frame \(i)"] }
        let payload=String(decoding:try JSONEncoder().encode(frames),as:UTF8.self)
        print("Check trajectory load")
        _=try evaluate("studioLoadTrajectoryB64(\(payload),true);true",web)
        try wait("studioPocketState().ready && studioPocketState().models===2",web)
        check(try evaluate("(()=>{const [a,b]=studioPocketState().coordinates;return a.length===b.length&&Math.max(...a.map((p,i)=>Math.hypot(...p.map((v,j)=>v-b[i][j]))))<0.01})()",web) as? Bool == true)
        _=try evaluate("document.getElementById('frameSlider').value='1';document.getElementById('frameSlider').dispatchEvent(new Event('input'));true",web)
        try wait("studioPocketState().ready && studioPocketState().frame===1",web)
        check(try evaluate("document.getElementById('playButton').disabled",web) as? Bool == true)
        _=try evaluate("studioSelectImageStyle('illustration');true",web)
        check(try evaluate("!document.getElementById('playButton').disabled && !document.getElementById('overlayButton').disabled",web) as? Bool == true)
        print("Check illustration-to-pocket return")
        _=try evaluate("studioSelectImageStyle('pocket');true",web)
        try wait("studioPocketState().ready",web)
        print("PASS target-aligned trajectory and cycle scrubbing; playback explicitly uses illustration mode")
        _=try evaluate("studioLoadStructureB64(btoa('invalid'),'pdb','Invalid test fixture',false,true);true",web)
        check(try evaluate("studioPocketState().models===0 && !studioPocketState().ready",web) as? Bool == true)
        check(try evaluate("studioPNG()===null",web) as? Bool == true)
        check(try Data(contentsOf:pdbURL)==pdb && Data(contentsOf:cifURL)==cif)
        print("PASS stale-scene rejection and source-file preservation")
    }
}
