import Foundation

enum IntelliFoldModel: String, Codable, Hashable { case v2flash = "v2-flash", v2 }

@main
struct PredictionTemplateContractHarness {
    static func main() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let file = directory.appendingPathComponent("template.pdb")
        try Data("synthetic fixture".utf8).write(to: file)
        let old = try JSONDecoder().decode(PredictionRequest.self, from: Data("{}".utf8))
        precondition(!old.hasTemplate && old.templateChainIDs.isEmpty)
        var request = PredictionRequest()
        request.jobs = [.init(name: "one", chains: [.init(id: "A", kind: "protein", sequence: "ACDEFGHIK", msa: "empty")])]
        request.parsedInputSignature = request.inputSignature
        request.templatePath = file.path
        request.templateEnabled = true
        precondition(!request.validationIssues.isEmpty, "Must explicitly select chains")
        request.templateChainIDs = ["A"]
        precondition(request.validationIssues.isEmpty && request.jobsAreCurrent)
        precondition(request.commonProteinChainIDs == ["A"])
        let saved = try JSONEncoder().encode(request)
        let restored = try JSONDecoder().decode(PredictionRequest.self, from: saved)
        precondition(restored == request)
        var legacy = try JSONSerialization.jsonObject(with: saved) as! [String: Any]
        legacy.removeValue(forKey: "templateEnabled")
        let migrated = try JSONDecoder().decode(PredictionRequest.self, from: JSONSerialization.data(withJSONObject: legacy))
        precondition(migrated.templateEnabled && migrated.hasTemplate, "Existing guided jobs remain guided")
        request.templateEnabled = false
        request.predictors = [.protenixMini]
        precondition(!request.hasTemplate && request.validationIssues.isEmpty, "Off must disable guidance and engine restrictions")
        let disabled = try JSONDecoder().decode(PredictionRequest.self, from: JSONEncoder().encode(request))
        precondition(!disabled.templateEnabled && disabled.templatePath == file.path, "Off retains the chosen file across reopening")
        request.templateEnabled = true
        request.predictors = [.protenixMini]
        precondition(!request.validationIssues.isEmpty, "Mini cannot use templates")
        request.predictors = [.protenixV2]
        precondition(request.validationIssues.isEmpty)
        request.jobs[0].chains.append(.init(id: "B", kind: "protein", sequence: "ACDEFGHIK", msa: "empty"))
        precondition(!request.validationIssues.isEmpty, "Identical entity copies cannot be partly templated")
        request.templateChainIDs = ["A", "B"]
        precondition(request.validationIssues.isEmpty)
        request.jobs.append(.init(name: "two", chains: [.init(id: "A", kind: "protein", sequence: "ACDEFGHIK", msa: "empty")]))
        precondition(request.commonProteinChainIDs == ["A"] && !request.validationIssues.isEmpty)
        request.templateChainIDs = ["A"]
        request.jobs.removeFirst()
        try FileManager.default.removeItem(at: file)
        precondition(!request.validationIssues.isEmpty, "Missing structures must block starting")
        request.templateEnabled = false
        precondition(request.validationIssues.isEmpty, "A disabled missing template must not prevent an untemplated run")
        request.templatePath = ""
        request.templateEnabled = true
        precondition(!request.validationIssues.isEmpty, "Turning on guidance requires a structure")
        print("PASS Predict template request, persistence and chain/engine constraints")
    }
}
