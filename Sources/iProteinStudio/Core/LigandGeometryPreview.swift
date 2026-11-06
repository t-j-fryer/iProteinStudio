import Foundation
import Combine

@MainActor
final class LigandGeometryPreview: ObservableObject {
    @Published var structurePath: String?
    @Published var result: [String: Any]?
    @Published var error: String?
    @Published var busy = false
    private var runner: ProcessRunner?
    private var identity = UUID()
    func load(_ structure: URL) {
        runner?.cancel(); identity = UUID(); let id = identity
        result = nil; error = nil; busy = true; structurePath = structure.path
        guard let helper = AppPaths.bundledPipeline?.appendingPathComponent("scripts/ligand_geometry.py") else { error = "Missing geometry viewer helper."; busy = false; return }
        let process = ProcessRunner(); runner = process
        process.launch(executable: AppPaths.support.appendingPathComponent("venvs/NanoHunter_boltz/bin/python"),
            arguments: ["-B", helper.path, "recorded", "--structure", structure.path],
            environment: CommandBuilder.environment(), workingDir: AppPaths.support,
            onLine: { [weak self] line in
                guard let self, self.identity == id else { return }
                if let data = line.data(using: .utf8), let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any], value["cone"] != nil { self.result = value }
                else { self.error = line }
            }, onExit: { [weak self] code in
                guard let self, self.identity == id else { return }; self.busy = false
                if code == 0 { self.error = nil }
                else if self.error == nil { self.error = "Could not read a matching recorded linker-exit calculation." }
            })
    }
    static func hasRecordedGeometry(_ structure: URL) -> Bool {
        structure.pathComponents.count > 2 && sequence(first: structure.deletingLastPathComponent(), next: { parent in
            let next = parent.deletingLastPathComponent(); return next == parent ? nil : next
        }).prefix(12).contains { FileManager.default.fileExists(atPath: $0.appendingPathComponent("geometry_receipts").path) }
    }
}
