import Foundation
import Combine

/// Resolves the atom names Boltz will use for a ligand, so pocket constraints
/// can address them.
///
/// These names are a trap for the unwary and the reason this is a separate
/// object rather than a computed property. Boltz derives them from RDKit's
/// canonical ranking, and enabling the affinity head standardises the SMILES
/// *first*, which renumbers everything: the same linker atoms are O17/C24/N44
/// with the affinity head off and O19/C26/N46 with it on. A cached name reused
/// across that change silently constrains the wrong atoms — the run succeeds and
/// the pocket is built somewhere else entirely.
@MainActor
final class BoltzLigandAtoms: ObservableObject {
    struct Atom: Hashable, Identifiable {
        var name: String
        var element: String
        var id: String { name }
    }

    @Published var atoms: [Atom] = []
    /// Boltz name for each heavy atom of the input SMILES, in depiction order,
    /// so a click on the 2D structure becomes the right name.
    @Published var namesByInputIndex: [String] = []
    @Published var standardized = false
    @Published var isResolving = false
    @Published var error: String?
    /// The SMILES + affinity setting these names were generated for.
    @Published var generatedFor: String = ""

    private var runner: ProcessRunner?
    private var buffer: [String] = []
    private var resolutionID = UUID()

    var hasAtoms: Bool { !atoms.isEmpty }
    var canPickOnStructure: Bool { !namesByInputIndex.isEmpty }

    func reset() {
        resolutionID = UUID()
        runner?.cancel()
        runner = nil
        atoms = []; namesByInputIndex = []; error = nil; generatedFor = ""; standardized = false
        isResolving = false
    }

    /// Must run in the Boltz environment: the standardisation step has to be the
    /// one Boltz itself will apply, not a lookalike.
    func resolve(smiles: String, affinityHead: Bool) {
        guard !isResolving else { return }
        let trimmed = smiles.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { reset(); return }

        let boltz = AppPaths.support.appendingPathComponent("venvs/NanoHunter_boltz/bin/python")
        guard AppPaths.fm.fileExists(atPath: boltz.path) else {
            error = "Boltz isn't installed, so ligand atom names can't be resolved."
            return
        }
        AppPaths.stageRFD3Scripts()

        let key = "\(trimmed)|\(affinityHead ? 1 : 0)"
        reset()
        let runID = UUID()
        resolutionID = runID
        isResolving = true
        buffer = []

        let runner = ProcessRunner()
        self.runner = runner
        runner.launch(
            executable: boltz,
            arguments: [AppPaths.boltzLigandAtomsScript.path, trimmed, affinityHead ? "1" : "0"],
            environment: CommandBuilder.environment(),
            workingDir: AppPaths.support,
            onLine: { [weak self] line in
                guard self?.resolutionID == runID else { return }
                self?.buffer.append(line)
            },
            onExit: { [weak self] code in self?.finish(code, key: key, runID: runID) }
        )
    }

    private func finish(_ code: Int32, key: String, runID: UUID) {
        guard resolutionID == runID else { return }
        isResolving = false
        for line in buffer.reversed() {
            guard let data = line.data(using: .utf8),
                  let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            else { continue }
            if let message = payload["error"] as? String { error = message; return }
            guard let raw = payload["atoms"] as? [[String: Any]] else { continue }
            atoms = raw.compactMap { entry in
                guard let name = entry["name"] as? String else { return nil }
                return Atom(name: name, element: entry["el"] as? String ?? "")
            }
            namesByInputIndex = payload["input_order_names"] as? [String] ?? []
            standardized = payload["standardized"] as? Bool ?? false
            generatedFor = key
            return
        }
        error = code == 0 ? "No atom names were produced." : "Could not resolve the ligand atom names."
    }
}
