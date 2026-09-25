import Foundation

/// Ligand NISE has a separate, versioned request; historical iterative IDs stay stable.
struct NISERequest: Codable, Hashable {
    var search_policy_version = 3
    var scoring_mode = "boltz"
    var nesso_early_score_gate = 0.4
    var psichic_early_score_gate = 0.2
    var early_score_gate = 0.80
    var selective_affinity = true
    var adaptive_proposals = false
    var initial_proposals = 16
    var affinity_batch_size = 8
    var min_improvement = 0.01
    var smiles = ""
    var num_starts = 1000
    var backbone_method = "protein-hunter"
    var rfd3_num_bins = 5
    var trajectories = 8
    var nise_seqs = 32
    var first_cycle_seqs = 64
    var partial_noising = false
    var noise_radius = 6.0
    var noise_percent = 25.0
    var noise_predictions = 32
    var noise_mpnn_seqs = 32
    var noise_advance = 1
    var max_cycles = 30
    var patience = 4
    var binder_min_len = 65
    var binder_max_len = 150
    var seed = 0
    var preorganisation = false
    var top_x = 8
    var scheduler = "cycle-wave"
    var phase0_refine_cycles = 2
    var phase0_seqs1 = 3
    var phase0_seqs2 = 5
    var beam = 3
    var screening_engine = "nesso"
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
    var exposure_mode = "sasa"
    var geometry_workers = 0
    var ligand_atom_signature = ""
    var ligand_atoms_generated_for = ""

    init() {}

    // New controls must not discard existing saved NISE requests.
    enum CodingKeys: String, CodingKey {
        case scoring_mode, nesso_early_score_gate, psichic_early_score_gate
        case search_policy_version, early_score_gate, selective_affinity, adaptive_proposals, initial_proposals, affinity_batch_size, min_improvement
        case first_cycle_seqs, partial_noising, noise_radius, noise_percent, noise_predictions, noise_mpnn_seqs, noise_advance
        case smiles, num_starts, trajectories, nise_seqs, max_cycles, patience
        case binder_min_len, binder_max_len, seed, preorganisation, top_x, scheduler
        case screening_engine, phase0_refine_cycles, phase0_seqs1, phase0_seqs2, beam, nesso_screen, nesso_top_k
        case phase0_nesso_screen, phase0_nesso_refine_top_k, phase0_nesso_expand_top_k, phase0_gate_seqs, phase0_sc_ca, nise_sc_ca, nise_sc_lig, nise_ligand_sc_from_cycle
        case backbone_method, rfd3_num_bins
        case hotspot_atoms, exposed_atoms, hotspot_distance, exposure_min_fraction, exposure_mode, geometry_workers
        case ligand_atom_signature, ligand_atoms_generated_for
    }

