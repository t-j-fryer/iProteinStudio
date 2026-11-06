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

struct RFD4Conformer: Codable, Hashable {
    var label: String
    var path: String
    var weight: Double
}

struct RFD4MotifResidue: Codable, Hashable, Identifiable {
    var chain: String
    var residue: Int
    var atoms: [String]
    var id: String { chain + ":" + String(residue) }
}

struct RFD4Motif: Codable, Hashable {
    var source_sha256: String?
    var partner_chains: [String]?
    var ligand_ids: [String]?
    var residues: [RFD4MotifResidue] = []
    var coordinate_mode = "absolute"
    var fix_sequence = true
    var unindexed = false
    var group_segments = true
    var prefix = [20, 20]
    var linker = [10, 10]
    var suffix = [20, 20]
    var issues: [String] {
        var result: [String] = []
        if !["absolute", "relative"].contains(coordinate_mode) { result.append("Choose fixed coordinates or relative geometry.") }
        if Set(residues.map(\.id)).count != residues.count { result.append("Choose each motif residue once.") }
        if residues.contains(where: { $0.residue < 1 || $0.residue > Int(Int32.max) }) { return ["Use positive native residue numbers."] }
        if residues.isEmpty || residues.contains(where: { $0.atoms.isEmpty }) { result.append("Choose motif residues and at least one coordinate atom in each.") }
        if Set(residues.map(\.chain)).count > 1 { result.append("The guided motif uses one source protein chain. Use native annotated input for multi-chain motifs.") }
        if !Set(partner_chains ?? []).isDisjoint(with: Set(residues.map(\.chain))) { result.append("A retained partner cannot also be the motif-bearing chain.") }
        if [prefix, linker, suffix].allSatisfy({ $0.count == 2 && $0.allSatisfy { (0...2000).contains($0) } }) {
            let sorted = residues.sorted { $0.residue < $1.residue }
            let gaps = zip(sorted, sorted.dropFirst()).filter { pair in pair.1.residue != pair.0.residue + 1 }.count
            if prefix[1] + suffix[1] + linker[1] * gaps + (unindexed ? 0 : residues.count) > 2000 { result.append("The maximum scaffold length exceeds 2000 residues.") }
            if unindexed && prefix[0] + suffix[0] + linker[0] * gaps < residues.count { result.append("Free placement needs at least one generated scaffold position per motif residue.") }
        }
        if !fix_sequence && residues.contains(where: { !Set($0.atoms).isSubset(of: ["N", "CA", "C", "O"]) }) { result.append("Sidechain coordinates reveal sequence. Keep residue identities fixed or select backbone atoms only.") }
        for bounds in [prefix, linker, suffix] {
            if bounds.count != 2 || bounds[0] < 0 || bounds[0] > bounds[1] || bounds[1] > 2000 || (bounds[0] == 0 && bounds[1] != 0) { result.append("Use 0–0 to omit a segment, or positive ordered length bounds up to 2000.") }
        }
        return result
    }
}

