import Foundation

@main struct ChimeraXStyleHarness {
    static func main() throws {
        if CommandLine.arguments.count >= 3 {
            let source = URL(fileURLWithPath: CommandLine.arguments[1])
            let script = try ChimeraXPublicationStyle.script(structure: source, emphasizedChains: CommandLine.arguments.count > 3 ? CommandLine.arguments[3] : "")
            try script.write(toFile: CommandLine.arguments[2], atomically: true, encoding: .utf8)
            return
        }
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let source = directory.appendingPathComponent("quoted ' ; unicode α.pdb")
        try Data("synthetic".utf8).write(to: source)
        let script = try ChimeraXPublicationStyle.script(structure: source)
        precondition(script.contains("sha256") && !script.contains("close all"))
        precondition(script.contains("model.atomspec") && script.contains("60 target s") && script.contains("55 target s"))
        do { _ = try ChimeraXPublicationStyle.script(structure: source, emphasizedChains: "A; close all"); preconditionFailure("Unsafe chain spec accepted") }
        catch { }
        print("PASS scoped, hash-bound manuscript style generation and unsafe chain rejection")
    }
}
