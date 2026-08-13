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
    /// Full-chain contig suggested for a protein target, e.g. "B1-71".
    @Published var suggestedContig: String = ""
    @Published var formalCharge: Int?
    @Published var warnings: [String] = []
    @Published var error: String?
    @Published var isInspecting = false

    private var runner: ProcessRunner?
    private var buffer: [String] = []

    var hasResult: Bool { !sites.isEmpty }

    func reset() {
        sites = []; chains = []; suggestedContig = ""; formalCharge = nil
        warnings = []; error = nil
    }

    func inspectLigand(smiles: String) {
        run(["--kind", "ligand", "--smiles", smiles])
    }

    func inspectLigandFile(path: String, residueName: String) {
        run(["--kind", "ligand", "--structure", path, "--resname", residueName])
    }

    func inspectProtein(path: String, chain: String) {
        var args = ["--kind", "protein", "--structure", path]
        if !chain.isEmpty { args += ["--chain", chain] }
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
        isInspecting = true
        buffer = []

        let runner = ProcessRunner()
        self.runner = runner
        runner.launch(
            executable: rfd3Root.appendingPathComponent(".venv/bin/python"),
            arguments: [AppPaths.rfd3InspectScript.path] + args,
            environment: CommandBuilder.environment(),
            workingDir: rfd3Root,
            onLine: { [weak self] line in self?.buffer.append(line) },
            onExit: { [weak self] code in self?.finish(code) }
        )
    }

    private func finish(_ code: Int32) {
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
            TargetSite(
                name: entry["name"] as? String ?? "?",
                element: entry["element"] as? String ?? "",
                suggestion: (entry["suggestion"] as? String).flatMap(AtomCondition.init(rawValue:)),
                suggestionReason: entry["suggestionReason"] as? String
            )
        }
        chains = payload["chains"] as? [String] ?? []
        suggestedContig = payload["contig"] as? String ?? ""
        formalCharge = payload["formal_charge"] as? Int
        warnings = payload["warnings"] as? [String] ?? []
        if sites.isEmpty { error = "No conditionable sites were found in that target." }
    }

    /// Apply every suggestion the inspector made. This is what the "Suggest for
    /// me" button does — it fills in a complete, sane starting point that the
    /// user then edits, rather than leaving them with an empty table.
    func suggestedConditions() -> [String: Set<AtomCondition>] {
        var result: [String: Set<AtomCondition>] = [:]
        for site in sites {
            if let suggestion = site.suggestion { result[site.name] = [suggestion] }
        }
        return result
    }
}
