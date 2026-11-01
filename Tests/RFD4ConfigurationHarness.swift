import Foundation

@main struct RFD4ConfigurationHarness {
    static func main() throws {
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
        print("PASS RFD4 length allocation, validation, frozen settings and backward decoding")
    }
}
