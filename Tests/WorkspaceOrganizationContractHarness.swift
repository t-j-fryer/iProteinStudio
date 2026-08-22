import Foundation

@main
struct WorkspaceOrganizationContractHarness {
    static var failures: [String] = []

    static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        if !condition() { failures.append(message) }
    }

    static func main() throws {
        expect(WorkspaceMode.allCases == [.iterative, .rfdiffusion, .predict],
               "workspace workflow order changed")
        expect(WorkspaceMode.predict.defaultWorkspaceName == "Untitled Prediction",
               "freeform prediction no longer has a truthful default name")

        let names = ["Untitled Prediction", "untitled prediction 2"]
        expect(WorkspaceNaming.uniqueName(base: "Untitled Prediction", existing: names)
               == "Untitled Prediction 3",
               "default prediction names can collide or differ only by case")
        expect(WorkspaceNaming.uniqueName(base: "  Cobratoxin  ", existing: []) == "Cobratoxin",
               "workspace names were not trimmed")

        expect(WorkspaceNaming.slugify("Anti-CMY2 / round 1") == "anti_cmy2_round_1",
               "workspace slug normalization drifted")
        expect(WorkspaceNaming.uniqueSlug(for: "Cobratoxin", existing: ["cobratoxin", "cobratoxin_2"])
               == "cobratoxin_3",
               "workspace output directories can collide")

        let encoded = try JSONEncoder().encode(WorkspaceMode.predict)
        let decoded = try JSONDecoder().decode(WorkspaceMode.self, from: encoded)
        expect(decoded == .predict, "remembered workspace workflow did not survive persistence")

        if failures.isEmpty {
            print("PASS workspace organization contract")
        } else {
            for failure in failures { fputs("FAIL: \(failure)\n", stderr) }
            exit(1)
        }
    }
}
