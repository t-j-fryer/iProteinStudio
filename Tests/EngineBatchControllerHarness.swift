import Foundation
import Combine

enum IntelliFoldModel: String, Codable, Hashable { case v2flash = "v2-flash", v2 }
enum RunPhase: Equatable { case idle, running, finished, cancelled, failed(String) }
struct Project {
    var id = UUID()
    var name: String
    var slug = "engine-test"
    var request = DesignRequest()
}
struct NHError: LocalizedError {
    var text: String
    var errorDescription: String? { text }
    static func message(_ text: String) -> NHError { NHError(text: text) }
}
enum AppPaths {
    static let fm = FileManager.default
    static let support = fm.temporaryDirectory.appendingPathComponent("engine-controller-\(UUID())")
    static var projects: URL { support.appendingPathComponent("projects") }
    static var pipeline: URL { support.appendingPathComponent("pipeline") }
    static var msaCache: URL { support.appendingPathComponent("msa") }
    static var scaffoldMSACache: URL { support.appendingPathComponent("scaffold") }
    static var boltzCache: URL { support.appendingPathComponent("boltz") }
    static var numbaCache: URL { support.appendingPathComponent("numba") }
    static var intelliFoldCache: URL { support.appendingPathComponent("intelli") }
    static var objectStore: URL { support.appendingPathComponent("objects") }
    static var rfd3Root: URL { support.appendingPathComponent("rfd3") }
    static var parseSequencesScript: URL { support.appendingPathComponent("parse.py") }
    static func stageRFD3Scripts() {}
    static func projectDir(_ project: Project) -> URL { projects.appendingPathComponent(project.slug) }
    static var snapshotCalls = 0
    static var failAt = 0
    static func createPipelineSnapshot(in root: URL) throws -> URL {
        snapshotCalls += 1
        if snapshotCalls == failAt { throw NHError.message("fixture preparation failure") }
        let path = root.appendingPathComponent(".studio_runtime/pipeline")
        try fm.createDirectory(at: path, withIntermediateDirectories: true)
        try Data("inert fixture".utf8).write(to: path.appendingPathComponent("nanohunter_run.sh"))
        return path
    }
}
struct ManagedJob {
    var id = "fixture"
    var project = "engine-test"
    var kind = "desktop_iterative_batch"
    var status = "running"
    var message: String? = "fixture progress"
    var active_output: String?
    var child_outputs: [String]?
    var engine_label: String?
    var engine_index: Int?
    var engine_count: Int?
    var output: URL?
    var pipeline_log_tail: [String]? = []
    var stage: String?
    var isActive: Bool { ["queued", "running", "stopping"].contains(status) }
}
@MainActor final class JobCenter { static let shared = JobCenter(); var jobs: [ManagedJob] = [] }
enum BrokerClient { static func savedJobID(at root: URL) -> String? { nil } }
enum RunResultsLoader { static func iterativeHitThreshold(root: URL) -> Double { 0.7 } }
@MainActor final class ManagedJobSession {
    private(set) var id: String?
    var hasSession: Bool { id != nil }
    static var submissions: [(workflow: String, output: URL)] = []
    static var receiver: ((ManagedJob) -> Void)?
    static var cancelCalls = 0
    static var lastAttachResumed = false
    static var holdSubmission = false
    static var pending: ManagedJobSession?
    func submit(project: String, workflow: String, output: URL, update: @escaping (ManagedJob) -> Void, failure: @escaping (String) -> Void) {
        Self.submissions.append((workflow, output)); Self.receiver = update
        if Self.holdSubmission { Self.pending = self }
        else { id = "fixture-\(Self.submissions.count)" }
    }
    func attach(id: String, resume: Bool = false, update: @escaping (ManagedJob) -> Void, failure: @escaping (String) -> Void) { self.id = id; Self.receiver = update; Self.lastAttachResumed = resume }
    func cancel() { Self.cancelCalls += 1 }
    func detach() { id = nil; Self.receiver = nil }
    static func completeSubmission() { pending?.id = "pending-fixture"; pending = nil; holdSubmission = false }
}

