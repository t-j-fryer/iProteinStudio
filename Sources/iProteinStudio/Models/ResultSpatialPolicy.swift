import Foundation
import CryptoKit

struct ResultSpatialPolicy: Codable, Equatable {
    enum Mode: String, Codable, CaseIterable { case protein, ligand }
    enum Coverage: String, Codable, CaseIterable { case all, any }
    var schema = 1
    var mode: Mode = .protein
    var binderChains = ""
    var targetChain = ""
    var residues = ""
    var ligandResidue = ""
    var atoms = ""
    var cutoff = "8"
    var coverage: Coverage = .all
    var requireGeometry = false
    var minimumBurial = ""
    var maximumBurial = ""

    var json: Data { let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]; return (try? encoder.encode(self)) ?? Data() }
    var digest: String { SHA256.hash(data: json).map { String(format: "%02x", $0) }.joined() }
    private func number(_ text: String) -> Double? { Double(text.trimmingCharacters(in: .whitespacesAndNewlines)).flatMap { $0.isFinite ? $0 : nil } }
    var validationMessage: String? {
        if schema != 1 { return "Unsupported spatial review version." }
        let chains = binderChains.split { $0 == "," || $0 == ";" || $0.isWhitespace }.map(String.init)
        let target = targetChain.trimmingCharacters(in: .whitespacesAndNewlines)
        if chains.isEmpty || target.isEmpty { return "Choose distinct protein and target/ligand chains from the exact pose." }
        if chains.contains(target) && (mode == .protein || ligandResidue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) {
            return "Protein targets need a distinct chain. A ligand in the protein chain needs its exact nonpolymer residue ID."
        }
        if let value = number(cutoff), value > 0 && value <= 100 {} else { return "Enter a distance greater than0 and at most100 Å." }
        if mode == .protein && residues.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return "Enter explicit target residue IDs, including insertion codes when present." }
        for text in [minimumBurial, maximumBurial] where !text.isEmpty {
            guard let value = number(text), (0...100).contains(value) else { return "Burial thresholds must be between0 and100 percent." }
        }
        if let low = number(minimumBurial), let high = number(maximumBurial), low > high { return "Minimum burial exceeds maximum burial." }
        if mode == .protein && (requireGeometry || !minimumBurial.isEmpty || !maximumBurial.isEmpty) { return "Geometry and ligand burial require ligand mode." }
        return nil
    }
}

struct ResultSpatialRow: Codable, Equatable {
    struct SASA: Codable, Equatable { let buried_percent: Double; let isolated_sasa_a2: Double; let complex_sasa_a2: Double }
    struct Geometry: Codable, Equatable { let passed: Bool; let receipt: String; let sha256: String }
    let id: String
    let source_item_id: String
    let source: String
    let source_stamp: String
    let policy_sha256: String
    let source_sha256: String?
    let passed: Bool
    let error: String?
    let geometry_warning: String?
    let minimum_distance: Double?
    let maximum_distance: Double?
    let distances: [String: Double]?
    let sasa: SASA?
    let recorded_geometry: Geometry?
    let receipt: String?
    var scores: [StudioResultMetric.Kind: Double] {
        var result: [StudioResultMetric.Kind: Double] = [:]
        if let minimum_distance { result[.spatialMinimumDistance] = minimum_distance }
        if let maximum_distance { result[.spatialMaximumDistance] = maximum_distance }
        if let sasa {
            result[.ligandBuriedPercent] = sasa.buried_percent
            result[.ligandFreeSASA] = sasa.isolated_sasa_a2
            result[.ligandBoundSASA] = sasa.complex_sasa_a2
        }
        if let recorded_geometry { result[.recordedGeometryPass] = recorded_geometry.passed ? 1 : 0 }
        return result.filter { $0.value.isFinite }
    }
}
