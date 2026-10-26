import Foundation

enum RFD4Task: String, Codable, CaseIterable, Identifiable {
    case monomer, protein, ligand, nanobody, motif, partial, inverse, annotated
    var id: String { rawValue }
    var label: String {
        switch self {
        case .monomer: return "New monomer"
        case .protein: return "Protein binder"
        case .ligand: return "Small-molecule binder"
        case .nanobody: return "Nanobody with fixed framework"
        case .motif: return "Motif scaffolding"
        case .partial: return "Partial diffusion"
        case .inverse: return "Inverse folding"
        case .annotated: return "Native annotated input"
        }
    }
}

enum DesignSearchPolicy: String, Codable, CaseIterable, Identifiable {
    case native, fixed, iterative, greedy, beam
    var id: String { rawValue }
    var label: String {
        switch self {
        case .native: return "Generated sequence"
        case .fixed: return "Fixed backbone"
        case .iterative: return "Iterative"
        case .greedy: return "Greedy search"
        case .beam: return "Beam search"
        }
    }
}

struct RFD4Condition: Codable, Hashable, Identifiable {
    var condition = "C_HOT"
    var value = "true"
    var selection = ""
    var id: String { condition + selection }
    static let names = ["C_CRD", "C_SEQ", "C_IDX", "C_CRDGRP", "C_CENTROID", "C_HOT", "C_RAS", "C_SEC", "C_HB", "C_PISTACK", "C_PICATION", "C_SALT", "C_HPHOB", "C_MCOORD", "C_CATH"]
    private enum CodingKeys: String, CodingKey { case condition, value, selection }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(condition, forKey: .condition); try c.encode(selection, forKey: .selection)
        if value == "true" || value == "false" { try c.encode(value == "true", forKey: .value) }
        else if let number = Double(value), number.isFinite { try c.encode(number, forKey: .value) }
        else { try c.encode(value, forKey: .value) }
    }
    init() {}
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        condition = try c.decode(String.self, forKey: .condition)
        selection = try c.decode(String.self, forKey: .selection)
        if let v = try? c.decode(Bool.self, forKey: .value) { value = v ? "true" : "false" }
        else if let v = try? c.decode(Double.self, forKey: .value) { value = String(v) }
        else { value = try c.decode(String.self, forKey: .value) }
    }
}