@main struct EngineBatchControllerHarness {
    @MainActor static func main() throws {
        defer { try? AppPaths.fm.removeItem(at: AppPaths.support) }
        var project = Project(name: "Engine fixture")
        project.request.designType = .minibinder
        project.request.targetSequence = "ACDEFGHIKLMN"
        project.request.designer = .solublempnn
        project.request.designEngines = [.intellifoldFlash, .intellifoldFull, .openfold3]
        project.request.postPredictors = [.boltz, .intellifold]
        project.request.numDesigns = 12
        let controller = RunController()
        controller.start(project: project)
        precondition(controller.isRunning)
        precondition(ManagedJobSession.submissions.count == 1)
        let submission = ManagedJobSession.submissions[0]
        precondition(submission.workflow == "iterative_batch")
        let data = try Data(contentsOf: submission.output.appendingPathComponent("studio_engine_batch.json"))
        let descriptor = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        let paths = descriptor["campaigns"] as! [String]
        precondition(paths.count == 3 && Set(paths).count == 3 && descriptor["trajectoriesPerEngine"] as? Int == 12)
        var seeds = Set<String>()
        for (index, path) in paths.enumerated() {
            let root = URL(fileURLWithPath: path)
            let manifest = try JSONDecoder().decode(StudioRunManifest.self, from: Data(contentsOf: root.appendingPathComponent("studio_run.json")))
            let metadata = try JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("studio_run.json"))) as! [String: Any]
            let active = metadata["request"] as! [String: Any]
            let form = metadata["savedFormState"] as! [String: Any]
            precondition(metadata["version"] as? Int == 2)
            precondition(active["designType"] as? String == "minibinder")
            for key in ["scaffoldID", "scaffoldSequence", "cdrs", "betaBiasStrength", "betaPatternStrength", "secondaryStructureBiasScope"] {
                precondition(active[key] == nil && form[key] != nil)
            }
            var legacy = metadata
            legacy["version"] = 1; legacy["request"] = form; legacy.removeValue(forKey: "savedFormState")
            let legacyManifest = try JSONDecoder().decode(StudioRunManifest.self, from: JSONSerialization.data(withJSONObject: legacy))
            precondition(legacyManifest.request == manifest.request)
            precondition(manifest.engineBatchRoot == submission.output.path)
            let engine = project.request.selectedDesignEngines[index]
            precondition(manifest.request?.selectedDesignEngines == [engine])
            precondition(manifest.arguments[manifest.arguments.firstIndex(of: "--predictor")! + 1] == engine.predictor.runnerValue)
            if let model = engine.model {
                precondition(manifest.arguments[manifest.arguments.firstIndex(of: "--model")! + 1] == model.rawValue)
            }
            precondition(manifest.requestedTrajectories == 12)
            precondition(manifest.arguments[manifest.arguments.firstIndex(of: "--num-runs")! + 1] == "12")
            let template = manifest.arguments[manifest.arguments.firstIndex(of: "--template-yaml")! + 1]
            precondition(AppPaths.fm.fileExists(atPath: template))
            seeds.insert(manifest.arguments[manifest.arguments.firstIndex(of: "--binder-random-seed")! + 1])
        }
        precondition(seeds.count == 1)
        ManagedJobSession.receiver?(ManagedJob(active_output: paths[1], engine_label: "IntelliFold", engine_index: 2, engine_count: 3))
        precondition(controller.campaignRoot?.path == paths[1])
        precondition(controller.projectContext?.request.designPredictor == .intellifold)
        precondition(controller.projectContext?.request.intellifoldModel == .v2)
        precondition(controller.currentMessage.contains("2/3"))
        // Seven frameworks share one total per engine, with exact saved sequences.
        ManagedJobSession.submissions = []
        var nanobody = project
        nanobody.request.designType = .nanobody
        nanobody.request.designer = .proteinmpnn
        nanobody.request.numDesigns = 70
        nanobody.request.scaffoldSelections = (0..<7).map { i in
            .init(id: "framework\(i)", name: "Framework \(i)",
                  sequence: "EVQLVESGGGLVQPGGSLRLSCAASGSVFKINVMAWYRQAPGKGRELVAGIISGGSTSYADSVKGRFTISRDNAKNTLYLQMNSLRPEDTAVYYCAFITTESDYDLGRRYWGQGTLVTVSS",
                  trajectories: 1)
        }
        precondition(nanobody.request.allocatedScaffolds.map(\.trajectories) == Array(repeating: 10, count: 7))
        nanobody.request.numDesigns = 72
        precondition(nanobody.request.allocatedScaffolds.map(\.trajectories) == [11, 11, 10, 10, 10, 10, 10])
        nanobody.request.numDesigns = 70
        nanobody.request.setEqualScaffoldBudgets(false)
        nanobody.request.setScaffoldBudget(id: "framework0", trajectories: 15)
        nanobody.request.setScaffoldBudget(id: "framework1", trajectories: 5)
        precondition(nanobody.request.numDesigns == 70 && nanobody.request.totalTrajectories == 210)
        nanobody.request.reconcileDesigner()
        nanobody.request.reconcilePredictors()
        let roundTrip = try JSONDecoder().decode(DesignRequest.self, from: JSONEncoder().encode(nanobody.request))
        precondition(roundTrip == nanobody.request)
        var legacyRequest = nanobody.request.forScaffold(nanobody.request.allocatedScaffolds[0])
        precondition(legacyRequest.allocatedScaffolds.count == 1 && legacyRequest.allocatedScaffolds[0].trajectories == 15)
        legacyRequest.scaffoldSelections = []
        precondition(!legacyRequest.isRunnable)
        precondition(legacyRequest.totalTrajectories == 0)
        let scaffoldController = RunController(); scaffoldController.start(project: nanobody)
        precondition(scaffoldController.isRunning && ManagedJobSession.submissions.count == 1)
        let scaffoldSubmission = ManagedJobSession.submissions[0]
        let scaffoldDescriptor = try JSONSerialization.jsonObject(with: Data(contentsOf:
            scaffoldSubmission.output.appendingPathComponent("studio_engine_batch.json"))) as! [String: Any]
        precondition(scaffoldDescriptor["version"] as? Int == 2)
        let scaffoldPaths = scaffoldDescriptor["campaigns"] as! [String]
        precondition(scaffoldPaths.count == 21 && Set(scaffoldPaths).count == 21)
        precondition(scaffoldDescriptor["campaignBudgets"] as? [Int] == Array(repeating: [15, 5, 10, 10, 10, 10, 10], count: 3).flatMap { $0 })
        for (index, path) in scaffoldPaths.enumerated() {
            let manifest = try JSONDecoder().decode(StudioRunManifest.self,
                from: Data(contentsOf: URL(fileURLWithPath: path).appendingPathComponent("studio_run.json")))
            let selected = nanobody.request.allocatedScaffolds[index % 7]
            precondition(manifest.request?.scaffoldID == selected.id)
            precondition(manifest.request?.scaffoldSequence == selected.sequence)
            precondition(manifest.request?.scaffoldSelections == nil)
            precondition(manifest.requestedTrajectories == selected.trajectories)
            precondition(manifest.arguments[manifest.arguments.firstIndex(of: "--num-runs")! + 1] == String(selected.trajectories))
            let template = manifest.arguments[manifest.arguments.firstIndex(of: "--template-yaml")! + 1]
            let yaml = try String(contentsOfFile: template, encoding: .utf8)
            precondition(yaml.contains(selected.sequence))
        }
        var selection = nanobody.request
        selection.setScaffold(id: "framework0", name: "", sequence: "", selected: false)
        precondition(selection.numDesigns == 55 && selection.allocatedScaffolds[0].trajectories == 5)
        selection.scaffoldSelections![0].trajectories = 0
        precondition(!selection.isRunnable)
        print("PASS scaffold equal/custom budgets, round-trip, exclusions and 21 engine/scaffold campaign manifests")
        // Typing updates the request before Start, without Return/focus loss.
        var perFramework = nanobody.request
        perFramework.setFrameworkBudgetMode(.perFramework)
        var valid = NumericInputValue.apply("100", in: 1...10_000) { perFramework.setTrajectoriesPerScaffold($0) }
        precondition(valid && perFramework.numDesigns == 700)
        precondition(perFramework.campaignRequests.allSatisfy { $0.request.numDesigns == 100 && $0.request.trajectoriesPerScaffold == nil })
        for invalid in ["", "abc", "0", "10001", "999999999999999999999999"] {
            valid = NumericInputValue.apply(invalid, in: 1...10_000) { perFramework.setTrajectoriesPerScaffold($0) }
            precondition(!valid && perFramework.numDesigns == 700)
        }
        perFramework.setScaffold(id: "eighth", name: "Eighth", sequence: perFramework.allocatedScaffolds[0].sequence, selected: true)
        precondition(perFramework.numDesigns == 800 && perFramework.allocatedScaffolds.allSatisfy { $0.trajectories == 100 })
        let restoredBudget = try JSONDecoder().decode(DesignRequest.self, from: JSONEncoder().encode(perFramework))
        precondition(restoredBudget == perFramework && restoredBudget.frameworkBudgetMode == .perFramework)
        perFramework.setFrameworkBudgetMode(.custom)
        perFramework.setScaffoldBudget(id: "eighth", trajectories: 50)
        precondition(perFramework.numDesigns == 750 && perFramework.trajectoriesPerScaffold == nil)
        perFramework.setFrameworkBudgetMode(.total)
        precondition(perFramework.numDesigns == 750 && perFramework.allocatedScaffolds.reduce(0) { $0 + $1.trajectories } == 750)
        precondition(scaffoldController.resultsRoot == scaffoldSubmission.output)
        let batchRecord = StudioRunRecord(projectID: nanobody.id, projectName: nanobody.name,
            workflow: .iterative, name: "Combined", root: scaffoldSubmission.output, date: Date(),
            state: .stopped, detail: "", manifestURL: nil, managedJobID: "batch-fixture", hasViewableResults: true)
        let resumedBatch = RunController(); resumedBatch.resume(batchRecord)
        precondition(resumedBatch.isRunning && resumedBatch.resultsRoot == scaffoldSubmission.output)
        precondition(ManagedJobSession.lastAttachResumed && resumedBatch.observedJobID == "batch-fixture")

        print("PASS immediate numeric edits, invalid submission gates, per-framework mode, selection changes, round-trip and batch result root")
        // Starting another workspace detaches only the dashboard, not its job.
        ManagedJobSession.submissions = []
        let queuedController = RunController()
        queuedController.start(project: project, name: "  Trial α / first  ")
        let firstSubmission = ManagedJobSession.submissions[0]
        let firstBytes = try Data(contentsOf: firstSubmission.output.appendingPathComponent("studio_engine_batch.json"))
        let firstID = queuedController.observedJobID!
        var secondProject = project
        secondProject.id = UUID(); secondProject.slug = "second-workspace"
        queuedController.start(project: secondProject, name: "Trial α / first")
        precondition(ManagedJobSession.submissions.count == 2)
        precondition(queuedController.projectID == secondProject.id && ManagedJobSession.cancelCalls == 0)
        precondition(firstSubmission.output != ManagedJobSession.submissions[1].output)
        precondition(RunNaming.read(at: firstSubmission.output, fallback: "missing") == "Trial α / first")
        precondition(RunNaming.read(at: ManagedJobSession.submissions[1].output, fallback: "missing") == "Trial α / first")
        precondition(RunNaming.normalized("  line one\nline two  ") == "line one line two")
        precondition(RunNaming.normalized(String(repeating: "a", count: 150)).count == 120)
        let unchangedBytes = try Data(contentsOf: firstSubmission.output.appendingPathComponent("studio_engine_batch.json"))
        precondition(unchangedBytes == firstBytes)
        precondition(queuedController.prepareNewRun() && queuedController.campaignRoot == nil)
        queuedController.inspect(ManagedJob(id: firstID, output: firstSubmission.output), project: project)
        precondition(queuedController.observedJobID == firstID && queuedController.projectID == project.id)
        precondition(ManagedJobSession.submissions.count == 2 && ManagedJobSession.cancelCalls == 0)
        // A double click during submission cannot detach a not-yet-saved job.
        ManagedJobSession.holdSubmission = true
        let pending = RunController(); pending.start(project: project)
        let pendingCount = ManagedJobSession.submissions.count
        precondition(!pending.canStartAnother && !pending.prepareNewRun())
        pending.start(project: secondProject)
        precondition(ManagedJobSession.submissions.count == pendingCount && pending.projectID == project.id)
        ManagedJobSession.completeSubmission()
        precondition(pending.canStartAnother && pending.prepareNewRun())
        print("PASS queue submission across workspaces, independent manifests, observation switching and submission guard")
        // Every tab can leave an observed durable job and reopen it without a
        // broker cancellation or another submission. No engine is launched.
        let beforeSwitches = ManagedJobSession.submissions.count
        let fixtureRoot = AppPaths.projects.appendingPathComponent("queue-fixture/runs/first")
        let secondRoot = AppPaths.projects.appendingPathComponent("other-fixture/runs/second")
        let nise = NISEController()
        nise.reattach(root: fixtureRoot, jobID: "nise-first")
        precondition(nise.isRunning && nise.canStartAnother)
        precondition(nise.prepareNewRun() && nise.outputRoot == nil && nise.phase == .idle)
        nise.reattach(root: secondRoot, jobID: "nise-second")
        precondition(nise.observedJobID == "nise-second" && nise.projectSlug == "other-fixture")
        let predict = PredictionController()
        predict.reattach(root: fixtureRoot, jobID: "predict-first")
        precondition(predict.isRunning && predict.canStartAnother)
        precondition(predict.prepareNewRun() && predict.outputRoot == nil && predict.phase == .idle)
        predict.reattach(root: secondRoot, jobID: "predict-second")
        precondition(predict.observedJobID == "predict-second" && predict.projectSlug == "other-fixture")
        let rfd3 = RFD3Controller()
        rfd3.reattach(root: fixtureRoot, jobID: "rfd3-first")
        precondition(rfd3.isRunning && rfd3.canStartAnother)
        precondition(rfd3.prepareNewRun() && rfd3.campaignRoot == nil && rfd3.phase == .idle)
        rfd3.reattach(root: secondRoot, jobID: "rfd3-second")
        precondition(rfd3.observedJobID == "rfd3-second" && rfd3.projectSlug == "other-fixture")
        precondition(ManagedJobSession.submissions.count == beforeSwitches && ManagedJobSession.cancelCalls == 0)
        // Without a durable ID, a pending submission (or old unmanaged RFD3
        // process) must remain attached until it can be safely observed later.
        let pendingNISE = NISEController(); pendingNISE.phase = .running
        let pendingPredict = PredictionController(); pendingPredict.phase = .running
        let pendingRFD3 = RFD3Controller(); pendingRFD3.phase = .running
        precondition(!pendingNISE.prepareNewRun() && !pendingNISE.canStartAnother)
        precondition(!pendingPredict.prepareNewRun() && !pendingPredict.canStartAnother)
        precondition(!pendingRFD3.prepareNewRun() && !pendingRFD3.canStartAnother)
        print("PASS NISE, Predict and RFdiffusion3 queue observation, workspace switching and pending-job guards")
        // A preparation failure in a later engine must submit nothing.
        ManagedJobSession.submissions = []
        AppPaths.failAt = AppPaths.snapshotCalls + 2
        let failed = RunController(); failed.start(project: project)
        precondition(!failed.isRunning && ManagedJobSession.submissions.isEmpty)
        print("PASS native engine-batch preparation, saved launch records, progress routing and all-before-submit failure")
    }
}
