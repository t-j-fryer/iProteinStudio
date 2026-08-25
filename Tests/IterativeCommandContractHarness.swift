import Foundation

enum IntelliFoldModel: String, CaseIterable, Codable, Identifiable {
    case v2flash = "v2-flash"
    case v2
    var id: String { rawValue }
}

// Minimal runtime-path surface needed to compile the real CommandBuilder in a
// framework-free harness. The argument tests never read or write these paths.
enum AppPaths {
    static let fm = FileManager.default
    static let support = URL(fileURLWithPath: "/tmp/iproteinstudio-contract")
    static let msaCache = support.appendingPathComponent("msa_cache")
    static let scaffoldMSACache = support.appendingPathComponent("scaffold_msa_cache")
    static let boltzCache = support.appendingPathComponent("boltz_cache")
    static let numbaCache = support.appendingPathComponent("numba_cache")
    static let intelliFoldCache = support.appendingPathComponent("intellifold_cache")
}

struct NHError: LocalizedError {
    let text: String
    var errorDescription: String? { text }
    static func message(_ text: String) -> NHError { NHError(text: text) }
}

@main
struct IterativeCommandContractHarness {
    static var failures: [String] = []
    static let template = URL(fileURLWithPath: "/tmp/contract-template.yaml")
    static let output = URL(fileURLWithPath: "/tmp/contract-output")