    init(from decoder: Decoder) throws {
        self.init()
        let c = try decoder.container(keyedBy: CodingKeys.self)
        search_policy_version = try c.decodeIfPresent(Int.self, forKey: .search_policy_version) ?? 1
        if search_policy_version == 1 {
            num_starts = 100; max_cycles = 30; patience = 5; trajectories = 6; beam = 1
            early_score_gate = 0; selective_affinity = false; min_improvement = 0.0001
        }
        scoring_mode = try c.decodeIfPresent(String.self, forKey: .scoring_mode) ?? "boltz"
        nesso_early_score_gate = try c.decodeIfPresent(Double.self, forKey: .nesso_early_score_gate) ?? (scoring_mode == "screening" ? 0 : nesso_early_score_gate)
        psichic_early_score_gate = try c.decodeIfPresent(Double.self, forKey: .psichic_early_score_gate) ?? (scoring_mode == "screening" ? 0 : psichic_early_score_gate)
        early_score_gate = try c.decodeIfPresent(Double.self, forKey: .early_score_gate) ?? early_score_gate
        selective_affinity = try c.decodeIfPresent(Bool.self, forKey: .selective_affinity) ?? selective_affinity
        adaptive_proposals = try c.decodeIfPresent(Bool.self, forKey: .adaptive_proposals) ?? adaptive_proposals
        initial_proposals = try c.decodeIfPresent(Int.self, forKey: .initial_proposals) ?? initial_proposals
        affinity_batch_size = try c.decodeIfPresent(Int.self, forKey: .affinity_batch_size) ?? affinity_batch_size
        min_improvement = try c.decodeIfPresent(Double.self, forKey: .min_improvement) ?? min_improvement
        exposure_mode = try c.decodeIfPresent(String.self, forKey: .exposure_mode) ?? "sasa"
        geometry_workers = try c.decodeIfPresent(Int.self, forKey: .geometry_workers) ?? 0
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
        nise_seqs = try c.decodeIfPresent(Int.self, forKey: .nise_seqs) ?? (search_policy_version < 3 ? 64 : nise_seqs)
        first_cycle_seqs = try c.decodeIfPresent(Int.self, forKey: .first_cycle_seqs) ?? (search_policy_version < 3 ? nise_seqs : first_cycle_seqs)
        partial_noising = try c.decodeIfPresent(Bool.self, forKey: .partial_noising) ?? false
        noise_radius = try c.decodeIfPresent(Double.self, forKey: .noise_radius) ?? noise_radius
        noise_percent = try c.decodeIfPresent(Double.self, forKey: .noise_percent) ?? noise_percent
        noise_predictions = try c.decodeIfPresent(Int.self, forKey: .noise_predictions) ?? noise_predictions
        noise_mpnn_seqs = try c.decodeIfPresent(Int.self, forKey: .noise_mpnn_seqs) ?? noise_mpnn_seqs
        noise_advance = try c.decodeIfPresent(Int.self, forKey: .noise_advance) ?? noise_advance
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
        screening_engine = try c.decodeIfPresent(String.self, forKey: .screening_engine) ?? "nesso"
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

    var screeningLabel: String { screening_engine == "psichic" ? "PSICHIC" : "NESSO" }
    var usesScreeningObjective: Bool { scoring_mode == "screening" }
    var objectiveLabel: String { usesScreeningObjective ? screeningLabel : "Boltz" }
    var objectiveFormula: String {
        usesScreeningObjective ? (screening_engine == "psichic" ? "1 − predicted_nonbinder" : "P(bind) + (1 − entropy_crop_pl)") : "ligand pLDDT/100 + P(bind)"
    }
    var objectiveEarlyGate: Double {
        get { usesScreeningObjective ? (screening_engine == "psichic" ? psichic_early_score_gate : nesso_early_score_gate) : early_score_gate }
        set {
            if !usesScreeningObjective { early_score_gate = newValue }
            else if screening_engine == "psichic" { psichic_early_score_gate = newValue }
            else { nesso_early_score_gate = newValue }
        }
    }
    mutating func enableScreeningObjective() {
        scoring_mode = "screening"; search_policy_version = 3
        nesso_screen = true; phase0_nesso_screen = true; selective_affinity = true
        partial_noising = false
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
    func proposalRounds(_ cap: Int) -> Int {
        guard adaptive_proposals else { return 1 }
        var count = 1, level = max(1, initial_proposals)
        while level < cap { level = min(cap, level * 2); count += 1 }
        return count
    }
    var proposalRoundCount: Int { proposalRounds(nise_seqs) }
    var noisingPredictionBudget: Int { partial_noising ? trajectories * (noise_predictions + (nesso_screen ? min(nesso_top_k, noise_mpnn_seqs) : noise_mpnn_seqs)) : 0 }
    var normalParentCount: Int { max(0, beam - (partial_noising ? noise_advance : 0)) }
    var cyclePredictionBudget: Int { trajectories * (nesso_screen ? min(nesso_top_k * proposalRoundCount, normalParentCount * nise_seqs) : normalParentCount * nise_seqs) + noisingPredictionBudget }
    var firstCyclePredictionBudget: Int { trajectories * (nesso_screen ? min(nesso_top_k * proposalRounds(first_cycle_seqs), first_cycle_seqs) : first_cycle_seqs) }
    var optimizationPredictionBudget: Int { firstCyclePredictionBudget + max(0, max_cycles - 1) * cyclePredictionBudget }


    var validationIssues: [String] {
        var issues: [String] = []
        if !["boltz", "screening"].contains(scoring_mode)
            || !nesso_early_score_gate.isFinite || !(0...2).contains(nesso_early_score_gate)
            || !psichic_early_score_gate.isFinite || !(0...1).contains(psichic_early_score_gate) {
            issues.append("Choose a valid objective and separate NESSO (0–2) / PSICHIC (0–1) early gates; 0 disables a gate.")
        }
        if usesScreeningObjective && (search_policy_version < 3 || !nesso_screen || !phase0_nesso_screen || !selective_affinity || partial_noising) {
            issues.append("Screening-objective mode requires both stage screens, geometry-first prediction and no partial noising.")
        }

        if !["sasa", "biotin-carboxamide-v1"].contains(exposure_mode) || !(0...64).contains(geometry_workers) {
            issues.append("Choose a supported exposure policy and 0–64 geometry workers (0 means automatic).")
        }
        if exposure_mode == "biotin-carboxamide-v1" && !selective_affinity {
            issues.append("Biotin exit filtering requires geometry-before-affinity scoring.")
        }
        if !(1...3).contains(search_policy_version) || !early_score_gate.isFinite || !(0...2).contains(early_score_gate)
            || !min_improvement.isFinite || !(0...1).contains(min_improvement)
            || !(1...128).contains(affinity_batch_size) || !(1...4096).contains(initial_proposals) {
            issues.append("Use an early score gate of 0–2, improvement of 0–1 and valid sampling/affinity batches.")
        }
        if adaptive_proposals && (initial_proposals > min(nise_seqs, first_cycle_seqs) || initial_proposals < beam) {
            issues.append("Adaptive starting proposals must be between the advancement count and the maximum per parent.")
        }
        if !(1...4096).contains(first_cycle_seqs) || first_cycle_seqs < beam {
            issues.append("First-cycle proposals must cover the beam width (up to 4,096).")
        }
        if !noise_radius.isFinite || !(3...15).contains(noise_radius) || !noise_percent.isFinite || !(1...100).contains(noise_percent)
            || !(1...1024).contains(noise_predictions) || !(1...4096).contains(noise_mpnn_seqs) || !(1...63).contains(noise_advance) {
            issues.append("Use a noising radius of 3–15 Å, mask 1–100%, and valid proposal counts.")
        }
        if partial_noising && (adaptive_proposals || noise_advance >= beam || noise_advance > noise_mpnn_seqs
            || (nesso_screen && noise_advance > nesso_top_k)) {
            issues.append("Partial noising requires fixed sampling, at least one normal beam place, and enough repair/NESSO candidates for its reserved places.")
        }
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
        if !["nesso", "psichic"].contains(screening_engine) { issues.append("Choose a supported experimental screening engine.") }
        if usesNesso && screening_engine == "psichic" && binder_max_len > 700 { issues.append("Experimental PSICHIC supports sequences up to 700 residues.") }
        if !(1...4096).contains(nesso_top_k) || (nesso_screen && (nesso_top_k < beam || nesso_top_k > nise_seqs)) {
            issues.append("The NESSO shortlist must be between the number to advance and the number sampled per parent.")
        }
        if !["cycle-wave", "resident"].contains(scheduler) { issues.append("Choose a supported execution policy.") }
        return issues
    }

    mutating func useSmallTrial() {
        adaptive_proposals = false; initial_proposals = 3; partial_noising = false; first_cycle_seqs = 3
        num_starts = 5; trajectories = 2; nise_seqs = 3; max_cycles = 3; patience = 2
        binder_min_len = 65; binder_max_len = 70; top_x = 3
        phase0_refine_cycles = 2; phase0_seqs1 = 3; phase0_seqs2 = 5; phase0_gate_seqs = 3; phase0_nesso_refine_top_k = 1; phase0_nesso_expand_top_k = 5; beam = 1; nesso_top_k = 2
    }
}
