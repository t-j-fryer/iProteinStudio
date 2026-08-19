import Foundation
import Combine

/// One conformational state the ligand can adopt.
struct LigandState: Codable, Hashable, Identifiable {
    var id: String                  // "A", "B", …
    var nMembers: Int
    var ensembleFraction: Double
    var relativeEnergy: Double      // kcal/mol above the best conformer found
    var pdbEntries: [String]
    var recommended: Bool
    var share: Int                  // percent of the design budget
    var sdf: String?

    private enum CodingKeys: String, CodingKey {
        case id, nMembers = "n_members", ensembleFraction = "ensemble_fraction"
        case relativeEnergy = "relative_energy", pdbEntries = "pdb_entries"
        case recommended, share, sdf
    }

    var hasExperimentalSupport: Bool { !pdbEntries.isEmpty }

    /// Why this state was or was not recommended, in the user's terms.
    var justification: String {
        if !recommended {
            if relativeEnergy > 6 && ensembleFraction < 0.05 {
                return "Rare and strained — not worth spending designs on."
            }
            return "Beyond the number of states worth splitting the budget across."
        }
        if hasExperimentalSupport {
            let n = pdbEntries.count
            return "Seen in \(n) experimental structure\(n == 1 ? "" : "s"), so this is a shape the molecule demonstrably adopts."
        }
        if ensembleFraction >= 0.3 {
            return "A large share of the low-energy ensemble, but not observed experimentally."
        }
        return "A distinct low-energy shape worth covering, though not seen experimentally."
    }
}

/// A note from the chemistry check.
struct LigandNote: Codable, Hashable, Identifiable {
    var level: String       // "warning" | "info"
    var title: String
    var detail: String
    var id: String { title }
    var isWarning: Bool { level == "warning" }
}

/// The full analysis of a small molecule.
struct LigandAnalysis: Codable, Hashable {
    struct Core: Codable, Hashable {
        var coreAtoms: [Int]
        var presentationAtoms: [Int]
        var rule: String
        var coreRotatableBonds: Int
        var totalRotatableBonds: Int
        private enum CodingKeys: String, CodingKey {
            case coreAtoms = "core_atoms", presentationAtoms = "presentation_atoms"
            case rule, coreRotatableBonds = "core_rotatable_bonds"
            case totalRotatableBonds = "total_rotatable_bonds"
        }
    }
    struct Ensemble: Codable, Hashable {
        var requested: Int
        var keptAfterStrainFilter: Int
        var strainWindowKcal: Double
        var clusterRMSDUsed: Double
        var clusters: Int
        private enum CodingKeys: String, CodingKey {
            case requested, keptAfterStrainFilter = "kept_after_strain_filter"
            case strainWindowKcal = "strain_window_kcal"
            case clusterRMSDUsed = "cluster_rmsd_used", clusters
        }
    }
    struct PDBEvidence: Codable, Hashable {
        var searched: Bool
        var ccdCodes: [String]
        var nEntries: Int
        var nInstancesUsed: Int
        var nInstancesMatched: Int
        var nInstancesUnmatched: Int
        var note: String
        private enum CodingKeys: String, CodingKey {
            case searched, ccdCodes = "ccd_codes", nEntries = "n_entries"
            case nInstancesUsed = "n_instances_used", nInstancesMatched = "n_instances_matched"
            case nInstancesUnmatched = "n_instances_unmatched"
            case note
        }
    }
    struct Flexibility: Codable, Hashable {
        var level: String       // low | moderate | high
        var rationale: String
    }

    var smiles: String
    var atomNames: [String]
    var forceField: String
    var qa: [LigandNote]
    var core: Core
    var ensemble: Ensemble
    var pdb: PDBEvidence
    var flexibility: Flexibility
    var states: [LigandState]

    private enum CodingKeys: String, CodingKey {
        case smiles, atomNames = "atom_names", forceField = "force_field"
        case qa, core, ensemble, pdb, flexibility, states
    }

    var recommendedStates: [LigandState] { states.filter(\.recommended) }

    var headline: String {
        switch flexibility.level {
        case "low":      return "Rigid enough for one geometry"
        case "moderate": return "A few distinct shapes"
        default:         return "Many accessible shapes"
        }
    }
}