struct RFD4Request: Codable, Hashable {
    var schema = 1
    var task: RFD4Task = .monomer
    var source = ""
    var length = 120
    var count = 1
    var seed = 42
    var target_chain = "B"
    var source_target_chain = ""
    var binder_chain = "A"
    var hotspots: [Int] = []
    var hotspot_residues: [String]?
    var contig = ""
    var conditions: [RFD4Condition] = []
    var partial_fraction = 0.5
    var search: DesignSearchPolicy = .native
    var cycles = 5
    var proposals = 4
    var beam_width = 4
    var sequence_model = "solublempnn"
    var predictor = "esmfold2-full-mlx"
    var target_msa = ""
    var scaffold_msa = ""
    var cdr_ranges = ""
    var omit_amino_acids = "C"
    var temperature = 0.1
    var optimized_kernels = false
    var annotated_input = false
    var assess_native = false
    var starting_structures: [String] = []
    var native_search = false
    var native_beam_width = 2
    var native_branches = 2
    var native_checkpoints = [8, 15]
    var native_partial_fraction = 0.5
    var ligand_smiles = ""
    var time_budget_minutes: Double?
    var scaffold_id: String?
    var canSearch: Bool { task == .protein || task == .nanobody || task == .ligand }
    var needsPrediction: Bool { search != .native || assess_native || native_search }
    var predictions: Int {
        guard (1...10000).contains(count), (1...100).contains(cycles), (1...64).contains(proposals), (1...64).contains(beam_width) else { return 0 }
        if native_search {
            guard (1...16).contains(native_beam_width), (1...16).contains(native_branches), native_checkpoints.count <= 60 else { return 0 }
            guard native_partial_fraction.isFinite, (0...1).contains(native_partial_fraction) else { return 0 }
            let terminal = (native_checkpoints.last ?? 0) < Int((60 * native_partial_fraction).rounded(.toNearestOrEven)) ? 1 : 0
            return count * native_beam_width * (native_branches * native_checkpoints.count + terminal)
        }
        switch search {
        case .native: return assess_native ? count : 0
        case .fixed: return count * proposals
        case .iterative: return count * cycles
        case .greedy: return count * proposals * cycles
        case .beam: return count * proposals * (1 + beam_width * (cycles - 1))
        }
    }
    var validationIssues: [String] {
        var issues: [String] = []
        if task != .monomer && source.isEmpty && starting_structures.isEmpty && !(task == .ligand && !ligand_smiles.isEmpty) { issues.append("Choose a source structure.") }
        if let minutes = time_budget_minutes, !minutes.isFinite || minutes <= 0 || minutes > 10080 { issues.append("Choose a design time between zero and seven days.") }
        if scaffold_msa == "auto" && scaffold_id == nil { issues.append("Choose an explicit alignment for a custom framework.") }
        if scaffold_id != nil && (binder_chain != "A" || target_chain != "B") { issues.append("Automatic framework assembly uses binder A and target B.") }
        if !(1...2000).contains(length) || !(1...10000).contains(count) || seed < 0 || seed > 4_294_967_295 - max(0, count - 1) { issues.append("Check the length, family count and seed.") }
        if !(1...100).contains(cycles) || !(1...64).contains(proposals) || !(1...64).contains(beam_width) { issues.append("Check the cycle, proposal and beam counts.") }
        if !partial_fraction.isFinite || partial_fraction <= 0 || partial_fraction > 1 || !temperature.isFinite || temperature <= 0 || temperature > 2 { issues.append("Check the partial trajectory fraction and sequence temperature.") }
        if task == .protein && !contig.isEmpty { issues.append("Clear the retained segments for protein de novo design; Studio derives them.") }
        if binder_chain.isEmpty || target_chain.isEmpty || binder_chain == target_chain { issues.append("Choose distinct binder and target chains.") }
        if Set(hotspots).count != hotspots.count || hotspots.contains(where: { $0 < 1 }) { issues.append("Use unique positive hotspot residue numbers.") }
        if (task == .nanobody || task == .motif) && !annotated_input && contig.isEmpty && starting_structures.isEmpty && scaffold_id == nil { issues.append("Choose an annotated CIF, or define the retained residues and generated segments.") }
        if !starting_structures.isEmpty && starting_structures.count != count { issues.append("Use one imported structure per family.") }
        if !starting_structures.isEmpty && !needsPrediction { issues.append("Choose a search or assessment for imported structures.") }
        if needsPrediction {
            if task == .ligand && (predictor != "boltz" || ligand_smiles.isEmpty) { issues.append("Small-molecule assessment requires Boltz and the exact molecule SMILES.") }
            if task == .ligand && search != .native && sequence_model != "lasermpnn" { issues.append("Use LASErMPNN for this small-molecule search.") }
            if task == .ligand && search != .native && omit_amino_acids != "C" { issues.append("The ligand sampler uses its qualified cysteine exclusion.") }
            if !canSearch && !(native_search && task == .ligand) { issues.append("This sequence search needs a protein target or nanobody.") }
            if task != .ligand && predictor != "esmfold2-fast-mlx" && target_msa.isEmpty { issues.append("Choose the target alignment or single-sequence prediction.") }
            if task == .nanobody && (cdr_ranges.isEmpty || (predictor != "esmfold2-fast-mlx" && scaffold_msa.isEmpty)) { issues.append("Set CDR ranges and the scaffold alignment policy.") }
            if search == .beam && beam_width > proposals { issues.append("The first generation needs at least one proposal per beam place.") }
        }
        if native_search {
            if !(1...16).contains(native_beam_width) || !(1...16).contains(native_branches) || !native_partial_fraction.isFinite || native_partial_fraction <= 0 || native_partial_fraction >= 1 { issues.append("Check the native search width, branches and partial trajectory fraction.") }
            if search != .native || assess_native { issues.append("Native rollout search uses generated sequences and assesses every rollout.") }
            if task == .ligand && ligand_smiles.isEmpty { issues.append("Enter the exact ligand SMILES for the Boltz oracle.") }
            if native_partial_fraction.isFinite && (0...1).contains(native_partial_fraction) && (native_checkpoints.isEmpty || native_checkpoints != Array(Set(native_checkpoints)).sorted()
                || native_checkpoints.contains(where: { $0 < 1 || $0 > Int((60 * native_partial_fraction).rounded(.toNearestOrEven)) })) {
                issues.append("Native checkpoints must increase within the partial trajectory.")
            }
        }
        if conditions.contains(where: { $0.selection.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) { issues.append("Complete every condition's atom selection.") }
        return issues
    }
}
