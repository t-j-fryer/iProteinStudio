import Foundation

// RunResult.swift supplies the shared header-aware CSV reader used by the live
// metrics watcher. The production workflow enum lives in RunHistoryStore; this
// narrow harness defines only the surface needed by the loader.
enum StudioWorkflow: String, Codable {
    case iterative, nise, rfdiffusion3, prediction
    var label: String { rawValue }
}

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

    static func testTargetTemplateModes() throws {
        let pdb = FileManager.default.temporaryDirectory
            .appendingPathComponent("target-template-\(UUID().uuidString).pdb")
        try "END\n".write(to: pdb, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: pdb) }

        var request = proteinRequest()
        request.epitopeResidues = ""
        request.targetTemplatePath = pdb.path
        request.targetTemplateMode = .guide
        expect(request.isRunnable, "Boltz guide template was rejected")
        var args = arguments(request)
        expect(value(after: "--target-template", in: args) == pdb.path,
               "target template path was not emitted")
        expect(value(after: "--target-template-mode", in: args) == "guide",
               "ordinary guide mode was not emitted")
        expect(!args.contains("--target-template-threshold"),
               "guide mode emitted an irrelevant force threshold")

        request.targetTemplateMode = .strong
        request.targetTemplateThreshold = 1.75
        expect(!request.isRunnable, "unsafe Boltz strong target restraint was accepted")
        expect(request.targetTemplateCompatibilityError?.contains("broken target geometry") == true,
               "disabled strong target restraint did not explain its acceptance failure")

        request.designPredictor = .protenixV2
        request.targetTemplateMode = .guide
        expect(request.isRunnable, "Protenix v2 guide template was rejected")
        request.targetTemplateMode = .strong
        expect(!request.isRunnable, "Protenix v2 accepted Boltz-only strong restraint")
        request.targetTemplateMode = .guide
        request.designPredictor = .intellifold
        expect(request.isRunnable, "IntelliFold v2 guide template was rejected")
        args = arguments(request)
        expect(value(after: "--target-template-mode", in: args) == "guide",
               "IntelliFold guide mode was not emitted")
        request.targetTemplateMode = .strong
        expect(!request.isRunnable, "IntelliFold accepted Boltz-only strong restraint")
    }

    static func testProtenixConstraintPocket() throws {
        var request = proteinRequest()
        request.designPredictor = .protenixConstraint
        request.postPredictors = [.protenixConstraint, .boltz]
        request.reconcilePredictors()
        expect(request.hasEpitopeSteering, "constraint engine did not activate the selected epitope")
        expect(request.effectivePostPredictors == [.boltz], "guided constraint checkpoint was accepted as a post-checker")
        expect(request.requiredComponents.contains(.protenixConstraint), "constraint runtime dependency was omitted")
        let args = arguments(request)
        expect(value(after: "--predictor", in: args) == "protenix-constraint-v0.5",
               "constraint campaign was routed to the wrong runner identity")
        expect(!args.contains("--boltz-use-potentials"), "constraint campaign leaked Boltz steering flags")

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("protenix-pocket-\(UUID().uuidString).yaml")
        defer { try? FileManager.default.removeItem(at: url) }
        try TemplateWriter.write(request, to: url)
        let yaml = try String(contentsOf: url, encoding: .utf8)
        expect(yaml.contains("target_epitope_residues:") && yaml.contains("- B34"),
               "constraint pocket residues were not written")
        expect(yaml.contains("protenix_pocket_max_distance: 8.0"),
               "constraint pocket distance was not explicit")
        expect(!yaml.contains("boltz_contact_"), "constraint template leaked Boltz contact controls")

        request.targetKind = .ligand
        request.targetSequence = ""
        request.targetSmiles = "CCO"
        expect(!request.isRunnable, "protein-only constraint checkpoint accepted a ligand campaign")
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
        expect(!args.contains("--post-include-cycle00"), "all-cycle checking incorrectly included unoptimized cycle 00")
        request.postOnlyHits = true
        args = arguments(request)
        expect(value(after: "--post-mode", in: args) == "iptm", "hit-gated all-cycle checking was not emitted")
        expect(!args.contains("--post-include-cycle00"), "hit-gated all-cycle checking incorrectly included unoptimized cycle 00")
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
        expect(request.designPredictor == .intellifold, "a saved hotspot silently replaced the selected design engine")
        expect(request.effectivePostPredictors == [.boltz], "independent Boltz checking was lost")
        expect(!request.hasEpitopeSteering, "non-Boltz design incorrectly claimed to apply epitope steering")
        expect(request.hasEnteredEpitopeResidues, "dormant hotspot selection was discarded")
        expect(request.isRunnable, "non-Boltz full-target design was blocked by a dormant hotspot selection")
        expect(!arguments(request).contains("--boltz-use-potentials"), "dormant hotspots enabled Boltz potentials")

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

    static func testSecondaryStructureControls() throws {
        var request = proteinRequest()
        request.epitopeResidues = ""
        for strength in [0.0, 0.5, 1.0] {
            request.helixKill = strength
            let args = arguments(request)
            expect(value(after: "--negative-helix-constant", in: args) == String(format: "%.2f", strength),
                   "initialization helix strength was not emitted")
            expect(!args.contains("--secondary-bias") && !args.contains("--secondary-bias-scope"),
                   "retired controls were emitted")
        }
        request.helixKill = .nan
        expect(!request.secondaryStructureControlsValid, "NaN helix strength accepted")
        request.helixKill = 0.5
        request.secondaryStructureBias = .beta
        expect(!request.isRunnable, "retired saved beta configuration was silently changed")
        request.secondaryStructureBias = .antihelix
        request.secondaryStructureBiasScope = .seedAndCycles
        expect(!request.isRunnable, "saved sustained bias was silently changed")
        request.secondaryStructureBiasScope = .seedOnly
        expect(request.secondaryStructureCompatibilityError == nil, "initialization-only setting rejected")
        let restored = try JSONDecoder().decode(DesignRequest.self, from: JSONEncoder().encode(request))
        expect(restored.helixKill == 0.5, "helix strength did not survive saving")
    }

    static func testOptimizedSchedulerPolicy() throws {
        var request = proteinRequest()
        request.epitopeResidues = ""
        expect(request.speedMode == .batched, "new campaigns did not default to optimized scheduling")

        let residentEngines: [Predictor] = [
            .boltz, .boltzPotentials, .intellifold,
            .protenixMini, .protenixConstraint,
        ]
        for engine in residentEngines {
            request.designPredictor = engine
            let args = arguments(request)
            expect(value(after: "--design-scheduler", in: args) == "resident",
                   "\(engine.label) did not select campaign residency")
            expect(value(after: "--wave-batch-size", in: args) == "all",
                   "\(engine.label) resident worker did not own the complete wave")
            expect(value(after: "--max-parallel", in: args) == "1",
                   "\(engine.label) resident worker did not enforce one GPU owner")
        }

        request.designPredictor = .protenixV2
        var args = arguments(request)
        expect(value(after: "--design-scheduler", in: args) == "cycle-wave",
               "full Protenix v2 did not select the measured cycle-wave policy")
        expect(!args.contains("resident"), "full Protenix v2 incorrectly selected residency")
        expect(!args.contains("--wave-batch-size"),
               "full Protenix v2 hard-coded an unvalidated wave size")

        request.speedMode = .standard
        args = arguments(request)
        expect(value(after: "--design-scheduler", in: args) == "cycle-wave",
               "legacy GUI scheduling value bypassed Protenix v2's optimized policy")

        for designType in [DesignType.minibinder, .nanobody] {
            request.designType = designType
            request.designPredictor = .openfold3
            for mode in [SpeedMode.standard, .batched] {
                request.speedMode = mode
                args = arguments(request)
                expect(value(after: "--design-scheduler", in: args) == "run",
                       "OpenFold-3 selected an unsupported resident worker")
                expect(value(after: "--max-parallel", in: args) == "1",
                       "OpenFold-3 lost the single GPU owner policy")
                expect(!args.contains("--wave-batch-size"), "OpenFold-3 received resident wave settings")
            }
        }

        request = proteinRequest()
        request.speedMode = .standard
        let legacyData = try JSONEncoder().encode(request)
        let migrated = try JSONDecoder().decode(DesignRequest.self, from: legacyData)
        expect(migrated.speedMode == .batched,
               "saved Compatibility project was not migrated to optimized scheduling")
        expect(value(after: "--design-scheduler", in: arguments(migrated)) == "resident",
               "migrated saved project did not launch a resident worker")
    }

    static func testExplicitDesignCheckpoints() throws {
        var request = proteinRequest()
        request.epitopeResidues = ""
        request.numDesigns = 12
        request.designEngines = [.intellifoldFlash, .intellifoldFull, .openfold3]
        request.postPredictors = [.intellifold, .boltz]
        request.intellifoldModel = .v2
        expect(DesignEngine.choices.contains(.openfold3), "OpenFold-3 was omitted from design choices")
        expect(request.totalTrajectories == 36, "two IntelliFold checkpoints collapsed into one campaign")
        expect(request.requiredComponents.contains(.intellifoldFull) && request.requiredComponents.contains(.intellifold)
               && request.requiredComponents.contains(.openfold3), "explicit checkpoint dependencies were missing")
        expect(request.usesFullIntelliFold, "full model did not suppress the Flash-based time estimate")
        for engine in request.selectedDesignEngines {
            let child = request.forDesignEngine(engine)
            let args = arguments(child)
            expect(value(after: "--num-runs", in: args) == "12", "checkpoint did not receive the full budget")
            expect(value(after: "--predictor", in: args) == engine.predictor.runnerValue, "checkpoint backend changed")
            expect(value(after: "--design-scheduler", in: args) == (engine == .openfold3 ? "run" : "resident"),
                   "checkpoint selected an unsupported scheduler")
            if let model = engine.model {
                expect(value(after: "--model", in: args) == model.rawValue, "wrong IntelliFold checkpoint selected")
                expect(!child.effectivePostPredictors.contains(.intellifold), "Flash/Full were treated as independent checkers")
            } else {
                expect(value(after: "--model", in: args) == "v2", "independent checker model was changed by design selection")
            }
        }
        let restored = try JSONDecoder().decode(DesignRequest.self, from: JSONEncoder().encode(request))
        expect(restored.selectedDesignEngines == request.selectedDesignEngines, "Flash/Full selections did not survive saving")
        request.setDesignEngine(.intellifoldFull, selected: false)
        expect(request.selectedDesignEngines == [.intellifoldFlash, .openfold3], "removing Full removed Flash or changed the checkpoint")
        request = proteinRequest()
        request.designPredictor = .intellifold
        request.intellifoldModel = .v2
        let old = try JSONDecoder().decode(DesignRequest.self, from: JSONEncoder().encode(request))
        expect(old.selectedDesignEngines == [.intellifoldFull], "legacy full-v2 workspace silently migrated to Flash")
        request.designPredictors = [.boltz, .intellifold]
        expect(request.selectedDesignEngines == [.boltz, .intellifoldFull], "build-25 checklist lost its full-v2 choice")
        request.designEngines = [.intellifoldFlash]
        request.postPredictors = []
        expect(!request.usesFullIntelliFold && !request.requiredComponents.contains(.intellifoldFull),
               "a stale checking model overrode explicit Flash selection")
    }

    static func testDesignEngineChecklist() throws {
        var request = proteinRequest()
        request.epitopeResidues = ""
        request.numDesigns = 12
        request.numCycles = 5
        let legacy = try JSONDecoder().decode(DesignRequest.self, from: JSONEncoder().encode(request))
        expect(legacy.selectedDesignPredictors == [.boltz], "legacy single-engine selection changed")
        request.designPredictors = [.boltz, .intellifold, .protenixV2]
        request.postPredictors = [.boltz, .intellifold]
        expect(request.isRunnable, "valid engine checklist was rejected")
        expect(request.totalTrajectories == 36 && request.expectedOptimizedDesigns == 180,
               "trajectory budget was divided between engines")
        expect(request.expectedStartingStructures == 36, "starting structure total omitted an engine")
        expect(request.requiredComponents.contains(.protenixV2) && request.requiredComponents.contains(.intellifold),
               "installation requirements omitted selected engines")
        var expectedSeconds = 0.0
        for engine in request.selectedDesignPredictors {
            let child = request.forDesignEngine(engine)
            let args = arguments(child)
            expect(child.selectedDesignPredictors == [engine], "child retained the parent checklist")
            expect(value(after: "--num-runs", in: args) == "12", "an engine received a partial trajectory budget")
            expect(value(after: "--num-opt-cycles", in: args) == "5", "cycle settings changed per engine")
            expect(value(after: "--predictor", in: args) == engine.runnerValue, "engine routing was wrong")
            expect(value(after: "--design-scheduler", in: args) == (engine == .protenixV2 ? "cycle-wave" : "resident"),
                   "engine batch changed the measured scheduling policy")
            expect(!child.effectivePostPredictors.contains { $0.independenceIdentity == engine.independenceIdentity },
                   "design engine was counted as its own independent checker")
            expectedSeconds += child.estimatedPredictionSeconds
        }
        expect(request.estimatedPredictionSeconds == expectedSeconds, "estimate did not sum all engine campaigns")
        let restored = try JSONDecoder().decode(DesignRequest.self, from: JSONEncoder().encode(request))
        expect(restored.selectedDesignPredictors == request.selectedDesignPredictors, "checklist did not persist")
        request.designPredictors = []
        expect(!request.isRunnable && request.totalTrajectories == 0, "empty checklist silently fell back to one engine")
        request.designPredictors = [.boltz, .boltz]
        expect(request.totalTrajectories == 12, "duplicate saved engine multiplied the budget")
        request.designPredictors = [.boltz, .alphafold3]
        expect(!request.isRunnable, "retired selected engine was silently dropped")
        request.designPredictors = [.boltz, .intellifold]
        request.targetKind = .ligand
        request.targetSmiles = "CCOC"
        request.ligandContactAtoms = ["C1"]
        request.ligandAtomsGeneratedFor = request.ligandAtomKey
        expect(!request.isRunnable, "incompatible targeting was checked only for the first engine")
    }

    static func testRequestedTrajectoryBudgetIsExact() {
        var request = proteinRequest()
        request.numDesigns = 37
        request.numCycles = 7
        let args = arguments(request)
        expect(value(after: "--num-runs", in: args) == "37",
               "GUI trajectory count reverted to a runner default")
        expect(value(after: "--num-opt-cycles", in: args) == "7",
               "GUI cycle count reverted to a runner default")
        expect(request.expectedOptimizedDesigns == 259,
               "optimized design budget incorrectly included cycle 00")
        expect(request.expectedStartingStructures == 37,
               "starting-structure budget did not match trajectories")
    }

    static func testExplicitResumeContract() {
        let recorded = ["--predictor", "boltz", "--num-runs", "4"]
        let resumed = ResumeContract.arguments(from: recorded)
        expect(resumed.filter { $0 == "--resume" }.count == 1,
               "explicit Resume did not add exactly one checkpoint flag")
        expect(Array(resumed.dropLast()) == recorded,
               "explicit Resume changed recorded scientific settings")
        let repeated = ResumeContract.arguments(from: resumed + ["--resume"])
        expect(repeated.filter { $0 == "--resume" }.count == 1,
               "repeated Resume accumulated duplicate flags")
    }

    static func testDormantHotspotsAreNotPassed() throws {
        var request = proteinRequest()
        request.designPredictor = .intellifold
        request.postPredictors = [.boltz]
        request.reconcilePredictors()
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("dormant-hotspot-\(UUID().uuidString).yaml")
        defer { try? FileManager.default.removeItem(at: url) }
        try TemplateWriter.write(request, to: url)
        let yaml = try String(contentsOf: url, encoding: .utf8)
        expect(!yaml.contains("target_epitope_residues"),
               "a non-Boltz campaign passed an unsupported epitope restraint")
        expect(value(after: "--predictor", in: arguments(request)) == "intellifold",
               "non-Boltz campaign was not routed to its selected engine")
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
            let verdict = predictor == "intellifold" ? "True" : "False"
            let csv = "run,cycle,predictor,iptm,ipsae_min,complex_plddt,binder_plddt,complex_rmsd,binder_backbone_rmsd,binder_rmsd,binder_sequence,structure_path,confidence_json,binder_structure_path,binder_confidence_json,is_hit,failed_filters\n1,5,\(predictor),0.80,0.72,0.75,0.88,1.2,0.7,1.1,AAAA,/tmp/model.cif,/tmp/confidence.json,/tmp/binder.cif,/tmp/binder-confidence.json,\(verdict),\(verdict == "True" ? "" : "maximum_complex_rmsd")\n"
            try csv.write(to: directory.appendingPathComponent("post_metrics_row.csv"),
                          atomically: true, encoding: .utf8)
        }
        let watcher = await MainActor.run {
            let watcher = MetricsWatcher()
            watcher.start(root: root, interval: 3600)
            return watcher
        }
        await watcher.waitForRefresh()
        await MainActor.run {
            expect(watcher.validationPoints.count == 2, "one of two checker results was discarded")
            expect(Set(watcher.validationPoints.map(\.predictor)) == Set(["intellifold", "openfold-3-mlx"]),
                   "checker identity was not retained")
            expect(watcher.validationPoints.filter { $0.isHit(threshold: 0.70) }.count == 1,
                   "live dashboard did not use the saved multi-filter verdict")
            watcher.stop()
        }
    }

    static func testLigandNessoOptions() throws {
        var request = DesignRequest()
        request.designEngines = nil
        request.designPredictors = nil
        request.targetKind = .ligand
        request.targetSmiles = "CCO"
        request.nesso.enabled = true
        request.nesso.predictor = .intellifold
        request.nesso.intellifoldModel = .v2
        expect(request.requiredComponents.contains(.nesso), "ligand screen needs NESSO")
        expect(request.requiredComponents.contains(.intellifoldFull), "shortlist full IntelliFold needs exact weights")
        let restored = try JSONDecoder().decode(DesignRequest.self, from: JSONEncoder().encode(request))
        expect(restored.nesso == request.nesso, "NESSO options must round-trip")
        request.targetKind = .protein
        expect(!request.requiredComponents.contains(.nesso), "protein target leaves NESSO dormant")
        var rfd = RFD3Request()
        rfd.targetKind = .smallMolecule
        rfd.nesso = restored.nesso
        expect(rfd.requiredComponents.contains(.nesso) && rfd.requiredComponents.contains(.intellifoldFull), "RFD3 uses shared shortlist dependencies")
        expect(!rfd.requiredComponents.contains(.boltz), "NESSO/IntelliFold route does not require Boltz")
        rfd.nesso.topK = 0
        expect(rfd.validationIssues.contains { $0.contains("advance from NESSO") }, "invalid shortlist blocks run")
        let old = try JSONDecoder().decode(DesignRequest.self, from: Data("{}".utf8))
        expect(!old.nesso.enabled, "old projects must not opt in silently")
    }

    static func main() async throws {
        try testLigandNessoOptions()
        try testBoltzProteinHotspots()
        try testTargetTemplateModes()
        try testProtenixConstraintPocket()
        try testMultimerTargetMapping()
        testPostChecksAndModels()
        testCanonicalCheckers()
        testDesignerSeeds()
        try testSecondaryStructureControls()
        try testOptimizedSchedulerPolicy()
        try testExplicitDesignCheckpoints()
        try testDesignEngineChecklist()
        testRequestedTrajectoryBudgetIsExact()
        testExplicitResumeContract()
        try testDormantHotspotsAreNotPassed()
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
