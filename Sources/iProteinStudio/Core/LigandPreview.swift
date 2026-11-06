import Foundation
import Combine

/// Input-order display conformer. Never used as a design input or a bound pose.
@MainActor
final class LigandPreview: ObservableObject {
    @Published var payload: String?
    @Published var error: String?
    @Published var busy = false
    @Published var atomElements: [String] = []
    @Published var figure4Preset: LigandGeometryFilter?
    @Published var splitCore: [Int] = []
    @Published var splitLinker: [Int] = []
    private var runner: ProcessRunner?
    private var identity = UUID()
    private var lastKey = ""

    func load(smiles: String, core: Int? = nil, linker: Int? = nil) {
        let key = "\(smiles)|\(core ?? -1)|\(linker ?? -1)"
        guard key != lastKey else { return }
        lastKey = key; runner?.cancel(); identity = UUID()
        let current = identity
        payload = nil; error = nil; atomElements = []; figure4Preset = nil; splitCore = []; splitLinker = []
        guard !smiles.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        // All three shipped chemistry runtimes provide RDKit. Selection is
        // explicit here and this preview never loads weights or owns the GPU.
        let candidates = [AppPaths.support.appendingPathComponent("venvs/NanoHunter_rfd4/bin/python"),
                          AppPaths.support.appendingPathComponent("venvs/NanoHunter_boltz/bin/python"),
                          AppPaths.rfd3Root.appendingPathComponent(".venv/bin/python")]
        guard let python = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0.path) }),
              let script = AppPaths.bundledRFD3Scripts?.appendingPathComponent("ligand_preview.py") else {
            error = "Install a molecule design engine to generate the 3D preview."; return
        }
        var request: [String: Any] = ["smiles": smiles]
        if let core, let linker { request["core"] = core; request["linker"] = linker }
        guard let data = try? JSONSerialization.data(withJSONObject: request), let json = String(data: data, encoding: .utf8) else { return }
        busy = true
        let process = ProcessRunner(); runner = process
        process.launch(executable: python, arguments: ["-B", script.path, "--json", json],
                       environment: CommandBuilder.environment(), workingDir: AppPaths.support,
                       onLine: { [weak self] line in
            guard let self, self.identity == current, let data = line.data(using: .utf8),
                  let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
            if let message = value["error"] as? String { self.error = message; return }
            guard let atoms = value["atoms"] as? [[String: Any]] else { return }
            self.payload = data.base64EncodedString()
            self.atomElements = atoms.map { $0["element"] as? String ?? "?" }
            if let raw = value["figure4_preset"], !(raw is NSNull), let encoded = try? JSONSerialization.data(withJSONObject: raw) {
                self.figure4Preset = try? JSONDecoder().decode(LigandGeometryFilter.self, from: encoded)
            }
            if let split = value["split"] as? [String: [Int]] { self.splitCore = split["core"] ?? []; self.splitLinker = split["linker"] ?? [] }
        }, onExit: { [weak self] code in
            guard let self, self.identity == current else { return }
            self.busy = false
            if code != 0 && self.error == nil { self.error = "Could not prepare the molecule preview." }
        })
    }
}
