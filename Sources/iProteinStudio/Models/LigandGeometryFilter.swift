import Foundation

/// Optional predicted-holo geometry gate, independent of generator conditioning.
struct LigandGeometryFilter: Codable, Hashable {
    var schema = 1
    var mode = "sasa"
    var contact_atoms: [Int] = []
    var exposed_atoms: [Int] = []
    var contact_distance = 6.0
    var exposure_min_fraction = 0.5

    init() {}
    private enum CodingKeys: String, CodingKey { case schema, mode, contact_atoms, exposed_atoms, contact_distance, exposure_min_fraction }
    init(from decoder: Decoder) throws {
        self.init()
        let c = try decoder.container(keyedBy: CodingKeys.self)
        schema = try c.decodeIfPresent(Int.self, forKey: .schema) ?? schema
        mode = try c.decodeIfPresent(String.self, forKey: .mode) ?? mode
        contact_atoms = try c.decodeIfPresent([Int].self, forKey: .contact_atoms) ?? []
        exposed_atoms = try c.decodeIfPresent([Int].self, forKey: .exposed_atoms) ?? []
        contact_distance = try c.decodeIfPresent(Double.self, forKey: .contact_distance) ?? contact_distance
        exposure_min_fraction = try c.decodeIfPresent(Double.self, forKey: .exposure_min_fraction) ?? exposure_min_fraction
    }

    var validationIssues: [String] {
        var issues: [String] = []
        if [contact_atoms, exposed_atoms].contains(where: { Set($0).count != $0.count || $0.contains(where: { $0 < 0 }) }) { issues.append("Choose distinct valid atom indices.") }
        if schema != 1 || !["sasa", "biotin-carboxamide-v1"].contains(mode) { issues.append("Choose a supported ligand geometry policy.") }
        if mode == "sasa" && contact_atoms.isEmpty && exposed_atoms.isEmpty { issues.append("Choose contact or exposed atoms for the geometry hit filter.") }
        if !Set(contact_atoms).isDisjoint(with: exposed_atoms) { issues.append("An atom cannot require both contact and exposure.") }
        if !(0.1...20).contains(contact_distance) || !(0.01...1).contains(exposure_min_fraction) { issues.append("Enter valid geometry distances and accessibility thresholds.") }
        return issues
    }
    var json: String { (try? String(data: JSONEncoder().encode(self), encoding: .utf8)) ?? "{}" }
}
