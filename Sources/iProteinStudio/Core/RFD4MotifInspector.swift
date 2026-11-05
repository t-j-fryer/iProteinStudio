import Foundation
import Combine

struct RFD4MotifInventory: Decodable {
    struct Chain: Decodable, Identifiable {
        let chain: String
        let sequence: String
        var id: String { chain }
    }
    struct Ligand: Decodable, Identifiable {
        let id: String
        let name: String
    }
    struct Residue: Decodable, Identifiable {
        let chain: String
        let residue: Int
        let name: String
        let atoms: [String]
        var id: String { chain + ":" + String(residue) }
    }
    let source_sha256: String
    let preview: String
    let residues: [Residue]
    let chains: [Chain]
    let ligands: [Ligand]
}

final class RFD4MotifInspector: ObservableObject {
    @Published var inventory: RFD4MotifInventory?
    @Published var error: String?
    @Published var running = false
    private var runner: ProcessRunner?
    private var token = UUID()
    private var lines: [String] = []

    func cancel() { token = UUID(); runner?.cancel(); running = false }
    func inspect(source: String) {
        cancel(); inventory = nil; error = nil; lines = []
        let python = AppPaths.support.appendingPathComponent("venvs/NanoHunter_rfd4/bin/python")
        guard FileManager.default.isExecutableFile(atPath: python.path), let pipeline = AppPaths.bundledPipeline else {
            error = "Install RFD4 to inspect native motif atom identities."; return
        }
        let current = token
        do {
            let folder = AppPaths.support.appendingPathComponent("motif_inspections/" + current.uuidString)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            let config = folder.appendingPathComponent("request.json")
            try JSONEncoder().encode(["source": source]).write(to: config, options: .atomic)
            let process = ProcessRunner(); runner = process; running = true
            process.launch(executable: python,
                arguments: ["-B", pipeline.appendingPathComponent("scripts/rfd4_cli.py").path, "inspect-motif", "--root", AppPaths.support.path, "--config", config.path, "--output", folder.path],
                environment: CommandBuilder.environment(), workingDir: AppPaths.support,
                onLine: { [weak self] line in if self?.token == current { self?.lines.append(line) } },
                onExit: { [weak self] status in
                    guard let self, self.token == current else { return }
                    self.running = false
                    if status == 0, let data = try? Data(contentsOf: folder.appendingPathComponent("motif-inspection.json")),
                       let result = try? JSONDecoder().decode(RFD4MotifInventory.self, from: data) { self.inventory = result }
                    else { self.error = "Cannot inspect motif: " + self.lines.suffix(4).joined(separator: " ") }
                })
        } catch { self.error = error.localizedDescription }
    }
}
