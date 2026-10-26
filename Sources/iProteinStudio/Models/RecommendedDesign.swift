import Foundation

enum RecommendedDesign {
    struct Hotspots {
        var numbers: [Int] = []
        var qualified: [String] = []
    }
    static func hotspots(_ text: String) -> Hotspots? {
        var result = Hotspots()
        for token in text.split(whereSeparator: { $0 == "," || $0.isWhitespace }) {
            if let number = Int(token), number > 0 { result.numbers.append(number) }
            else if token.range(of: "^([A-Za-z][1-9][0-9]*|[A-Za-z0-9]+:[1-9][0-9]*)$", options: .regularExpression) != nil {
                result.qualified.append(String(token))
            } else { return nil }
        }
        return result
    }
    /// Sequence inputs have known 1-based residue bounds before any prediction runs.
    static func hotspotIssues(_ hotspots: Hotspots, chainLengths: [String: Int]) -> [String] {
        if chainLengths.count > 1 && !hotspots.numbers.isEmpty {
            return ["For multiple target chains, include the chain: B32 C55."]
        }
        var residues = hotspots.qualified.compactMap { token -> (String, Int)? in
            if let separator = token.firstIndex(of: ":") {
                guard let number = Int(token[token.index(after: separator)...]) else { return nil }
                return (String(token[..<separator]), number)
            }
            guard let chain = token.first, let number = Int(token.dropFirst()) else { return nil }
            return (String(chain), number)
        }
        if let chain = chainLengths.keys.first, chainLengths.count == 1 {
            residues += hotspots.numbers.map { (chain, $0) }
        }
        var seen = Set<String>()
        var issues: [String] = []
        for (chain, number) in residues {
            let residue = "\(chain)\(number)"
            guard let length = chainLengths[chain], (1...length).contains(number) else {
                issues.append("Hotspot \(residue) is outside the supplied target sequences.")
                continue
            }
            if !seen.insert(residue).inserted { issues.append("Hotspot \(residue) is repeated.") }
        }
        return issues
    }
    static func request(intention: DesignIntention, hard: Bool, minutes: Double) -> RFD4Request {
        var value = RFD4Request()
        value.task = intention == .nanobody ? .nanobody : intention == .smallMolecule ? .ligand : .protein
        value.length = 120
        value.count = 10000
        value.time_budget_minutes = minutes
        value.target_msa = intention == .smallMolecule ? "empty" : "auto"
        value.search = hard ? .beam : .native
        value.assess_native = !hard
        value.cycles = 7; value.proposals = 4; value.beam_width = 4
        if intention == .nanobody {
            value.scaffold_id = "7xl0_vobarilizumab"
            value.cdr_ranges = "CDR1:26-33,CDR2:51-57,CDR3:97-110"
            value.scaffold_msa = "auto"
            value.sequence_model = "abmpnn"
        } else if intention == .smallMolecule {
            value.predictor = "boltz"; value.sequence_model = "lasermpnn"
            value.temperature = 0.5
        }
        return value
    }
}

extension DesignIntention {
    var rfd4Tasks: [RFD4Task] {
        switch self {
        case .monomer: return [.monomer]
        case .minibinder: return [.protein]
        case .nanobody: return [.nanobody]
        case .smallMolecule: return [.ligand]
        case .motif: return [.motif, .annotated]
        case .optimize: return [.partial, .inverse]
        }
    }
}
