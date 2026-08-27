import Foundation

/// Writes the predictor/NanoHunter template YAML for a design request:
/// chain A = nanobody scaffold, chain B = target antigen, plus an optional
/// `nanohunter:` block for epitope-directed contacts.
enum TemplateWriter {
    static func write(_ request: DesignRequest, to url: URL) throws {
        // Chain A = binder. For a nanobody it's the fixed scaffold; for de-novo
        // modes it's a placeholder the runner overwrites via --random-binder.
        let binderA: String
        switch request.designType {
        case .nanobody:
            binderA = clean(request.scaffoldSequence)
            guard !binderA.isEmpty else { throw NHError.message("Scaffold sequence is empty.") }
        case .minibinder, .peptide:
            binderA = String(repeating: "G", count: max(1, request.binderMinLen))
        }

        // Protein targets occupy B, C, D…; a small molecule occupies B.
        let targetBlock: String
        switch request.targetKind {
        case .protein:
            guard case .success(let targets) = request.targetChainResult else {
                throw NHError.message(request.targetSequenceError ?? "Target sequence is invalid.")
            }
            targetBlock = targets.map { target in
                "  - protein:\n      id: \(target.id)\n      sequence: \(target.sequence)\n      msa: empty\n"
            }.joined()
        case .ligand:
            let smiles = request.targetSmiles.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !smiles.isEmpty else { throw NHError.message("Ligand SMILES is empty.") }
            let quoted = smiles.replacingOccurrences(of: "'", with: "''")   // YAML single-quote escape
            targetBlock = "  - ligand:\n      id: B\n      smiles: '\(quoted)'\n"
        }

        var yaml = ""
        // Epitope-directed contacts only make sense for a protein target.
        let epitopeResult = request.hasEpitopeSteering
            ? residueTokenResult(request.epitopeResidues,
                                 allowedTargetChains: request.targetChainIDs)
            : (tokens: [], invalid: [])
        guard epitopeResult.invalid.isEmpty else {
            throw NHError.message("Invalid hotspot residue(s): \(epitopeResult.invalid.joined(separator: ", ")). Use numbers such as 32 55, or chain-qualified residues such as B32 B55.")
        }
        let epitopes = epitopeResult.tokens
        if !epitopes.isEmpty {
            yaml += "nanohunter:\n"
            yaml += "  target_epitope_residues:\n"
            for r in epitopes { yaml += "    - \(r)\n" }
            if request.designPredictor == .protenixConstraint {
                // The validated v0.5 checkpoint consumes a soft pocket made
                // from binder entity 1 and these target residues. Keep this
                // distinct from Boltz's contact restraint contract.
                yaml += "  protenix_pocket_max_distance: 8.0\n"
            } else {
                yaml += "  boltz_contact_distance: 6\n"
                // The runner resolves auto by workflow: nanobody adds a CDR3-centre
                // contact; generic protein binders use the shared pocket restraint.
                yaml += "  boltz_contact_mode: auto\n"
                yaml += "  boltz_contact_force: true\n"
            }
        }
        yaml += "sequences:\n"
        yaml += "  - protein:\n"
        yaml += "      id: A\n"
        yaml += "      sequence: \(binderA)\n"
        yaml += "      msa: empty\n"
        yaml += targetBlock

        // Ligand targeting: a Boltz pocket constraint naming the atoms the
        // binder should wrap around, plus the affinity head.
        //
        // Only positive contacts exist in Boltz — there is no "keep this atom
        // exposed" field. Leaving the linker atoms out of the contact list is
        // therefore a nudge, not a guarantee, and the linker's exposure has to
        // be checked afterwards rather than assumed.
        if request.targetKind == .ligand {
            let atoms = request.ligandContactAtoms.filter { !$0.isEmpty }
            if !atoms.isEmpty {
                yaml += "constraints:\n"
                yaml += "  - pocket:\n"
                yaml += "      binder: A\n"
                yaml += "      contacts:\n"
                for atom in atoms { yaml += "        - [B, \(atom)]\n" }
                yaml += String(format: "      max_distance: %.1f\n", request.ligandContactDistance)
                yaml += "      force: \(request.ligandContactForce)\n"
            }
            if request.ligandAffinityHead && request.usesBoltzAnywhere {
                yaml += "properties:\n"
                yaml += "  - affinity:\n"
                yaml += "      binder: B\n"
            }
        }

        yaml += "version: 1\n"

        try yaml.write(to: url, atomically: true, encoding: .utf8)
    }

    static func clean(_ s: String) -> String {
        String(s.uppercased().unicodeScalars.filter { ("A"..."Z").contains(Character($0)) })
    }

    /// Normalize epitope tokens to chain-qualified residues on the target
    /// (chain B). Accepts bare numbers ("32" -> "B32"), chain-qualified
    /// ("b32" -> "B32"), and colon form ("B:32" -> "B32").
    /// This convenience overload is for the common single-target chain B case.
    static func residueTokens(_ raw: String, targetChain: String = "B") -> [String] {
        residueTokenResult(raw, allowedTargetChains: [targetChain]).tokens
    }

    /// Normalize valid hotspot tokens while retaining invalid input for a loud,
    /// actionable validation error instead of silently dropping typos.
    static func residueTokenResult(_ raw: String, allowedTargetChains: [String] = ["B"])
        -> (tokens: [String], invalid: [String]) {
        let targets = Set(allowedTargetChains.map { $0.uppercased() })
        let defaultTarget = allowedTargetChains.first?.uppercased() ?? "B"
        var tokens: [String] = []
        var invalid: [String] = []
        for tok in raw.split(whereSeparator: { ", ;".contains($0) }) {
            let t = tok.uppercased().replacingOccurrences(of: ":", with: "")
            if t.range(of: "^[0-9]+$", options: .regularExpression) != nil {
                tokens.append(defaultTarget + t)
            } else if t.range(of: "^[A-Z][0-9]+$", options: .regularExpression) != nil,
                      targets.contains(String(t.prefix(1))) {
                tokens.append(t)
            } else {
                invalid.append(String(tok))
            }
        }
        return (tokens, invalid)
    }
}