struct RFD4MotifAssessment: Codable, Hashable {
    var apo = true
    var holo = false
    var rmsd_max: Double? = 2.0
    var placement_rmsd_max: Double?
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
    var optimized_kernels = true
    var annotated_input = false
    var assess_native = false
    var starting_structures: [String] = []
    var native_search = false
    var native_beam_width = 2
    var native_branches = 2
    var native_checkpoints = [8, 15]
    var native_partial_fraction = 0.5
    var ligand_smiles = ""
    var ligand_geometry: LigandGeometryFilter?
    var time_budget_minutes: Double?
    var scaffold_id: String?
    var length_plan: RFD4LengthPlan?
    var hit_filters: [String: Double]?
    var motif: RFD4Motif?
    var motif_assessment: RFD4MotifAssessment?
    var ligand_conformers: [RFD4Conformer]?
    var ligand_conformer: String?
    var ligand_atom_conditions: [String: [String]]?
    var ligand_attachment_atom: Int?
    var ligand_attachment_linker_atom: Int?
    var ligand_search_pdb: Bool?
    var ligand_is_conjugated: Bool?
    var selection_metric: String?
    var scaffold_weights: [String: Int]?
    var selectionMetrics: [String] { task == .ligand ? (predictor == "boltz" ? ["pbind_ligand_plddt", "pbind", "ligand_plddt", "iptm", "complex_plddt"] : ["ligand_plddt", "iptm", "complex_plddt"]) : ["ipsae_min", "iptm", "ptm", "complex_plddt"] }
    var selectedMetric: String { selection_metric ?? (task == .ligand ? "pbind_ligand_plddt" : "ipsae_min") }
    static func metricLabel(_ metric: String) -> String {
        switch metric {
        case "ipsae_min": return "Minimum directional ipSAE"
        case "iptm": return "Interface confidence (iPTM)"
        case "ptm": return "Global confidence (pTM)"
        case "complex_plddt": return "Mean complex pLDDT (0–1)"
        case "pbind": return "Boltz binding probability P(bind)"
        case "ligand_plddt": return "Ligand pLDDT (0–100)"
        default: return "P(bind) + ligand pLDDT/100"
        }
    }
    var frameworkCounts: [String: Int] {
        guard let weights = scaffold_weights, !weights.isEmpty,
              (1...10000).contains(count), weights.values.allSatisfy({ (1...10000).contains($0) }) else { return [:] }
        let keys = weights.keys.sorted(), total = weights.values.reduce(0, +)
        var credit = weights.mapValues { _ in 0 }, counts = credit
        for _ in 0..<count {
            for key in keys { credit[key, default: 0] += weights[key] ?? 0 }
            var selected = keys[0]
            for key in keys.dropFirst() where credit[key, default: 0] > credit[selected, default: 0] { selected = key }
            credit[selected, default: 0] -= total; counts[selected, default: 0] += 1
        }
        return counts
    }
    var canSearch: Bool { task == .protein || task == .nanobody || task == .ligand }
    var needsPrediction: Bool { search != .native || assess_native || native_search || motif_assessment != nil }
    var predictions: Int {
        guard (1...10000).contains(count), (1...100).contains(cycles), (1...64).contains(proposals), (1...64).contains(beam_width) else { return 0 }
        if let assessment = motif_assessment { return count * ((assessment.apo ? 1 : 0) + (assessment.holo ? 1 : 0)) }
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
        if let assessment = motif_assessment {
            if task != .motif || motif == nil || search != .native || assess_native || native_search { issues.append("Final motif prediction requires a guided motif and native generation.") }
            if !assessment.apo && !assessment.holo { issues.append("Select apo, holo, or both predictions.") }
            if assessment.holo && (motif?.partner_chains ?? []).isEmpty && (motif?.ligand_ids ?? []).isEmpty { issues.append("Select retained partners for holo prediction in the motif editor.") }
            if assessment.placement_rmsd_max != nil && !assessment.holo { issues.append("Partner-aligned RMSD needs holo prediction.") }
            for cutoff in [assessment.rmsd_max, assessment.placement_rmsd_max].compactMap({ $0 }) {
                if !cutoff.isFinite || cutoff <= 0 || cutoff > 100 { issues.append("Use a positive RMSD cutoff up to 100 Å.") }
            }
            if (motif?.residues.reduce(0) { $0 + $1.atoms.count } ?? 0) < 3 { issues.append("RMSD assessment needs at least three noncollinear motif atoms.") }
            if assessment.holo && !(motif?.ligand_ids ?? []).isEmpty && !["boltz", "esmfold2-full-mlx", "esmfold2-fast-mlx", "esmfold2-600-mlx"].contains(predictor) { issues.append("Ligand holo prediction requires Boltz or ESMFold2.") }
            if assessment.holo && !(motif?.partner_chains ?? []).isEmpty && !["esmfold2-fast-mlx", "esmfold2-600-mlx"].contains(predictor) && target_msa.isEmpty { issues.append("Choose a retained partner alignment policy.") }
            if time_budget_minutes != nil { issues.append("Complete motif assessments do not support an active-time cap.") }
        }
        if let motif {
            issues += motif.issues
            if task != .motif || annotated_input || !contig.isEmpty || !starting_structures.isEmpty { issues.append("Guided motifs require an ordinary source structure without a manual contig.") }
            if conditions.contains(where: { ["C_CRD", "C_CRDGRP", "C_SEQ", "C_IDX"].contains($0.condition) }) { issues.append("Set motif geometry, identity and indexing in the motif controls.") }
            if !hotspots.isEmpty || !(hotspot_residues ?? []).isEmpty { issues.append("Use native motif conditions instead of protein-binder hotspots.") }
        }
        if !selectionMetrics.contains(selectedMetric) { issues.append("Choose a selection metric supported by this task.") }
        if let weights = scaffold_weights {
            if task != .nanobody || annotated_input || native_search || !starting_structures.isEmpty { issues.append("Framework allocation requires newly generated nanobodies without native rollout search.") }
            if weights.isEmpty || weights.values.contains(where: { !(1...10000).contains($0) }) || count < weights.count { issues.append("Select frameworks, positive weights and at least one family per framework.") }
            if frameworkCounts.values.contains(0) { issues.append("Increase the family count or rebalance weights so every selected framework receives a start.") }
            if !["auto", "empty", ""].contains(scaffold_msa) { issues.append("Use automatic per-framework alignments or single-sequence prediction for multiple frameworks.") }
        }
        if let conformers = ligand_conformers, !conformers.isEmpty {
            if task != .ligand || !source.isEmpty || !starting_structures.isEmpty || annotated_input || native_search { issues.append("Conformer allocation requires newly generated SMILES-based ligand binders without native rollout search.") }
            if count < conformers.count { issues.append("Request at least one starting family per selected ligand shape.") }
        }
        if native_search && task == .ligand && predictor != "boltz" { issues.append("Native ligand rollout search requires Boltz.") }
        if let plan = length_plan {
            if ![.monomer, .protein, .ligand].contains(task) || !starting_structures.isEmpty || annotated_input || native_search { issues.append("Length allocation applies to newly generated monomers or binders.") }
            issues += plan.issues(count: count)
        }
        for (metric, cutoff) in hit_filters ?? [:] {
            if !["ipsae_min", "iptm", "complex_plddt"].contains(metric) || !cutoff.isFinite || !(0...1).contains(cutoff) { issues.append("Hit cutoffs must be between 0 and 1.") }
        }
        if !(hit_filters ?? [:]).isEmpty && (!needsPrediction || task == .ligand) { issues.append("Protein hit filters require a protein or nanobody assessment.") }
        if let ligand_geometry {
            issues += ligand_geometry.validationIssues
            if let motif_assessment, !motif_assessment.holo { issues.append("Enable holo assessment to use the ligand geometry hit filter.") }
        }
        if task != .monomer && source.isEmpty && starting_structures.isEmpty && !(task == .ligand && !ligand_smiles.isEmpty) { issues.append("Choose a target structure or predict one from its sequence.") }
        if let minutes = time_budget_minutes, !minutes.isFinite || minutes <= 0 || minutes > 10080 { issues.append("Choose a design time between zero and seven days.") }
        if scaffold_msa == "auto" && scaffold_id == nil { issues.append("Choose an explicit alignment for a custom framework.") }
        if scaffold_id != nil && (binder_chain != "A" || target_chain != "B") { issues.append("Automatic framework assembly uses binder A and target B.") }
        if !(1...2000).contains(length) || !(1...10000).contains(count) || seed < 0 || seed > 4_294_967_295 - max(0, count - 1) { issues.append("Check the length, family count and seed.") }
        if !(1...100).contains(cycles) || !(1...64).contains(proposals) || !(1...64).contains(beam_width) { issues.append("Check the cycle, proposal and beam counts.") }
        if !partial_fraction.isFinite || partial_fraction <= 0 || partial_fraction > 1 || !temperature.isFinite || temperature <= 0 || temperature > 2 { issues.append("Check the partial trajectory fraction and sequence temperature.") }
        if task == .protein && !contig.isEmpty { issues.append("Clear the retained segments for protein de novo design; Studio derives them.") }
        if binder_chain.isEmpty || target_chain.isEmpty || binder_chain == target_chain { issues.append("Choose distinct binder and target chains.") }
        if Set(hotspots).count != hotspots.count || hotspots.contains(where: { $0 < 1 }) { issues.append("Use unique positive hotspot residue numbers.") }
        if (task == .nanobody || task == .motif) && !annotated_input && contig.isEmpty && starting_structures.isEmpty && scaffold_id == nil && motif == nil { issues.append(task == .motif ? "Choose motif residues and atoms, or use an already annotated RFD4 CIF." : "Choose an annotated CIF, or define the retained residues and generated segments.") }
        if !starting_structures.isEmpty && starting_structures.count != count { issues.append("Use one imported structure per family.") }
        if !starting_structures.isEmpty && !needsPrediction { issues.append("Choose a search or assessment for imported structures.") }
        if needsPrediction && motif_assessment == nil {
            if task == .ligand && (!["boltz", "esmfold2-full-mlx", "esmfold2-fast-mlx", "esmfold2-600-mlx"].contains(predictor) || ligand_smiles.isEmpty) { issues.append("Choose a compatible ligand predictor and the exact molecule SMILES.") }
            if task == .ligand && search != .native && sequence_model != "lasermpnn" { issues.append("Use LASErMPNN for this small-molecule search.") }
            if task == .ligand && search != .native && omit_amino_acids != "C" { issues.append("The ligand sampler uses its qualified cysteine exclusion.") }
            if !canSearch && !(native_search && task == .ligand) { issues.append("This sequence search needs a protein target or nanobody.") }
            if task != .ligand && !["esmfold2-fast-mlx", "esmfold2-600-mlx"].contains(predictor) && target_msa.isEmpty { issues.append("Choose the target alignment or single-sequence prediction.") }
            if task == .nanobody && (cdr_ranges.isEmpty || (!["esmfold2-fast-mlx", "esmfold2-600-mlx"].contains(predictor) && scaffold_msa.isEmpty)) { issues.append("Set CDR ranges and the scaffold alignment policy.") }
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