    static func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
        if !condition() { failures.append(message) }
    }

    static func value(after flag: String, in args: [String]) -> String? {
        guard let index = args.firstIndex(of: flag), args.indices.contains(index + 1) else { return nil }
        return args[index + 1]
    }

    static func proteinRequest() -> DesignRequest {
        var request = DesignRequest()
        request.designType = .minibinder
        request.targetKind = .protein
        request.targetSequence = "MKTIIALSYIFCLVFADYKDDDDK"
        request.designer = .solublempnn
        request.designPredictor = .boltz
        request.postPredictors = []
        request.epitopeResidues = "34 B:35"
        request.numDesigns = 4
        request.numCycles = 5
        request.hitThreshold = 0.70
        return request
    }

    static func arguments(_ request: DesignRequest, seed: Int = 1234) -> [String] {
        CommandBuilder.arguments(request: request, templateYAML: template,
                                 outRoot: output, runName: "contract", mpnnSeed: seed)
    }

    static func testBoltzProteinHotspots() throws {
        let request = proteinRequest()
        let args = arguments(request)
        expect(value(after: "--iptm-threshold", in: args) == "0.70", "campaign hit threshold was not emitted")
        expect(value(after: "--post-predictor", in: args) == "none", "empty checker list was not explicit")
        expect(value(after: "--post-mode", in: args) == "none", "empty checker mode was not none")
        expect(args.contains("--boltz-use-potentials"), "protein hotspots did not enable Boltz potentials")
        expect(value(after: "--binder-random-seed", in: args) == "1234", "cycle-0 binder seed was not recorded")
        expect(!args.contains("--boltz-no-potentials"), "contradictory no-potentials flag was emitted")
        expect(!args.contains("--model"), "irrelevant IntelliFold model was emitted")
        expect(!args.contains("--post-iptm-threshold"), "irrelevant post threshold was emitted")

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("protein-hotspot-\(UUID().uuidString).yaml")
        defer { try? FileManager.default.removeItem(at: url) }
        try TemplateWriter.write(request, to: url)
        let yaml = try String(contentsOf: url, encoding: .utf8)
        expect(yaml.contains("- B34") && yaml.contains("- B35"), "hotspots were not normalized")
        expect(yaml.contains("boltz_contact_mode: auto"), "template did not delegate workflow-specific mode")
        expect(!yaml.contains("pocket+cdr3"), "generic template hard-coded a nanobody CDR mode")
    }

    static func testMultimerTargetMapping() throws {
        var request = proteinRequest()
        request.targetSequence = "ACDEFGHIK:LMNPQRSTV"
        request.epitopeResidues = "B3 C7"
        expect(request.targetChainIDs == ["B", "C"], "multimer targets were not assigned B/C")
        expect(request.isRunnable, "valid colon-separated multimer target was rejected")

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("multimer-target-\(UUID().uuidString).yaml")
        defer { try? FileManager.default.removeItem(at: url) }
        try TemplateWriter.write(request, to: url)
        let yaml = try String(contentsOf: url, encoding: .utf8)
        expect(yaml.contains("id: B\n      sequence: ACDEFGHIK")
               && yaml.contains("id: C\n      sequence: LMNPQRSTV"),
               "template did not preserve both target subunits")
        expect(yaml.contains("- B3") && yaml.contains("- C7"),
               "chain-qualified multimer hotspots were not preserved")

        request.epitopeResidues = "D2"
        expect(!request.isRunnable, "hotspot on a nonexistent target chain was accepted")
    }

    static func testPostChecksAndModels() {
        var request = proteinRequest()
        request.epitopeResidues = ""
        request.postPredictors = [.intellifold]
        request.intellifoldModel = .v2
        request.postOnlyHits = true
        var args = arguments(request)
        expect(value(after: "--post-predictor", in: args) == "intellifold", "IntelliFold checker missing")
        expect(value(after: "--post-mode", in: args) == "final-iptm", "checks were not limited to passing final designs")
        expect(value(after: "--post-iptm-threshold", in: args) == "0.70", "post gate missing")
        expect(value(after: "--model", in: args) == "v2", "selected IntelliFold model missing")

        request.postPredictors = [.openfold3]
        request.postOnlyHits = false
        args = arguments(request)
        expect(value(after: "--post-mode", in: args) == "final", "ungated checks included intermediate cycles")
        expect(!args.contains("--post-iptm-threshold"), "ungated check emitted an irrelevant threshold")
        expect(!args.contains("--model"), "OpenFold-only request emitted an IntelliFold model")

        request.postCheckScope = .allCycles
        args = arguments(request)
        expect(value(after: "--post-mode", in: args) == "all", "ungated all-cycle checking was not emitted")
        expect(args.contains("--post-include-cycle00"), "all-cycle checking silently skipped cycle 00")
        request.postOnlyHits = true
        args = arguments(request)
        expect(value(after: "--post-mode", in: args) == "iptm", "hit-gated all-cycle checking was not emitted")
        expect(args.contains("--post-include-cycle00"), "hit-gated all-cycle checking skipped cycle 00")
    }

    static func testCanonicalCheckers() {
        var request = proteinRequest()
        request.epitopeResidues = ""
        request.designPredictor = .intellifold
        request.postPredictors = [.intellifold, .boltzPotentials, .boltz, .openfold3, .openfold3]
        expect(request.effectivePostPredictors == [.boltz, .openfold3], "checker list was not canonical and independent")
        expect(value(after: "--post-predictor", in: arguments(request)) == "boltz,openfold-3-mlx", "canonical checker command was wrong")

        request.postPredictors = [.boltz]
        request.epitopeResidues = "34"
        request.reconcilePredictors()
        expect(request.designPredictor == .boltzPotentials, "hotspot targeting did not select its required design engine")
        expect(request.effectivePostPredictors == [.intellifold], "previous design engine was not retained as the orthogonal checker")

        request = proteinRequest()
        request.epitopeResidues = ""
        request.postPredictors = [.intellifold]
        request.selectDesignPredictor(.intellifold)
        expect(request.effectivePostPredictors == [.boltz], "changing drivers did not swap the former driver into checking")
    }

    static func testDesignerSeeds() {
        var request = proteinRequest()
        request.epitopeResidues = ""
        request.designer = .solublempnn
        expect(value(after: "--mpnn-seed", in: arguments(request)) == "1234", "MPNN seed routing failed")

        request.designType = .nanobody
        request.scaffoldSequence = String(repeating: "A", count: 120)
        request.designer = .antifold
        expect(value(after: "--antifold-seed", in: arguments(request)) == "1234", "AntiFold seed routing failed")
        expect(!arguments(request).contains("--mpnn-seed"), "AntiFold received an irrelevant MPNN seed")

        request.designType = .minibinder
        request.targetKind = .ligand
        request.targetSmiles = "CCO"
        request.targetSequence = ""
        request.designer = .lasermpnn
        expect(value(after: "--lasermpnn-seed", in: arguments(request)) == "1234", "LASErMPNN seed routing failed")
    }

    static func testValidationAndDependencies() {
        var request = proteinRequest()
        request.epitopeResidues = "34 residue-fifty"
        expect(request.hasInvalidEpitopeResidues, "invalid hotspot was not detected")
        expect(!request.isRunnable, "invalid hotspot request remained runnable")
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("invalid-hotspot-\(UUID().uuidString).yaml")
        defer { try? FileManager.default.removeItem(at: url) }
        do {
            try TemplateWriter.write(request, to: url)
            failures.append("invalid hotspot was silently written")
        } catch {}

        request.epitopeResidues = "A34"
        expect(request.hasInvalidEpitopeResidues, "a binder-chain residue was accepted as a target hotspot")

        request = proteinRequest()
        request.epitopeResidues = ""
        request.designPredictor = .alphafold3
        request.postPredictors = []
        expect(!request.isRunnable, "a saved AlphaFold 3 campaign remained runnable after retirement")
        expect(!Predictor.designChoices.contains(.alphafold3), "retired AlphaFold 3 remained in design choices")

        request.designPredictor = .intellifold
        expect(request.isRunnable, "retained IntelliFold PyTorch campaign was rejected")
        expect(request.requiredComponents.contains(.intellifold), "IntelliFold PyTorch dependency missing")

        request = proteinRequest()
        request.targetKind = .ligand
        request.targetSequence = ""
        request.targetSmiles = "CCOC"
        request.ligandIsConjugated = true
        request.ligandAttachmentAtom = 1
        expect(!request.isRunnable, "half-selected iterative linker bond remained runnable")
        request.ligandAttachmentLinkerAtom = 2
        expect(request.isRunnable, "complete iterative linker bond was rejected")
    }

    static func testMultipleCheckersRemainVisible() async throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("multi-check-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        for predictor in ["intellifold", "openfold-3-mlx"] {
            let directory = root.appendingPathComponent("run_001/post_\(predictor)/cycle_05",
                                                        isDirectory: true)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let csv = "run,cycle,iptm,complex_plddt,binder_sequence,structure_path,confidence_json\n1,5,0.80,0.75,AAAA,/tmp/model.cif,/tmp/confidence.json\n"
            try csv.write(to: directory.appendingPathComponent("post_metrics_row.csv"),
                          atomically: true, encoding: .utf8)
        }
        await MainActor.run {
            let watcher = MetricsWatcher()
            watcher.start(root: root, interval: 3600)
            expect(watcher.validationPoints.count == 2, "one of two checker results was discarded")
            expect(Set(watcher.validationPoints.map(\.predictor)) == Set(["intellifold", "openfold-3-mlx"]),
                   "checker identity was not retained")
            watcher.stop()
        }
    }

    static func main() async throws {
        try testBoltzProteinHotspots()
        try testMultimerTargetMapping()
        testPostChecksAndModels()
        testCanonicalCheckers()
        testDesignerSeeds()
        testValidationAndDependencies()
        try await testMultipleCheckersRemainVisible()
        if failures.isEmpty {
            print("PASS iterative command contract")
        } else {
            for failure in failures { fputs("FAIL: \(failure)\n", stderr) }
            exit(1)
        }
    }
}
