import Foundation

enum StudioWorkflow: String, Codable { case iterative, prediction, nise, rfd4, rfdiffusion3; var label: String { rawValue } }

@main
struct ResultAnalysisHarness {
    static func main() throws {
        var checks = 0
        func check(_ condition: @autoclosure () -> Bool, _ message: String) {
            precondition(condition(), message); checks += 1
        }
        func item(_ id: String, family: String = "family-A", cycle: Int? = 1,
                  metrics: [StudioResultMetric] = [], hit: Bool? = nil,
                  role: StudioResultArtifactRole = .designedComplex,
                  stage: StudioResultStage = .design, source: String = "Boltz 2",
                  variant: String? = nil, sequence: String? = "GAS") -> StudioResultItem {
            StudioResultItem(id: id, title: id, subtitle: "", structureURL: URL(fileURLWithPath: "/fixture/\(id).cif"),
                sequence: sequence, metrics: metrics, confidenceURL: nil, stage: stage, scoreSource: source,
                isHit: hit, groupID: family, groupTitle: family, variantID: variant ?? id, variantTitle: id,
                artifactRole: role, cycle: cycle)
        }
        let a = item("a", metrics: [.init(kind: .ipsaeMinimum, value: 0.3), .init(kind: .iptm, value: 0.9),
                                    .init(kind: .plddt, value: 0.8)], hit: false)
        let b = item("b", cycle: 2, metrics: [.init(kind: .ipsaeMinimum, value: 0.8),
                                             .init(kind: .complexRMSD, value: 1.5)], hit: true)
        let c = item("c", family: "family-B", metrics: [.init(kind: .ipsaeMinimum, value: 0.5)], hit: false)
        let missing = item("missing", family: "family-C", metrics: [.init(kind: .iptm, value: 0.99)], hit: true)
        let bad = item("bad", metrics: [.init(kind: .ipsaeMinimum, value: .nan)])
        let initial = item("initial", cycle: 0, metrics: [.init(kind: .ipsaeMinimum, value: 1)], hit: true,
                           role: .startingStructure, stage: .startingStructure)
        check(ResultAnalysis.defaultMetric(in: [a]) == .ipsaeMinimum, "Protein default must prefer ipSAE(min)")
        var ligand = item("ligand", metrics: [.init(kind: .bindingProbability, value: 0.7), .init(kind: .ligandPLDDT, value: 85)])
        ligand.smallMoleculeDesign = true
        check(ResultAnalysis.defaultMetric(in: [ligand]) == .boltzCombinedScore, "Ligand default")
        check(abs(ligand.metrics.first { $0.kind == .boltzCombinedScore }!.value - 1.55) < 1e-12, "Combined score formula")
        var noCombined = a; noCombined.smallMoleculeDesign = true
        check(ResultAnalysis.defaultMetric(in: [noCombined]) == .boltzCombinedScore, "Do not silently replace missing ligand default")
        let splitP = item("splitP", metrics: [.init(kind: .bindingProbability, value: 0.8)], variant: "same")
        let splitL = item("splitL", metrics: [.init(kind: .ligandPLDDT, value: 90)], role: .complexReprediction, variant: "same")
        check(ResultAnalysis.candidates(from: [splitP, splitL])[0].metric(.boltzCombinedScore) == nil, "Never combine components across assessments")
        let invalidP = item("invalid", metrics: [.init(kind: .bindingProbability, value: 1.5), .init(kind: .ligandPLDDT, value: 90)])
        check(invalidP.metrics.allSatisfy { $0.kind != .boltzCombinedScore }, "Reject out-of-range components")
        check(ResultAnalysis.value(.init(kind: .plddt, value: 0.8)) == 80, "Confidence filter uses 0–100")
        check(ResultAnalysis.value(.init(kind: .pocketFractionWithinCutoff, value: 0.8)) == 80, "Pocket fraction filter uses percent")
        check(ResultAnalysis.value(.init(kind: .ipsaeMinimum, value: .infinity)) == nil, "Nonfinite scores absent")

        let candidates = ResultAnalysis.candidates(from: [a, b, c, missing, bad, initial])
        check(candidates.count == 5 && !candidates.contains { $0.name.contains("initial") }, "One row per design, initialization excluded")
        let zeroDesign = item("zero", cycle: 0, metrics: [.init(kind: .ipsaeMinimum, value: 0.4)], hit: true)
        check(ResultAnalysis.candidates(from: [zeroDesign]).count == 1, "Scored cycle zero is not automatically an unoptimized start")
        let legacy = item("legacy", cycle: nil, metrics: a.metrics, variant: "cycle|3")
        check(ResultAnalysis.candidates(from: [legacy])[0].cycle == 3, "Legacy iterative cycle metadata")
        var policy = ResultHitPolicy()
        check(Set(policy.select(candidates, defaultMetric: .ipsaeMinimum).map(\.name)) == ["family-A · b", "family-C · missing"], "Saved verdicts preserved")
        policy.mode = .custom
        policy.rules = [.init(metric: .ipsaeMinimum, threshold: "0.3")]
        check(policy.select(candidates, defaultMetric: .ipsaeMinimum).map(\.name) == ["family-A · b", "family-B · c", "family-A · a"], "Custom filters admit failed hits and fail missing/nonfinite")
        check(candidates.first { $0.name == "family-A · a" }?.savedHit == false, "Raw verdict never mutated")
        policy.descending = false
        check(policy.select(candidates, defaultMetric: .ipsaeMinimum).first?.name == "family-A · a", "Ascending sort")
        policy.maxPerFamily = "1"; policy.descending = true
        check(policy.select(candidates, defaultMetric: .ipsaeMinimum).map(\.name) == ["family-A · b", "family-B · c"], "Family cap after ranking")
        policy.rules.append(.init(metric: .complexRMSD, comparison: .maximum, threshold: "1.5"))
        check(policy.select(candidates, defaultMetric: .ipsaeMinimum).count == 1, "AND and inclusive maximum")
        policy.rules[1].comparison = .less
        check(policy.select(candidates, defaultMetric: .ipsaeMinimum).isEmpty, "Strict maximum")
        policy.rules = [.init(metric: .ipsaeMinimum, comparison: .greater, threshold: "0.5")]
        check(policy.select(candidates, defaultMetric: .ipsaeMinimum).count == 1, "Strict minimum")
        for invalid in ["", "NaN", "inf", "xyz"] {
            policy.rules[0].threshold = invalid
            check(policy.validationMessage != nil && policy.select(candidates, defaultMetric: .ipsaeMinimum).isEmpty, "Invalid threshold \(invalid)")
        }
        policy.rules = []; policy.maxPerFamily = "-1"
        check(policy.validationMessage != nil, "Negative family cap rejected")
        policy.maxPerFamily = "1.5"; check(policy.validationMessage != nil, "Fractional family cap rejected")
        policy.maxPerFamily = ""; policy.descending = false
        check(policy.select(candidates, defaultMetric: .ipsaeMinimum).last?.metric(.ipsaeMinimum) == nil, "Missing scores always sort last")
        let encoded = try JSONEncoder().encode(policy)
        let decoded = try JSONDecoder().decode(ResultHitPolicy.self, from: encoded)
        check(decoded == policy, "Review policy persists")

        var duplicate = a; duplicate = item("a-copy", metrics: a.metrics, variant: "a")
        let otherEngine = item("e", metrics: [.init(kind: .ipsaeMinimum, value: 0.9)], source: "ESMFold2")
        let independent = item("a-check", metrics: [.init(kind: .ipsaeMinimum, value: 0.1)], role: .complexReprediction,
                               stage: .postPrediction, variant: "a")
        let medians = ResultAnalysis.cycleMedians(items: [a, duplicate, c, b, initial, bad, missing, legacy, otherEngine, independent], metric: .ipsaeMinimum)
        let designSeries = medians.filter { $0.series == "Boltz 2 · Design stage · Design structure" }
        check(designSeries.count == 3, "Explicit and legacy cycles")
        check(designSeries.first?.count == 2 && abs(designSeries.first!.median - 0.4) < 1e-12, "Even median, duplicate candidate ignored, includes unselected proposals")
        check(designSeries[1].median == 0.8 && designSeries[1].count == 1, "Odd median")
        check(medians.count == 5, "Independent checks and engines stay separate")
        check(ResultAnalysis.cycleMedians(items: [initial], metric: .ipsaeMinimum).isEmpty, "Unoptimized initialization not plotted")
        check(ResultAnalysis.cycleMedians(items: [zeroDesign], metric: .ipsaeMinimum).first?.cycle == 0, "Actual design cycle zero retained")
        let associated = ResultAnalysis.candidates(from: [a, independent])
        check(associated.count == 1 && associated[0].metric(.ipsaeMinimum) == 0.1, "Associated complex assessment preferred")

        let awkward = item("quoted", family: "=SUM(1,2)\n\"α\"", metrics: [.init(kind: .complexRMSD, value: -2.5)], sequence: nil)
        let exported = ResultAnalysis.candidates(from: [a, awkward])
        let csv = ResultAnalysis.csv(exported, mode: "custom")
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".csv")
        defer { try? FileManager.default.removeItem(at: url) }
        try csv.write(to: url, atomically: true, encoding: .utf8)
        let rows = CSVTable.rows(at: url)
        check(rows.count == 2, "CSV round-trip with commas, Unicode, quotes and embedded newline")
        check(rows.contains { $0["design_sequence"] == "GAS" && $0["pLDDT (0–100)"] == "80.0" }, "CSV sequence and canonical numeric score")
        check(rows.contains { $0["design_sequence"] == "" && $0["family_id"] == "'=SUM(1,2)\n\"α\"" }, "Blank sequence and formula protection")
        check(rows.contains { $0[ResultAnalysis.metricLabel(.complexRMSD)] == "-2.5" }, "Negative numeric score not escaped as text")
        check(rows.allSatisfy { $0["selection_mode"] == "custom" }, "Selection mode recorded")
        check(rows.contains { $0[ResultAnalysis.metricLabel(.complexRMSD)] == "" }, "Absent score stays blank")
        print("PASS \(checks) results analysis/default/median/filter/sort/family/CSV contracts")
    }
}
