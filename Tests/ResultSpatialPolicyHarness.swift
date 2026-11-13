import Foundation

enum StudioWorkflow: String, Codable { case rfd4, iterative, nise, rfdiffusion3, prediction; var label: String { rawValue } }
@main struct ResultSpatialPolicyHarness {
    static func main() throws {
        var policy = ResultSpatialPolicy()
        policy.binderChains = "A"; policy.targetChain = "B"; policy.residues = "10,11A"
        precondition(policy.validationMessage == nil)
        if CommandLine.arguments.count == 3 {
            let source = URL(fileURLWithPath: CommandLine.arguments[1])
            let output = URL(fileURLWithPath: CommandLine.arguments[2])
            let object: [String: Any] = ["policy": try JSONSerialization.jsonObject(with: policy.json),
                "policy_sha256": policy.digest, "cache": output.deletingLastPathComponent().appendingPathComponent("measurements").path,
                "units": [["id": "native-fixture", "source_item_id": "complex", "source": source.path, "source_stamp": ResultFileStamp.read(source)!]]]
            try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]).write(to: output)
            return
        }
        let original = policy.digest
        policy.cutoff = "9"; precondition(original != policy.digest)
        policy.cutoff = ""; precondition(policy.validationMessage != nil)
        policy.mode = .ligand; policy.cutoff = "8"; policy.targetChain = "A"; policy.ligandResidue = "901"
        precondition(policy.validationMessage == nil)
        policy.ligandResidue = ""; precondition(policy.validationMessage != nil)
        print("PASS spatial policy editing, exact digest changes and explicit shared-chain ligand validation")
    }
}
