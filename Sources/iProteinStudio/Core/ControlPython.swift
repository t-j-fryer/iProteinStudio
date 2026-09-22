import Foundation

/// A private standalone interpreter, never Apple's developer-tools shim.
enum ControlPython {
    static func executable(root: URL) -> URL {
        let portable = root.appendingPathComponent("components/control/current/python/bin/python3")
        if FileManager.default.isExecutableFile(atPath: portable.path) { return portable }
        // This exact bootstrap version is installed by setup_pipeline.sh.
        return root.appendingPathComponent("toolchains/python/cpython-3.11.13-macos-aarch64-none/bin/python3")
    }
}
