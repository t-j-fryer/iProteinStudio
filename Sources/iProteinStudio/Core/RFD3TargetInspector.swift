import Foundation
import Combine

/// Reads a target and reports the sites the user may condition on.
///
/// The point is that the vocabulary comes from the molecule, not from the
/// keyboard. A hand-typed atom name that does not exist would produce an
/// unconditioned design that looks exactly like a successful one — the failure
/// is invisible unless you already know what to look for.
@MainActor
final class RFD3TargetInspector: ObservableObject {
    @Published var sites: [TargetSite] = []
    @Published var chains: [String] = []
    /// The structure chains actually inspected, in target-subunit order.
    @Published var selectedChains: [String] = []
    /// Full-chain contig suggested for a protein target, e.g. "B1-71".
    @Published var suggestedContig: String = ""
    /// Amino-acid sequence extracted from that same structure chain.
    @Published var suggestedSequence: String = ""
    @Published var formalCharge: Int?
    @Published var warnings: [String] = []
    @Published var error: String?
    @Published var isInspecting = false

    private var runner: ProcessRunner?
    private var buffer: [String] = []
    private var inspectionID = UUID()

    var hasResult: Bool { !sites.isEmpty }

    func reset() {
        inspectionID = UUID()
        runner?.cancel()
        runner = nil
        sites = []; chains = []; selectedChains = []; suggestedContig = ""; suggestedSequence = ""; formalCharge = nil
        warnings = []; error = nil
        isInspecting = false
    }

    func inspectLigand(smiles: String) {
        run(["--kind", "ligand", "--smiles", smiles])
    }

    func inspectLigandFile(path: String, residueName: String) {
        run(["--kind", "ligand", "--structure", path, "--resname", residueName])
    }

    func inspectProtein(path: String, chains: [String], expectedChainCount: Int = 1) {
        var args = ["--kind", "protein", "--structure", path]
        if !chains.isEmpty { args += ["--chains", chains.joined(separator: ",")] }
        args += ["--chain-count", String(max(1, expectedChainCount))]
        run(args)
    }

    private func run(_ args: [String]) {
        guard !isInspecting else { return }
        guard let rfd3Root = RFD3Controller.rfd3Root else {
            error = RFD3Controller.unavailableReason ?? "RFdiffusion3 is not available."
            return
        }
        AppPaths.stageRFD3Scripts()
        reset()
        let runID = UUID()
        inspectionID = runID
        isInspecting = true
        buffer = []

        let runner = ProcessRunner()
        self.runner = runner
        runner.launch(
            executable: rfd3Root.appendingPathComponent(".venv/bin/python"),
            arguments: [AppPaths.rfd3InspectScript.path] + args,
            environment: CommandBuilder.environment(),
            workingDir: rfd3Root,
            onLine: { [weak self] line in
                guard self?.inspectionID == runID else { return }
                self?.buffer.append(line)
            },
            onExit: { [weak self] code in self?.finish(code, runID: runID) }
        )
    }

    private func finish(_ code: Int32, runID: UUID) {
        guard inspectionID == runID else { return }
        isInspecting = false
        // The script prints exactly one JSON object; anything else on stdout is
        // library noise, so take the last line that parses.
        guard let payload = buffer.reversed().compactMap({ line -> [String: Any]? in
            guard let data = line.data(using: .utf8),
                  let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            else { return nil }
            return obj
        }).first else {
            error = code == 0
                ? "The target could not be read, and no reason was reported."
                : "The target could not be read. \(buffer.suffix(3).joined(separator: " "))"
            return
        }

        if let message = payload["error"] as? String {
            error = message
            return
        }

        sites = (payload["sites"] as? [[String: Any]] ?? []).map { entry in
            let detailed = entry["suggestions"] as? [[String: Any]] ?? []
            var suggestions = Set(detailed.compactMap { item in
                (item["condition"] as? String).flatMap(AtomCondition.init(rawValue:))
            })
            var reasons: [AtomCondition: String] = [:]
            for item in detailed {
                guard let raw = item["condition"] as? String,
                      let condition = AtomCondition(rawValue: raw),
                      let reason = item["reason"] as? String else { continue }
                reasons[condition] = reason
            }
            // Protein inspection still emits one optional hotspot suggestion.
            if let raw = entry["suggestion"] as? String,
               let condition = AtomCondition(rawValue: raw) {
                suggestions.insert(condition)
                if let reason = entry["suggestionReason"] as? String {
                    reasons[condition] = reason
                }
            }
            return TargetSite(
                atomIndex: entry["index"] as? Int,
                name: entry["name"] as? String ?? "?",
                element: entry["element"] as? String ?? "",
                suggestions: suggestions,
                suggestionReasons: reasons
            )
        }
        chains = payload["chains"] as? [String] ?? []
        selectedChains = payload["selected_chains"] as? [String] ?? []
        suggestedContig = payload["contig"] as? String ?? ""
        suggestedSequence = payload["sequence"] as? String ?? ""
        formalCharge = payload["formal_charge"] as? Int
        warnings = payload["warnings"] as? [String] ?? []
        if sites.isEmpty { error = "No conditionable sites were found in that target." }
    }

    /// Apply every suggestion the inspector made. This is what the "Suggest for
    /// me" button does — it fills in a complete, sane starting point that the
    /// user then edits, rather than leaving them with an empty table.
    func suggestedConditions(presentationAtomIndices: Set<Int> = [])
        -> [String: Set<AtomCondition>] {
        var result: [String: Set<AtomCondition>] = [:]
        for site in sites {
            if let index = site.atomIndex, presentationAtomIndices.contains(index) {
                // An explicitly chosen linker side must remain reachable and
                // must not acquire donor/contact pulls that invite a pocket.
                result[site.name] = [.exposed]
            } else if !site.suggestions.isEmpty {
                result[site.name] = site.suggestions
            }
        }
        return result
    }

    /// Labels in original SMILES atom order, suitable for drawing directly on
    /// the molecule. Missing indices make the mapping incomplete and are never
    /// guessed.
    var atomLabels: [String] {
        let indexed = sites.compactMap { site -> (Int, String)? in
            guard let index = site.atomIndex else { return nil }
            return (index, site.name)
        }.sorted { $0.0 < $1.0 }
        guard indexed.enumerated().allSatisfy({ $0.offset == $0.element.0 }) else { return [] }
        return indexed.map { $0.1 }
    }
}
