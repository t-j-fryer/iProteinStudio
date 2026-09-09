import Foundation

/// Ligand NISE has a separate, versioned request; historical iterative IDs stay stable.
struct NISERequest: Codable, Hashable {
    var smiles = ""
    var num_starts = 100
    var backbone_method = "protein-hunter"
    var rfd3_num_bins = 5
    var trajectories = 6
    var nise_seqs = 64
    var max_cycles = 30
    var patience = 5
    var binder_min_len = 65
    var binder_max_len = 150
    var seed = 0
    var preorganisation = false
    var top_x = 8
    var scheduler = "cycle-wave"
    var phase0_refine_cycles = 2
    var phase0_seqs1 = 3
    var phase0_seqs2 = 5
    var beam = 1
    var nesso_screen = false
    var nesso_top_k = 16
    var phase0_nesso_screen = false
    var phase0_nesso_refine_top_k = 1
    var phase0_nesso_expand_top_k = 20
    var phase0_gate_seqs = 3
    var phase0_sc_ca = 2.0
    var nise_sc_ca = 2.5
    var nise_sc_lig = 2.5
    var nise_ligand_sc_from_cycle = 3
    var hotspot_atoms: [String] = []
    var exposed_atoms: [String] = []
    var hotspot_distance = 6.0
    var exposure_min_fraction = 0.5
    var ligand_atom_signature = ""
    var ligand_atoms_generated_for = ""

    init() {}

    // New controls must not discard existing saved NISE requests.
    enum CodingKeys: String, CodingKey {
        case smiles, num_starts, trajectories, nise_seqs, max_cycles, patience
        case binder_min_len, binder_max_len, seed, preorganisation, top_x, scheduler
        case phase0_refine_cycles, phase0_seqs1, phase0_seqs2, beam, nesso_screen, nesso_top_k
        case phase0_nesso_screen, phase0_nesso_refine_top_k, phase0_nesso_expand_top_k, phase0_gate_seqs, phase0_sc_ca, nise_sc_ca, nise_sc_lig, nise_ligand_sc_from_cycle
        case backbone_method, rfd3_num_bins
        case hotspot_atoms, exposed_atoms, hotspot_distance, exposure_min_fraction
        case ligand_atom_signature, ligand_atoms_generated_for
    }

