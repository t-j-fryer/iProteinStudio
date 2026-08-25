import Foundation

// The production enum lives with DesignRequest. This focused harness compiles
// only the RFdiffusion3/Predict request models, so provide the same Codable
// surface without pulling the iterative-design dependency graph into the test.
enum IntelliFoldModel: String, CaseIterable, Codable, Hashable, Identifiable {
    case v2flash = "v2-flash"
    case v2
    var id: String { rawValue }
}

enum TemplateWriter {
    static func clean(_ value: String) -> String {
        String(value.uppercased().unicodeScalars.filter { ("A"..."Z").contains(Character($0)) })
    }
}

@main
struct WorkflowRequestContractHarness {
    static var failures: [String] = []

    static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        if !condition() { failures.append(message) }
    }

    static func proteinRFD3(structure: URL) -> RFD3Request {
        var request = RFD3Request()
        request.targetKind = .protein
        request.targetStructurePath = structure.path
        request.targetChain = "B"
        request.targetContig = "B1-8"
        request.targetSequence = "ACDEFGHI"
        request.structureTargetSequence = "ACDEFGHI"
        request.sequenceModel = .proteinmpnn
        request.numDesigns = 4
        request.sequencesPerBackbone = 3
        request.verification.topN = 10
        request.verification.extraPredictors = [.boltzPotentials, .boltz, .intellifold]
        request.reconcileVerification()
        return request
    }

    static func testRFD3Contracts(structure: URL) {
        var request = proteinRFD3(structure: structure)
        expect(request.validationIssues.isEmpty, "valid protein RFdiffusion3 request was rejected")
        expect(request.verification.allPredictors(for: .protein) == [.boltz, .intellifold],
               "RFdiffusion3 predictors were not canonicalized")
        expect(request.requiredComponents.contains(.boltz), "protein MSA generator dependency is missing")
        expect(request.totalDesignedSequences == 12, "sequence budget ignored sequences per backbone")

        request.targetSequence = "ACDEFGHI:KLMNPQRS"
        request.structureTargetSequence = request.targetSequence
        request.targetChain = "B,C"
        request.targetContig = "B1-8,/0,C1-8"
        expect(request.targetChains.map(\.id) == ["B", "C"],
               "RFdiffusion3 did not retain the B/C target mapping")
        expect(request.validationIssues.isEmpty, "valid RFdiffusion3 multimer target was rejected")

        request.targetChain = "B"
        expect(request.validationIssues.contains { $0.contains("number of selected") },
               "RFdiffusion3 accepted two sequences mapped onto one structure chain")

        request.structureTargetSequence = "AAAAAAAA"
        expect(request.validationIssues.contains { $0.contains("does not match") },
               "structure/sequence mismatch was not blocked")

        request = proteinRFD3(structure: structure)
        request.numDesigns = 1
        request.sequencesPerBackbone = 1
        request.reconcileSelectionBudget()
        expect(request.verification.topN == 1, "top-N was not clamped to the produced sequence count")
    }

    static func testPredictionContracts() {
        var request = PredictionRequest()
        request.pastedSequences = "AAAAA"
        request.predictors = [.boltzPotentials, .boltz, .intellifold, .intellifold]
        request.jobs = [FoldJob(name: "one", chains: [
            .init(id: "A", kind: "protein", sequence: "AAAAA", msa: "auto")
        ])]
        request.normalizeEngineOptions()
        request.parsedInputSignature = request.inputSignature
        expect(request.effectivePredictors == [.boltz, .intellifold],
               "prediction engines were not canonicalized")
        expect(request.isRunnable, "current parsed prediction request was not runnable")
        expect(request.numberOfSeeds == 1 && request.diffusionSamples == 0,
               "new prediction sampling controls changed the established defaults")

        request.numberOfSeeds = 3
        request.diffusionSamples = 2
        let roundTrip = try! JSONDecoder().decode(PredictionRequest.self,
                                                  from: JSONEncoder().encode(request))
        expect(roundTrip.numberOfSeeds == 3 && roundTrip.diffusionSamples == 2,
               "prediction sampling controls did not survive project serialization")

        request.pairing = .shared
        request.partnerSequence = "CCCCC"
        expect(!request.jobsAreCurrent, "editing prediction inputs did not invalidate parsed jobs")
        expect(request.validationIssues.contains { $0.contains("Read sequences again") },
               "stale prediction jobs had no actionable error")

        request.predictors = [.alphafold3, .intellifoldJAX]
        request.normalizeEngineOptions()
        expect(request.effectivePredictors.isEmpty && !request.isRunnable,
               "retired Metal engines survived prediction-request normalization")
        expect(!Predictor.predictionChoices.contains(.alphafold3)
               && !Predictor.predictionChoices.contains(.intellifoldJAX),
               "retired Metal engines remained visible in prediction choices")

        request.predictors = [.openfold3]
        request.normalizeEngineOptions()
        expect(request.requiredComponents.contains(.boltz),
               "non-Boltz prediction with automatic MSA omitted the hidden Boltz dependency")

        request.numberOfSeeds = 0
        expect(request.validationIssues.contains { $0.contains("Seeds per fold") },
               "an invalid prediction seed count was accepted")
    }

    static func testLigandAttachmentContract() throws {
        var request = RFD3Request()
        request.targetKind = .smallMolecule
        request.smiles = "CCOC"
        request.componentCode = "LG1"
        request.ligandIsConjugated = true
        request.attachmentAtom = 1
        expect(request.validationIssues.contains { $0.contains("both ends") },
               "an ambiguous one-atom linker selection was accepted")

        request.attachmentLinkerAtom = 2
        expect(!request.validationIssues.contains { $0.contains("both ends") },
               "a complete directed linker bond was rejected")
        let data = try JSONEncoder().encode(request)
        let decoded = try JSONDecoder().decode(RFD3Request.self, from: data)
        expect(decoded.attachmentAtom == 1 && decoded.attachmentLinkerAtom == 2,
               "directed linker bond did not survive project serialization")
        expect(decoded.ligandIsConjugated,
               "conjugated-ligand intent did not survive project serialization")
    }

    static func main() throws {
        let structure = FileManager.default.temporaryDirectory
            .appendingPathComponent("workflow-contract-\(UUID().uuidString).pdb")
        try "MODEL\nEND\n".write(to: structure, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: structure) }

        testRFD3Contracts(structure: structure)
        try testLigandAttachmentContract()
        testPredictionContracts()
        if failures.isEmpty {
            print("PASS workflow request contract")
        } else {
            for failure in failures { fputs("FAIL: \(failure)\n", stderr) }
            exit(1)
        }
    }
}
