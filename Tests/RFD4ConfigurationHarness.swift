import Foundation

@main struct RFD4ConfigurationHarness {
    static func main() throws {
        precondition(RFD4Request().optimized_kernels)
        var motifRequest = RFD4Request(); motifRequest.task = .motif; motifRequest.source = "motif.pdb"
        var motif = RFD4Motif(); motif.residues = [.init(chain: "A", residue: 10, atoms: ["N", "CA", "C", "O"])]
        motifRequest.motif = motif; precondition(motifRequest.validationIssues.isEmpty)
        motifRequest.optimized_kernels = false
        let motifCopy = try JSONDecoder().decode(RFD4Request.self, from: JSONEncoder().encode(motifRequest))
        precondition(motifCopy == motifRequest && !motifCopy.optimized_kernels)
        motifRequest.motif_assessment = RFD4MotifAssessment()
        precondition(motifRequest.validationIssues.isEmpty && motifRequest.predictions == 1)
        motifRequest.motif_assessment?.holo = true
        precondition(!motifRequest.validationIssues.isEmpty)
        motifRequest.motif?.partner_chains = ["B"]; motifRequest.target_msa = "empty"
        precondition(motifRequest.validationIssues.isEmpty && motifRequest.predictions == 2)
        let assessmentCopy = try JSONDecoder().decode(RFD4Request.self, from: JSONEncoder().encode(motifRequest))
        precondition(assessmentCopy == motifRequest)
        motifRequest.motif_assessment = nil
        motifRequest.motif?.fix_sequence = false; motifRequest.motif?.residues[0].atoms = ["CB"]
        precondition(!motifRequest.validationIssues.isEmpty)
        let plan = RFD4LengthPlan(minimum: 75, maximum: 79)
        precondition(plan.lengths(count: 2) == [75,79])
        precondition(plan.lengths(count: 1) == [77])
        precondition(plan.lengths(count: 7) == [75,76,77,78,79,75,76])
        let weighted = RFD4LengthPlan(minimum: 75, maximum: 150, counts: ["75":2,"120":3,"150":1])
        precondition(weighted.lengths(count: 6) == [75,120,150,75,120,120])
        precondition(!weighted.issues(count: 7).isEmpty)
        var request = RFD4Request(); request.task = .protein; request.source = "target.pdb"
        request.assess_native = true; request.target_msa = "empty"
        request.length_plan = weighted; request.count = 6
        request.hit_filters = ["ipsae_min":0.65,"iptm":0.5]
        precondition(request.validationIssues.isEmpty)
        let data = try JSONEncoder().encode(request)
        let restored = try JSONDecoder().decode(RFD4Request.self, from: data)
        precondition(restored == request)
        var legacy = try JSONSerialization.jsonObject(with: data) as! [String:Any]
        legacy.removeValue(forKey: "length_plan"); legacy.removeValue(forKey: "hit_filters")
        let old = try JSONDecoder().decode(RFD4Request.self, from: JSONSerialization.data(withJSONObject: legacy))
        precondition(old.length_plan == nil && old.hit_filters == nil)
        request.hit_filters = ["ipsae_min":1.5]; precondition(!request.validationIssues.isEmpty)
        request.hit_filters = nil; request.native_search = true; precondition(!request.validationIssues.isEmpty)
        var multi = RFD4Request(); multi.task = .nanobody; multi.source = "target.pdb"
        multi.scaffold_id = "7xl0_vobarilizumab"; multi.scaffold_weights = ["7xl0_vobarilizumab":2,"7eow_caplacizumab":1]; multi.count = 3
        multi.selection_metric = "iptm"
        precondition(multi.validationIssues.isEmpty)
        precondition(multi.frameworkCounts == ["7xl0_vobarilizumab":2,"7eow_caplacizumab":1])
        let multiCopy = try JSONDecoder().decode(RFD4Request.self, from: JSONEncoder().encode(multi))
        precondition(multiCopy == multi)
        multi.count = 1; precondition(!multi.validationIssues.isEmpty)
        var ligand = RFD4Request(); ligand.task = .ligand; ligand.ligand_smiles = "CCO"; ligand.predictor = "esmfold2-fast-mlx"
        ligand.assess_native = true; ligand.selection_metric = "ligand_plddt"
        precondition(ligand.validationIssues.isEmpty)
        ligand.selection_metric = "pbind"; precondition(!ligand.validationIssues.isEmpty)
        print("PASS RFD4 length allocation, validation, frozen settings and backward decoding")
    }
}