    init(from decoder: Decoder) throws {
        self.init()
        let c = try decoder.container(keyedBy: CodingKeys.self)
        hotspot_atoms = try c.decodeIfPresent([String].self, forKey: .hotspot_atoms) ?? hotspot_atoms
        exposed_atoms = try c.decodeIfPresent([String].self, forKey: .exposed_atoms) ?? exposed_atoms
        hotspot_distance = try c.decodeIfPresent(Double.self, forKey: .hotspot_distance) ?? hotspot_distance
        exposure_min_fraction = try c.decodeIfPresent(Double.self, forKey: .exposure_min_fraction) ?? exposure_min_fraction
        ligand_atom_signature = try c.decodeIfPresent(String.self, forKey: .ligand_atom_signature) ?? ligand_atom_signature
        ligand_atoms_generated_for = try c.decodeIfPresent(String.self, forKey: .ligand_atoms_generated_for) ?? ligand_atoms_generated_for
        smiles = try c.decodeIfPresent(String.self, forKey: .smiles) ?? smiles
        num_starts = try c.decodeIfPresent(Int.self, forKey: .num_starts) ?? num_starts
        backbone_method = try c.decodeIfPresent(String.self, forKey: .backbone_method) ?? backbone_method
        rfd3_num_bins = try c.decodeIfPresent(Int.self, forKey: .rfd3_num_bins) ?? rfd3_num_bins
        trajectories = try c.decodeIfPresent(Int.self, forKey: .trajectories) ?? trajectories
        nise_seqs = try c.decodeIfPresent(Int.self, forKey: .nise_seqs) ?? nise_seqs
        max_cycles = try c.decodeIfPresent(Int.self, forKey: .max_cycles) ?? max_cycles
        patience = try c.decodeIfPresent(Int.self, forKey: .patience) ?? patience
        binder_min_len = try c.decodeIfPresent(Int.self, forKey: .binder_min_len) ?? binder_min_len
        binder_max_len = try c.decodeIfPresent(Int.self, forKey: .binder_max_len) ?? binder_max_len
        seed = try c.decodeIfPresent(Int.self, forKey: .seed) ?? seed
        preorganisation = try c.decodeIfPresent(Bool.self, forKey: .preorganisation) ?? preorganisation
        top_x = try c.decodeIfPresent(Int.self, forKey: .top_x) ?? top_x
        scheduler = try c.decodeIfPresent(String.self, forKey: .scheduler) ?? scheduler
        phase0_refine_cycles = try c.decodeIfPresent(Int.self, forKey: .phase0_refine_cycles) ?? phase0_refine_cycles
        phase0_seqs1 = try c.decodeIfPresent(Int.self, forKey: .phase0_seqs1) ?? phase0_seqs1
        phase0_seqs2 = try c.decodeIfPresent(Int.self, forKey: .phase0_seqs2) ?? phase0_seqs2
        beam = try c.decodeIfPresent(Int.self, forKey: .beam) ?? beam
        nesso_screen = try c.decodeIfPresent(Bool.self, forKey: .nesso_screen) ?? nesso_screen
        nesso_top_k = try c.decodeIfPresent(Int.self, forKey: .nesso_top_k) ?? nesso_top_k
        phase0_nesso_screen = try c.decodeIfPresent(Bool.self, forKey: .phase0_nesso_screen) ?? phase0_nesso_screen
        phase0_nesso_refine_top_k = try c.decodeIfPresent(Int.self, forKey: .phase0_nesso_refine_top_k) ?? phase0_nesso_refine_top_k
        phase0_nesso_expand_top_k = try c.decodeIfPresent(Int.self, forKey: .phase0_nesso_expand_top_k) ?? phase0_nesso_expand_top_k
        phase0_gate_seqs = try c.decodeIfPresent(Int.self, forKey: .phase0_gate_seqs) ?? phase0_seqs1
        phase0_sc_ca = try c.decodeIfPresent(Double.self, forKey: .phase0_sc_ca) ?? phase0_sc_ca
        nise_sc_ca = try c.decodeIfPresent(Double.self, forKey: .nise_sc_ca) ?? nise_sc_ca
        nise_sc_lig = try c.decodeIfPresent(Double.self, forKey: .nise_sc_lig) ?? nise_sc_lig
        nise_ligand_sc_from_cycle = try c.decodeIfPresent(Int.self, forKey: .nise_ligand_sc_from_cycle) ?? nise_ligand_sc_from_cycle
    }

    var usesNesso: Bool { nesso_screen || phase0_nesso_screen }

    var hasAtomSelections: Bool { !hotspot_atoms.isEmpty || !exposed_atoms.isEmpty }
    mutating func clearAtomSelections() {
        hotspot_atoms = []; exposed_atoms = []; ligand_atom_signature = ""; ligand_atoms_generated_for = ""
    }

    var initialPredictionBudget: Int {
        let refinement = phase0_nesso_screen ? phase0_nesso_refine_top_k : phase0_seqs1
        let expansion = phase0_nesso_screen ? min(num_starts, phase0_nesso_expand_top_k) : num_starts * phase0_gate_seqs * phase0_seqs2
        return num_starts * ((backbone_method == "rfdiffusion3" ? 0 : 1) + phase0_refine_cycles * refinement + phase0_gate_seqs) + expansion
    }
    var rfd3Lengths: [Int] {
        let count = max(1, min(rfd3_num_bins, num_starts, binder_max_len - binder_min_len + 1))
        if count == 1 { return [(binder_min_len + binder_max_len) / 2] }
        return (0..<count).map { binder_min_len + Int((Double($0 * (binder_max_len - binder_min_len)) / Double(count - 1)).rounded()) }
    }
    var cyclePredictionBudget: Int { trajectories * (nesso_screen ? nesso_top_k : beam * nise_seqs) }
    var firstCyclePredictionBudget: Int { trajectories * (nesso_screen ? nesso_top_k : nise_seqs) }
    var optimizationPredictionBudget: Int { firstCyclePredictionBudget + max(0, max_cycles - 1) * cyclePredictionBudget }