/// Runs the ligand analysis and holds its result.
///
/// The point of this layer is to stop a novice silently designing a pocket
/// around one arbitrary geometry of a floppy molecule. That run does not fail —
/// it produces confident-looking numbers for a shape the molecule may rarely
/// adopt — so nothing downstream can catch it.
@MainActor
final class LigandIntelligence: ObservableObject {
    @Published var analysis: LigandAnalysis?
    @Published var isRunning = false
    @Published var error: String?
    /// Which states the user has chosen to design against, by id.
    @Published var selected: Set<String> = []

    private var runner: ProcessRunner?
    private var buffer: [String] = []
    private var analysisID = UUID()

    var hasResult: Bool { analysis != nil }

    func reset() {
        analysisID = UUID()
        runner?.cancel()
        runner = nil
        analysis = nil; error = nil; selected = []
        isRunning = false
    }

    /// Design budget split across the states the user actually selected.
    /// Re-normalised, because unticking a state should give its share to the
    /// others rather than quietly shrinking the campaign.
    func plan() -> [(state: LigandState, share: Int)] {
        guard let analysis else { return [] }
        let chosen = analysis.states.filter { selected.contains($0.id) }
        guard !chosen.isEmpty else { return [] }
        let total = chosen.reduce(0) { $0 + max(1, $1.share) }
        var shares = chosen.map { Int((Double(max(1, $0.share)) / Double(total) * 100).rounded()) }
        if let index = shares.indices.max(by: { shares[$0] < shares[$1] }) {
            shares[index] += 100 - shares.reduce(0, +)
        }
        return Array(zip(chosen, shares))
    }

    func analyse(smiles: String, attachmentAtom: Int?, attachmentLinkerAtom: Int? = nil,
                 attachmentSymbol: String? = nil, attachmentLinkerSymbol: String? = nil,
                 searchPDB: Bool, outputDir: URL) {
        guard !isRunning else { return }
        guard let rfd3Root = RFD3Controller.rfd3Root else {
            error = RFD3Controller.unavailableReason ?? "RFdiffusion3 is not available."
            return
        }
        AppPaths.stageRFD3Scripts()
        reset()
        let runID = UUID()
        analysisID = runID
        isRunning = true
        buffer = []

        var request: [String: Any] = [
            "smiles": smiles,
            "search_pdb": searchPDB,
            "output_dir": outputDir.path,
        ]
        // JSONSerialization does not have a stable contract for Optional.none
        // boxed as Any. Omit absent endpoints explicitly; the Python boundary
        // treats omission as a free molecule.
        if let attachmentAtom { request["attachment_atom"] = attachmentAtom }
        if let attachmentLinkerAtom { request["attachment_linker_atom"] = attachmentLinkerAtom }
        if let attachmentSymbol { request["attachment_symbol"] = attachmentSymbol }
        if let attachmentLinkerSymbol {
            request["attachment_linker_symbol"] = attachmentLinkerSymbol
        }

        let requestURL = outputDir.appendingPathComponent("ligand_request.json")
        do {
            try AppPaths.fm.createDirectory(at: outputDir, withIntermediateDirectories: true)
            try JSONSerialization.data(withJSONObject: request, options: [.prettyPrinted])
                .write(to: requestURL)
        } catch {
            self.error = "Could not start the analysis: \(error.localizedDescription)"
            isRunning = false
            return
        }

        let runner = ProcessRunner()
        self.runner = runner
        runner.launch(
            executable: rfd3Root.appendingPathComponent(".venv/bin/python"),
            arguments: [AppPaths.rfd3LigandScript.path, requestURL.path],
            environment: CommandBuilder.environment(),
            workingDir: rfd3Root,
            onLine: { [weak self] line in
                guard self?.analysisID == runID else { return }
                self?.buffer.append(line)
            },
            onExit: { [weak self] code in self?.finish(code, runID: runID) }
        )
    }

    func cancel() {
        analysisID = UUID()
        runner?.cancel()
        runner = nil
        isRunning = false
    }

    private func finish(_ code: Int32, runID: UUID) {
        guard analysisID == runID else { return }
        isRunning = false
        // The script prints exactly one JSON object; take the last line that parses,
        // because RDKit and the network stack both write to stdout uninvited.
        let decoder = JSONDecoder()
        for line in buffer.reversed() {
            guard let data = line.data(using: .utf8) else { continue }
            if let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let message = payload["error"] as? String {
                error = message
                return
            }
            if let decoded = try? decoder.decode(LigandAnalysis.self, from: data) {
                analysis = decoded
                selected = Set(decoded.recommendedStates.map(\.id))
                return
            }
        }
        error = code == 0
            ? "The analysis produced no result."
            : "The analysis failed. \(buffer.suffix(3).joined(separator: " "))"
    }
}
