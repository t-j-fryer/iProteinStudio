import Foundation

// Project's other requests are irrelevant to this saved-workspace migration.
struct DesignRequest: Codable, Hashable { var targetSequence = ""; var targetSmiles = "" }
struct RFD3Request: Codable, Hashable { var targetSequence = ""; var targetStructurePath = ""; var smiles = "" }
struct PredictionRequest: Codable, Hashable { var pastedSequences = ""; var sequenceFile = ""; var jobs: [String] = [] }

@main
struct NISERequestContractHarness {
    static func main() throws {
        let old = Data(#"{"name":"Existing project","slug":"existing","preferredMode":"iterative"}"#.utf8)
        let project = try JSONDecoder().decode(Project.self, from: old)
        precondition(project.preferredMode == .iterative && project.nise.smiles.isEmpty)
        precondition(project.runNames.isEmpty)
        var named = project
        named.runNames = ["nise": "Ligand trial", "predict": "Fold trial"]
        let namedAgain = try JSONDecoder().decode(Project.self, from: JSONEncoder().encode(named))
        precondition(namedAgain.runNames == named.runNames)
        let roundTrip = try JSONEncoder().encode(project)
        let document = try JSONSerialization.jsonObject(with: roundTrip) as! [String: Any]
        precondition(document["preferredMode"] as? String == "iterative")
        var request = NISERequest()
        request.smiles = "CCO"
        precondition(request.validationIssues.isEmpty)
        precondition(request.max_cycles == 30 && request.patience == 4 && request.beam == 3 && request.trajectories == 8)
        precondition(request.early_score_gate == 0.8 && request.selective_affinity && !request.adaptive_proposals)
        precondition(request.num_starts == 1000 && request.backbone_method == "protein-hunter")
        precondition(request.nise_seqs == 32 && request.first_cycle_seqs == 64 && !request.partial_noising)
        precondition(request.firstCyclePredictionBudget == 8 * 64 && request.cyclePredictionBudget == 8 * 96)
        request.exposure_mode = "biotin-carboxamide-v1"
        request.geometry_workers = 4
        let exitRoundTrip = try JSONDecoder().decode(NISERequest.self, from: JSONEncoder().encode(request))
        precondition(exitRoundTrip.exposure_mode == request.exposure_mode && exitRoundTrip.geometry_workers == 4)
        request.selective_affinity = false
        precondition(!request.validationIssues.isEmpty)
        request.selective_affinity = true
        request.exposure_mode = "sasa"
        request.partial_noising = true
        precondition(request.validationIssues.isEmpty && request.normalParentCount == 2 && request.cyclePredictionBudget == 8 * 128)
        request.nesso_screen = true
        precondition(request.cyclePredictionBudget == 8 * (16 + 32 + 16))
        let noiseRoundTrip = try JSONDecoder().decode(NISERequest.self, from: JSONEncoder().encode(request))
        precondition(noiseRoundTrip == request)
        request.partial_noising = false; request.nesso_screen = false
        let version2 = try JSONDecoder().decode(NISERequest.self, from: Data(#"{"search_policy_version":2,"smiles":"CCO","nise_seqs":17}"#.utf8))
        precondition(version2.first_cycle_seqs == 17 && !version2.partial_noising)
        request.trajectories = 1001
        precondition(!request.validationIssues.isEmpty)
        request.num_starts = 500; request.trajectories = 100; request.beam = 3
        request.nise_seqs = 1000; request.nesso_screen = true; request.nesso_top_k = 20
        precondition(request.validationIssues.isEmpty)
        precondition(request.initialPredictionBudget == 12500)
        precondition(request.firstCyclePredictionBudget == 2000 && request.cyclePredictionBudget == 2000)
        request.nesso_top_k = 2
        precondition(!request.validationIssues.isEmpty)
        let prior = Data(#"{"smiles":"CCO","num_starts":48,"trajectories":6,"nise_seqs":64}"#.utf8)
        let restored = try JSONDecoder().decode(NISERequest.self, from: prior)
        precondition(restored.backbone_method == "protein-hunter")
        precondition(restored.max_cycles == 30 && restored.patience == 5 && !restored.selective_affinity && restored.early_score_gate == 0)
        precondition(restored.num_starts == 48 && restored.beam == 1 && !restored.nesso_screen)
        precondition(restored.phase0_refine_cycles == 2 && restored.phase0_seqs1 == 3 && restored.phase0_seqs2 == 5)
        let restoredAgain = try JSONDecoder().decode(NISERequest.self, from: JSONEncoder().encode(restored))
        precondition(restored == restoredAgain)
        request = NISERequest(); request.smiles = "CCO"; request.backbone_method = "rfdiffusion3"
        precondition(request.validationIssues.isEmpty && request.initialPredictionBudget == 24000)
        precondition(request.rfd3Lengths == [65, 86, 108, 129, 150])
        request.rfd3_num_bins = 1
        precondition(request.rfd3Lengths == [107])
        request.useSmallTrial()
        precondition(request.validationIssues.isEmpty)
        request.binder_min_len = request.binder_max_len + 1
        precondition(!request.validationIssues.isEmpty)
        request = NISERequest(); request.smiles = "CCO"
        request.hotspot_atoms = ["C8"]
        precondition(!request.validationIssues.isEmpty)
        request.ligand_atom_signature = String(repeating: "a", count: 64)
        request.ligand_atoms_generated_for = "CCO"
        precondition(request.validationIssues.isEmpty)
        request.exposed_atoms = ["C8"]
        precondition(!request.validationIssues.isEmpty)
        request.exposed_atoms = ["O7"]
        precondition(request.validationIssues.isEmpty)
        let selectedAgain = try JSONDecoder().decode(NISERequest.self, from: JSONEncoder().encode(request))
        precondition(selectedAgain == request)
        request.smiles = "CCN"
        precondition(!request.validationIssues.isEmpty)
        request.clearAtomSelections()
        precondition(request.validationIssues.isEmpty && request.hotspot_atoms.isEmpty && request.exposed_atoms.isEmpty)
        request = NISERequest(); request.smiles = "CCO"; request.phase0_nesso_screen = true
        precondition(request.usesNesso && !request.nesso_screen && request.validationIssues.isEmpty)
        precondition(request.initialPredictionBudget == 6020)
        request.backbone_method = "rfdiffusion3"
        precondition(request.initialPredictionBudget == 5020)
        request.phase0_nesso_refine_top_k = 4
        precondition(!request.validationIssues.isEmpty)
        request.phase0_nesso_refine_top_k = 1; request.phase0_nesso_expand_top_k = 5
        precondition(!request.validationIssues.isEmpty)
        request.phase0_nesso_expand_top_k = 20; request.phase0_sc_ca = .nan
        precondition(!request.validationIssues.isEmpty)
        let oldCustom = try JSONDecoder().decode(NISERequest.self, from: Data(#"{"smiles":"CCO","phase0_seqs1":7}"#.utf8))
        precondition(oldCustom.phase0_gate_seqs == 7 && !oldCustom.phase0_nesso_screen)
        let oldCustomAgain = try JSONDecoder().decode(NISERequest.self, from: JSONEncoder().encode(oldCustom))
        precondition(oldCustomAgain == oldCustom)
        var objective = NISERequest(); objective.smiles = "CCO"
        precondition(objective.scoring_mode == "boltz" && objective.objectiveEarlyGate == 0.8)
        objective.enableScreeningObjective()
        precondition(objective.validationIssues.isEmpty && objective.objectiveEarlyGate == 0.4)
        objective.objectiveEarlyGate = 1.25
        objective.screening_engine = "psichic"
        precondition(objective.objectiveEarlyGate == 0.2 && objective.objectiveFormula == "1 − predicted_nonbinder")
        objective.objectiveEarlyGate = 0.4
        objective.screening_engine = "nesso"
        precondition(objective.objectiveEarlyGate == 1.25)
        objective.scoring_mode = "boltz"
        precondition(objective.objectiveEarlyGate == 0.8)
        let copy = try JSONDecoder().decode(NISERequest.self, from: JSONEncoder().encode(objective))
        precondition(copy == objective)
        objective.enableScreeningObjective(); objective.nesso_screen = false
        precondition(!objective.validationIssues.isEmpty)
        precondition(oldCustom.scoring_mode == "boltz")
        precondition(oldCustom.nesso_early_score_gate == 0.4 && oldCustom.psichic_early_score_gate == 0.2)
        let historicalObjective = try JSONDecoder().decode(NISERequest.self, from: Data(#"{"scoring_mode":"screening","search_policy_version":3,"smiles":"CCO"}"#.utf8))
        precondition(historicalObjective.nesso_early_score_gate == 0 && historicalObjective.psichic_early_score_gate == 0)

        print("PASS NISE request and existing-workspace migration contracts")
    }
}
