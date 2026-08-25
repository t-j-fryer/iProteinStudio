import Foundation

struct ProteinChainInput: Identifiable, Codable, Hashable {
    var id: String
    var sequence: String
}

struct ProteinSequenceInputError: LocalizedError, Equatable {
    let message: String
    var errorDescription: String? { message }
}

/// One definition of the compact protein-complex syntax used across Studio.
/// Whitespace wraps a sequence; a colon starts the next chain. Chain IDs are
/// assigned here so individual predictor adapters never invent their own order.
enum ProteinSequenceInput {
    static let allowedResidues = Set("ACDEFGHIKLMNPQRSTVWYXBZJUO")

    static func chainID(at index: Int) -> String? {
        guard (0..<26).contains(index) else { return nil }
        return String(UnicodeScalar(65 + index)!)
    }

    static func parse(_ raw: String, startingAt start: Int = 0,
                      minimumLength: Int = 1) -> Result<[ProteinChainInput], ProteinSequenceInputError> {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return .failure(.init(message: "Enter at least one protein sequence."))
        }
        if trimmed.contains(">") {
            return .failure(.init(message: "This field takes sequences only. Remove FASTA headers; separate chains with a colon."))
        }
        let pieces = trimmed.split(separator: ":", omittingEmptySubsequences: false)
        guard start >= 0, start + pieces.count <= 26 else {
            return .failure(.init(message: "Studio supports at most \(26 - max(0, start)) chains in this field."))
        }

        var chains: [ProteinChainInput] = []
        for (offset, piece) in pieces.enumerated() {
            guard let id = chainID(at: start + offset) else {
                return .failure(.init(message: "Could not assign a chain identifier."))
            }
            let scalars = piece.uppercased().unicodeScalars.filter {
                !CharacterSet.whitespacesAndNewlines.contains($0)
            }
            let sequence = String(String.UnicodeScalarView(scalars))
            guard !sequence.isEmpty else {
                return .failure(.init(message: "Chain \(id) is empty. Add its sequence or remove the extra colon."))
            }
            let invalid = Set(sequence).filter { !allowedResidues.contains($0) }.sorted()
            guard invalid.isEmpty else {
                return .failure(.init(message: "Chain \(id) contains unsupported character(s): \(String(invalid))."))
            }
            guard sequence.count >= minimumLength else {
                return .failure(.init(message: "Chain \(id) must contain at least \(minimumLength) residues."))
            }
            chains.append(.init(id: id, sequence: sequence))
        }
        return .success(chains)
    }

    static func chains(_ raw: String, startingAt start: Int = 0,
                       minimumLength: Int = 1) -> [ProteinChainInput] {
        guard case .success(let value) = parse(raw, startingAt: start,
                                               minimumLength: minimumLength) else { return [] }
        return value
    }

    static func canonical(_ raw: String, startingAt start: Int = 0) -> String? {
        guard case .success(let chains) = parse(raw, startingAt: start) else { return nil }
        return chains.map(\.sequence).joined(separator: ":")
    }
}
