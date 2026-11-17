import SwiftUI
import WebKit

enum AppPaths {
    static var webRoot: URL? {
        URL(fileURLWithPath: CommandLine.arguments[1]).appendingPathComponent("Sources/iProteinStudio/Resources/web")
    }
}

@main struct MolartViewerHarness {
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
        guard CommandLine.arguments.count==5 else {fatalError("usage: ROOT PUBLIC_PDB PUBLIC_CIF OUTPUT_DIRECTORY")}
        setbuf(stdout,nil);_=NSApplication.shared;NSApp.setActivationPolicy(.accessory)
        let pdbURL=URL(fileURLWithPath:CommandLine.arguments[2]), cifURL=URL(fileURLWithPath:CommandLine.arguments[3])
        let pdb=try Data(contentsOf:pdbURL),cif=try Data(contentsOf:cifURL)
        let out=URL(fileURLWithPath:CommandLine.arguments[4]);try FileManager.default.createDirectory(at:out,withIntermediateDirectories:true)
        let host=NSHostingView(rootView:Py2DmolViewer(structurePath:pdbURL.path,selection:nil,showsControls:true))
        let window=NSWindow(contentRect:NSRect(x:0,y:0,width:1000,height:760),styleMask:[.titled],backing:.buffered,defer:false)
        window.contentView=host;window.orderFront(nil)
        while descendants(host).compactMap({$0 as? WKWebView}).isEmpty {spin()}
        let web=descendants(host).compactMap{$0 as? WKWebView}.first!
        try wait("typeof studioMolartState==='function' && studioSurfaceBridge.renderer.currentFrame>=0",web)
        check(try evaluate("typeof StudioMolart==='undefined'",web) as? Bool == true)
        _=try evaluate("window.chooseMolartStyle=id=>{studioSelectImageStyle('molart');document.getElementById('molartChain').value='';document.getElementById('molartChain').dispatchEvent(new Event('change'));document.getElementById('molartChainStyle').value=id;document.getElementById('molartChainStyle').dispatchEvent(new Event('change'));};studioSelectImageStyle('molart');true",web)
        try wait("studioMolartState().ready",web)
        check(try evaluate("JSON.stringify([...document.querySelectorAll('#imageStyle option')].map(o=>o.value))===JSON.stringify(['illustration','pocket','molart']) && StudioMolart.styles.length===21 && StudioMolart.styles.every(s=>document.querySelector('#molartChainStyle option[value=\"'+s.id+'\"]'))",web) as? Bool == true)
        check(try evaluate("studioPNG()===null && document.getElementById('imageStyle').value==='molart' && document.getElementById('molartChainStyle').value==='normal' && document.getElementById('molartNote').hidden && !document.getElementById('molartPanel').textContent.includes('MIT licence')",web) as? Bool == true)
        let fingerprint=try evaluate("studioMolartState().engine.fingerprint",web) as! String
        _=try evaluate("(()=>{window.fixtureHashes={};for(const s of StudioMolart.styles){chooseMolartStyle(s.id);if(!studioMolartState().ready)throw Error(studioMolartState().error);if(document.getElementById('imageStyle').value!=='molart'||document.getElementById('molartChainStyle').value!==s.id||studioMolartState().style!==s.id||!document.getElementById('molartNote').hidden)throw Error('Selector/status mismatch '+s.id);const px=studioMolartPixels(96);if(!px.some((v,i)=>i%4!==3&&v<240))throw Error('Blank '+s.id);let h=0;for(const v of px)h=(Math.imul(h,31)+v)|0;fixtureHashes[s.id]=h;if(!studioMolartState().engine.unchanged)throw Error('Coordinates changed');}return true})()",web)
        let hashes=try evaluate("JSON.stringify(fixtureHashes)",web) as! String
        try Data(hashes.utf8).write(to:out.appendingPathComponent("style-hashes.json"))
        print("PASS all21upstream styles render nonblank pixels in native offline WebKit; source coordinate fingerprint unchanged")
        _=try evaluate("chooseMolartStyle('glass');true",web)
        let before=try evaluate("JSON.stringify(studioMolartState().engine.camera)",web) as! String
        // Synthetic DOM pointer events cannot acquire trusted pointer capture.
        // Shim only that browser primitive in the fixture; upstream Trackball
        // handlers and camera mathematics still consume the full drag gesture.
        _=try evaluate("(()=>{const c=document.querySelector('#molartCanvas canvas'),r=c.getBoundingClientRect(),capture=c.setPointerCapture,release=c.releasePointerCapture;c.setPointerCapture=()=>{};c.releasePointerCapture=()=>{};try{for(const[type,x,y,buttons]of [['pointerdown',200,200,1],['pointermove',320,245,1],['pointerup',320,245,0]])c.dispatchEvent(new PointerEvent(type,{bubbles:true,pointerId:1,pointerType:'mouse',button:0,buttons,clientX:r.x+x,clientY:r.y+y}));}finally{c.setPointerCapture=capture;c.releasePointerCapture=release;}return true})()",web)
        try wait("JSON.stringify(studioMolartState().engine.camera)!=="+js(before),web)
        let rotated=try evaluate("JSON.stringify(studioMolartState().engine.camera)",web) as! String
        // Verify zoom independently from the actual native drag.
        _=try evaluate("document.querySelector('#molartCanvas canvas').dispatchEvent(new WheelEvent('wheel',{bubbles:true,deltaY:180}));true",web)
        try wait("JSON.stringify(studioMolartState().engine.camera)!=="+js(rotated),web)
        check(try evaluate("studioMolartState().engine.unchanged",web) as? Bool == true)
        _=try evaluate("document.getElementById('molartArt').checked=true;document.getElementById('molartArt').dispatchEvent(new Event('change'));true",web)
        check(try evaluate("studioMolartState().art && !document.getElementById('molartArtWarning').hidden && studioMolartState().engine.unchanged",web) as? Bool == true)
        _=try evaluate("document.getElementById('molartArt').checked=false;document.getElementById('molartArt').dispatchEvent(new Event('change'));document.getElementById('molartSun').checked=true;document.getElementById('molartSun').dispatchEvent(new Event('change'));true",web)
        _=try evaluate("document.getElementById('molartSeed').value='';document.getElementById('molartSeed').dispatchEvent(new Event('change'));true",web)
        check(try evaluate("document.getElementById('saveImageButton').disabled && studioMolartState().ready && !document.getElementById('molartNote').hidden",web) as? Bool == true)
        _=try evaluate("document.getElementById('molartSeed').value='42';document.getElementById('molartSeed').dispatchEvent(new Event('change'));true",web)
        check(try evaluate("!document.getElementById('saveImageButton').disabled && studioMolartState().ready && document.getElementById('molartNote').hidden",web) as? Bool == true)
        // Exercise the same asynchronous export path as the native Save button.
        _=try evaluate("window.fixturePNG=null;document.getElementById('molartExportSize').value='1024';studioMolartPNG().then(x=>window.fixturePNG=x);true",web)
        try wait("typeof fixturePNG==='string'",web)
        let uri=try evaluate("fixturePNG",web) as! String
        let image=Data(base64Encoded:String(uri.dropFirst("data:image/png;base64,".count)))!
        check(image.starts(with:[137,80,78,71,13,10,26,10]));try image.write(to:out.appendingPathComponent("glass.png"))
        print("PASS camera interaction, explicit art mode warning, sun controls and actual PNG export")
        _=try evaluate("studioLoadStructureB64(\(js(cif.base64EncodedString())),'cif','T4.cif',true,true);true",web)
        try wait("studioMolartState().ready",web)
        check(try evaluate("studioMolartState().engine.fingerprint",web) as! String == fingerprint)
        check(try evaluate("!studioMolartState().art && studioMolartState().selectable && document.getElementById('molartNote').hidden && document.getElementById('molartNote').textContent==='' && !document.getElementById('molartTechnique')",web) as? Bool == true)
        // Build a display-only two-chain complex and a rigidly transformed copy.
        let lines=String(decoding:pdb,as:UTF8.self).split(separator:"\n").map(String.init).filter{$0.hasPrefix("ATOM  ")}
        func transformed(_ moved:Bool)->String {
            var result:[String]=[]
            for chain in ["A","B"] {for line in lines {
                var chars=Array(line);guard chars.count>=54 else {continue};chars[21]=Character(chain)
                let x=Double(String(chars[30..<38]).trimmingCharacters(in:.whitespaces))!,y=Double(String(chars[38..<46]).trimmingCharacters(in:.whitespaces))!,z=Double(String(chars[46..<54]).trimmingCharacters(in:.whitespaces))!
                let shiftedX=x+(chain=="A" ? 30:0)
                let xyz=moved ? [y+20,-shiftedX+7,z-4]:[shiftedX,y,z]
                chars.replaceSubrange(30..<54,with:Array(String(format:"%8.3f%8.3f%8.3f",xyz[0],xyz[1],xyz[2])));result.append(String(chars))
            }};return result.joined(separator:"\n")+"\nEND\n"
        }
        let payload=[false,true].enumerated().map{i,moved in ["encoded":Data(transformed(moved).utf8).base64EncodedString(),"format":"pdb","name":"Synthetic rigid cycle \(i).pdb"]}
        let payloadJSON=String(decoding:try JSONEncoder().encode(payload),as:UTF8.self)
        _=try evaluate("studioLoadTrajectoryB64(\(payloadJSON),true);true",web)
        try wait("studioMolartState().ready && studioMolartState().info.chains.length===2",web)
        _=try evaluate("document.getElementById('molartChain').value='A';document.getElementById('molartChain').dispatchEvent(new Event('change'));document.getElementById('molartChainStyle').value='klimt';document.getElementById('molartChainStyle').dispatchEvent(new Event('change'));true",web)
        check(try evaluate("studioMolartState().engine.chains.A==='klimt' && document.getElementById('imageStyle').value==='molart'",web) as? Bool == true)
        let cycleCamera=try evaluate("JSON.stringify(studioMolartState().engine.camera)",web) as! String
        _=try evaluate("document.getElementById('frameSlider').value='1';document.getElementById('frameSlider').dispatchEvent(new Event('input'));true",web)
        try wait("studioMolartState().ready && studioMolartState().frame===1",web)
        check(try evaluate("document.getElementById('playButton').disabled && studioMolartState().engine.unchanged",web) as? Bool == true)
        check(try evaluate("JSON.stringify(studioMolartState().engine.camera)",web) as! String == cycleCamera)
        print("PASS exact PDB/CIF coordinates, per-chain style, target-aligned cycle scrubbing and explicit playback limits")
        for _ in 0..<4 {
            _=try evaluate("studioSelectImageStyle('illustration');true",web)
            check(try evaluate("!studioMolartState().active && studioMolartState().engine===null",web) as? Bool == true)
            _=try evaluate("chooseMolartStyle('glass');true",web);try wait("studioMolartState().ready",web)
        }
        _=try evaluate("studioSelectImageStyle('pocket');true",web);try wait("studioPocketState().ready",web)
        check(try evaluate("!studioMolartState().active && document.getElementById('playButton').disabled",web) as? Bool == true)
        _=try evaluate("chooseMolartStyle('normal');true",web);try wait("studioMolartState().ready",web)
        _=try evaluate("studioLoadStructureB64(btoa('invalid'),'pdb','invalid.pdb',false,true);true",web)
        check(try evaluate("!studioMolartState().ready && studioMolartState().engine===null && document.getElementById('saveImageButton').disabled",web) as? Bool == true)
        check(try evaluate("studioMolartState().created===studioMolartState().disposed",web) as? Bool == true)
        check(try evaluate("performance.getEntriesByType('resource').every(x=>!/^https?:/.test(x.name))",web) as? Bool == true)
        check(try Data(contentsOf:pdbURL)==pdb && Data(contentsOf:cifURL)==cif)
        try Data("PASS all styles, export, coordinates, chain overrides, offline switching and lifecycle cleanup\n".utf8).write(to:out.appendingPathComponent("PASS.txt"))
        print("PASS lazy load, repeated disposal/recreation, pocket handoff, stale-scene rejection, offline resource use and immutable files")
    }
}
