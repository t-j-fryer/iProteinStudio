import Foundation

@main struct RecommendedWorkflowHarness {
    static func main() throws {
        for intention in [DesignIntention.minibinder, .nanobody, .smallMolecule] {
            for hard in [false, true] {
                var request = RecommendedDesign.request(intention: intention, hard: hard, minutes: 90)
                if intention == .smallMolecule { request.ligand_smiles = "CCO" }
                else { request.source = "target.cif" }
                precondition(request.validationIssues.isEmpty, request.validationIssues.joined(separator: "; "))
                precondition(request.cycles == 7 && request.time_budget_minutes == 90)
                precondition(request.search == (hard ? .beam : .native))
                precondition(request.assess_native == !hard && !request.native_search)
                precondition(request.predictor == (intention == .smallMolecule ? "boltz" : "esmfold2-full-mlx"))
                precondition(request.sequence_model == (intention == .smallMolecule ? "lasermpnn" : intention == .nanobody ? "abmpnn" : "solublempnn"))
                let saved = SavedDesignWorkflow(name: "Custom", intention: intention, route: .rfd4, parameters: try JSONEncoder().encode(request))
                let decoded = try JSONDecoder().decode(SavedDesignWorkflow.self, from: JSONEncoder().encode(saved))
                precondition(saved == decoded)
                let restored = try JSONDecoder().decode(RFD4Request.self, from: decoded.parameters)
                precondition(restored == request)
            }
        }
        var old = try JSONSerialization.jsonObject(with: JSONEncoder().encode(RFD4Request())) as! [String: Any]
        old.removeValue(forKey: "time_budget_minutes"); old.removeValue(forKey: "scaffold_id")
        let migrated = try JSONDecoder().decode(RFD4Request.self, from: JSONSerialization.data(withJSONObject: old))
        precondition(migrated.time_budget_minutes == nil && migrated.scaffold_id == nil)
        precondition(!DesignIntention.nanobody.routes.contains(.rfd3))
        precondition(DesignIntention.smallMolecule.routes.contains(.nise))
        precondition(DesignIntention.monomer.routes == [.rfd4, .rfd3Monomer, .proteinHunter])
        precondition(DesignIntention.motif.routes.contains(.proteinHunter))
        precondition(DesignIntention.optimize.rfd4Tasks == [.partial, .inverse])
        precondition(RecommendedDesign.hotspots("B32 C:55")?.qualified == ["B32", "C:55"])
        precondition(RecommendedDesign.hotspots("B0") == nil)
        let assembly = ["B": 20, "C": 20]
        precondition(RecommendedDesign.hotspotIssues(RecommendedDesign.hotspots("B3 C:5")!, chainLengths: assembly).isEmpty)
        for invalid in ["3", "A3", "C21", "B3 B:3"] {
            precondition(!RecommendedDesign.hotspotIssues(RecommendedDesign.hotspots(invalid)!, chainLengths: assembly).isEmpty)
        }
        precondition(RecommendedDesign.hotspotIssues(RecommendedDesign.hotspots("3")!, chainLengths: ["B": 20]).isEmpty)
        var invalid = RFD4Request(); invalid.native_search = true; invalid.native_partial_fraction = .nan
        precondition(!invalid.validationIssues.isEmpty && invalid.predictions == 0)
        print("PASS recommended routes, seven-cycle proposals, snapshot round trips, legacy migration and invalid-number rejection")
    }
}