    var validationIssues: [String] {
        var issues: [String] = []
        if !Set(hotspot_atoms).isDisjoint(with: Set(exposed_atoms)) {
            issues.append("An atom cannot be both a binding hotspot and an exposed atom.")
        }
        if hasAtomSelections && (ligand_atoms_generated_for != smiles.trimmingCharacters(in: .whitespacesAndNewlines)
            || ligand_atom_signature.range(of: "^[0-9a-f]{64}$", options: .regularExpression) == nil) {
            issues.append("Reload the molecule and reselect atoms after changing its SMILES.")
        }
        for names in [hotspot_atoms, exposed_atoms] {
            if names.count > 256 || names.count != Set(names).count || names.contains(where: {
                $0.count > 4 || $0.range(of: "^[A-Z]{1,2}[1-9][0-9]{0,2}$", options: .regularExpression) == nil
            }) { issues.append("Choose valid atoms from the molecule diagram or list.") }
        }
        if !hotspot_distance.isFinite || !(3...10).contains(hotspot_distance)
            || !exposure_min_fraction.isFinite || !(0.1...1).contains(exposure_min_fraction) {
            issues.append("Use a contact distance of 3–10 Å and retained accessibility of 10–100%.")
        }
        if !["protein-hunter", "rfdiffusion3"].contains(backbone_method) || !(1...20).contains(rfd3_num_bins) {
            issues.append("Choose a supported backbone generator and 1–20 RFdiffusion3 length groups.")
        }
        let text = smiles.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty || text.count > 4096 || text.contains(where: \.isWhitespace) {
            issues.append("Enter one small-molecule SMILES without whitespace.")
        }
        if !(1...10000).contains(num_starts) || !(1...1000).contains(trajectories) || trajectories > num_starts {
            issues.append("Use 1–10,000 starts and 1–1,000 trajectories, with at least one start per trajectory.")
        }
        if !(60...250).contains(binder_min_len) || !(60...250).contains(binder_max_len) || binder_min_len > binder_max_len {
            issues.append("Binder lengths must be 60–250 residues, with minimum no greater than maximum.")
        }
        if !(1...4096).contains(nise_seqs) || !(1...1000).contains(max_cycles) || !(1...1000).contains(patience)
            || !(1...64).contains(top_x) || !(0...2147483647).contains(seed) {
            issues.append("The search budget or seed is outside its supported range.")
        }
        if !(0...20).contains(phase0_refine_cycles) || !(1...1024).contains(phase0_seqs1) || !(1...1024).contains(phase0_seqs2) {
            issues.append("Use 0–20 initial refinement rounds and 1–1,024 sequences for each initial sampling step.")
        }
        if !(1...1024).contains(phase0_gate_seqs) || !(1...1024).contains(phase0_nesso_refine_top_k)
            || !(1...10000).contains(phase0_nesso_expand_top_k) {
            issues.append("Initial gate sampling and NESSO shortlist sizes are outside their supported ranges.")
        }
        if phase0_nesso_screen && phase0_nesso_refine_top_k > phase0_seqs1 {
            issues.append("The initial NESSO refinement shortlist cannot exceed sequences sampled per lineage.")
        }
        if phase0_nesso_screen && phase0_nesso_expand_top_k < trajectories {
            issues.append("The initial NESSO expansion shortlist must allow at least the requested number of trajectories.")
        }
        if [phase0_sc_ca, nise_sc_ca, nise_sc_lig].contains(where: { !$0.isFinite || !(0.1...10).contains($0) })
            || !(1...1001).contains(nise_ligand_sc_from_cycle) {
            issues.append("Use structural RMSD limits of 0.1–10 Å and a ligand-check start cycle of 1–1,001.")
        }
        if !(1...64).contains(beam) || beam > nise_seqs {
            issues.append("Advance 1–64 sequences per trajectory, no more than you sample per parent.")
        }
        if !(1...4096).contains(nesso_top_k) || (nesso_screen && (nesso_top_k < beam || nesso_top_k > nise_seqs)) {
            issues.append("The NESSO shortlist must be between the number to advance and the number sampled per parent.")
        }
        if !["cycle-wave", "resident"].contains(scheduler) { issues.append("Choose a supported execution policy.") }
        return issues
    }

    mutating func useSmallTrial() {
        num_starts = 5; trajectories = 2; nise_seqs = 3; max_cycles = 3; patience = 2
        binder_min_len = 65; binder_max_len = 70; top_x = 3
        phase0_refine_cycles = 2; phase0_seqs1 = 3; phase0_seqs2 = 5; phase0_gate_seqs = 3; phase0_nesso_refine_top_k = 1; phase0_nesso_expand_top_k = 5; beam = 1; nesso_top_k = 2
    }
}
