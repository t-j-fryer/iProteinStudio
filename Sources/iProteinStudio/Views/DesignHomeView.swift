import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct SaveDesignWorkflowSheet: View {
    @EnvironmentObject var app: AppState
    @Environment(\.dismiss) private var dismiss
    @Binding var name: String
    let save: () -> Bool
    @State private var failed = false
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Save workflow").font(.title2.bold())
            TextField("Button name", text: $name).textFieldStyle(.roundedBorder)
            Text("Saves the current settings and input references. Open the button from Design home to review them before starting.").font(.callout).foregroundStyle(.secondary)
            if failed { Text(app.storageMessage ?? "The workflow could not be saved.").foregroundStyle(.red) }
            HStack {
                Button("Cancel", role: .cancel) { dismiss() }
                Spacer()
                Button("Save button") { if save() { dismiss() } else { failed = true } }
                    .buttonStyle(.borderedProminent).disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }.padding(24).frame(width: 450)
    }
}

struct DesignHomeView: View {
    @EnvironmentObject var app: AppState
    let project: Project
    @ObservedObject var installer: PipelineInstaller
    let onSelect: (WorkspaceMode) -> Void
    @State private var recommended: Recommendation?
    @State private var custom: DesignIntention?

    struct Recommendation: Identifiable {
        let intention: DesignIntention
        let hard: Bool
        var id: String { intention.rawValue + (hard ? "hard" : "easy") }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                HStack(spacing: 16) {
                    StudioArtwork(name: "design-object").frame(width: 68, height: 68)
                    VStack(alignment: .leading, spacing: 5) {
                        Text("What would you like to design?").font(.largeTitle.weight(.semibold))
                        Text("Start with a recommended workflow, or build your own.").foregroundStyle(.secondary)
                    }
                }
                Text("Recommended workflows").font(.title2.weight(.semibold))
                ForEach([DesignIntention.minibinder, .nanobody, .smallMolecule]) { intention in
                    HStack(spacing: 18) {
                        StudioArtwork(name: intention.artwork).frame(width: 88, height: 88)
                        VStack(alignment: .leading, spacing: 8) {
                            Text(intention.label).font(.title3.weight(.semibold))
                            Text(intention == .smallMolecule
                                 ? "RFD4 → Boltz binding probability + ligand confidence"
                                 : "RFD4 → ESMFold2 Full").font(.callout).foregroundStyle(.secondary)
                            HStack {
                                Button("Easy target") { recommended = .init(intention: intention, hard: false) }
                                    .accessibilityLabel("\(intention.label) · easy target")
                                    .accessibilityIdentifier("recommended-\(intention.rawValue)-easy")
                                Button("Hard target · 7-cycle beam") { recommended = .init(intention: intention, hard: true) }
                                    .accessibilityLabel("\(intention.label) · hard target · seven-cycle beam")
                                    .accessibilityIdentifier("recommended-\(intention.rawValue)-hard")
                            }.buttonStyle(.bordered)
                        }
                        Spacer(minLength: 0)
                    }.padding(18).frame(maxWidth: .infinity, alignment: .leading).modifier(StudioSurface())
                }
                if !app.savedWorkflows.isEmpty {
                    Text("Your workflows").font(.title2.weight(.semibold))
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 240))], spacing: 12) {
                        ForEach(app.savedWorkflows) { workflow in
                            Button {
                                if app.openWorkflow(workflow, projectID: project.id) { onSelect(workflow.route.mode) }
                            } label: {
                                HStack {
                                    StudioArtwork(name: workflow.intention.artwork).frame(width: 46, height: 46)
                                    VStack(alignment: .leading) {
                                        Text(workflow.name).font(.headline)
                                        Text(workflow.intention.label + " · " + workflow.route.label).font(.caption).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                }.padding(12).modifier(StudioSurface())
                            }.buttonStyle(.plain)
                        }
                    }
                    Text("Saved buttons open their settings and inputs for review before you start.").font(.caption).foregroundStyle(.secondary)
                }
                Text("Build a custom workflow").font(.title2.weight(.semibold))
                HStack {
                    Button("NISE · small-molecule search") { openDirect(.nise, intention: .smallMolecule) }
                    Button("Original Protein Hunter · Boltz hallucination + iteration") { openDirect(.proteinHunter, intention: .minibinder) }
                }.buttonStyle(.bordered)
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 240))], spacing: 12) {
                    ForEach(DesignIntention.allCases) { intention in
                        Button { custom = intention } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                StudioArtwork(name: intention.artwork).frame(width: 64, height: 64)
                                Text(intention.label).font(.headline)
                                Text(intention.introduction).font(.callout).foregroundStyle(.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }.frame(maxWidth: .infinity, minHeight: 155, alignment: .topLeading)
                                .padding(18).modifier(StudioSurface())
                        }.buttonStyle(.plain)
                    }
                }
            }.padding(28).frame(maxWidth: 920).frame(maxWidth: .infinity)
        }.background(StudioPalette.canvas)
            .accessibilityIdentifier("design-method-chooser")
            .sheet(item: $recommended) { choice in
                RecommendedDesignSheet(project: project, installer: installer, intention: choice.intention,
                                       hard: choice.hard, onSelect: onSelect)
            }
            .sheet(item: $custom) { intention in
                CustomWorkflowSheet(project: project, intention: intention, onSelect: onSelect)
            }
    }
    private func openDirect(_ route: DesignWorkflowRoute, intention: DesignIntention) {
        app.updateProject(id: project.id) { p in
            p.designIntention = intention; p.preferredMode = route.mode
            if route == .proteinHunter {
                p.request = DesignRequest(); p.request.designType = .minibinder
                p.request.designer = .solublempnn; p.request.designPredictor = .boltz; p.request.postPredictors = [.esmfold2Full]
            }
        }
        onSelect(route.mode)
    }
}

struct RecommendedDesignSheet: View {
    @EnvironmentObject var app: AppState
    @Environment(\.dismiss) private var dismiss
    let project: Project
    @ObservedObject var installer: PipelineInstaller
    let intention: DesignIntention
    let hard: Bool
    let onSelect: (WorkspaceMode) -> Void
    @State private var target = ""
    @State private var useSequence = false
    @State private var sequence = ""
    @State private var pendingStart = false
    @StateObject private var targetPredictor = TargetPredictor()
    @State private var molecule = ""
    @State private var hotspots = ""
    @State private var chain = ""
    @State private var minutes = 60.0
    private var parsedHotspots: RecommendedDesign.Hotspots? { RecommendedDesign.hotspots(hotspots) }
    private var sequenceChains: [ProteinChainInput]? {
        guard case .success(let chains) = ProteinSequenceInput.parse(sequence, startingAt: 1, minimumLength: 5) else { return nil }
        return chains
    }
    private var request: RFD4Request {
        var value = RecommendedDesign.request(intention: intention, hard: hard, minutes: minutes)
        value.source = target; value.ligand_smiles = molecule.trimmingCharacters(in: .whitespacesAndNewlines)
        value.hotspots = parsedHotspots?.numbers ?? []
        value.hotspot_residues = parsedHotspots?.qualified
        value.source_target_chain = useSequence ? "" : chain
        return value
    }
    private var issues: [String] {
        var check = request
        if useSequence && intention != .smallMolecule && target.isEmpty { check.source = "pending-target.cif" }
        var issues = check.validationIssues
        if useSequence && sequenceChains == nil { issues.append("Enter complete protein sequences separated by a colon.") }
        if useSequence, let chains = sequenceChains, let hotspots = parsedHotspots {
            issues += RecommendedDesign.hotspotIssues(hotspots, chainLengths: Dictionary(uniqueKeysWithValues: chains.map { ($0.id, $0.sequence.count) }))
        }
        return issues
    }
    private var ready: Bool {
        request.requiredComponents.allSatisfy { installer.isUsable($0) }
            && (!useSequence || (installer.isUsable(.esmfold2Full) && installer.isUsable(.boltz)))
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                StudioArtwork(name: intention.artwork).frame(width: 72, height: 72)
                VStack(alignment: .leading) {
                    Text(intention.label).font(.title2.bold())
                    Text(hard ? "Hard target · seven-cycle beam search" : "Easy target · native RFD4 + scoring").foregroundStyle(.secondary)
                }
            }
            ScrollView {
                configuration
            }
            actions
        }.padding(28).frame(width: 580, height: 700)
            .interactiveDismissDisabled(targetPredictor.isRunning)
            .onChange(of: targetPredictor.phase) { _, phase in
                if case .done(let path) = phase {
                    target = path
                    apply()
                    if pendingStart { pendingStart = false; startDesign() }
                }
                if case .failed = phase { pendingStart = false }
            }
    }
    private var configuration: some View {
        VStack(alignment: .leading, spacing: 18) {
            if intention == .smallMolecule {
                TextField("Molecule SMILES", text: $molecule).textFieldStyle(.roundedBorder)
                Text("Paste one molecule, including its intended stereochemistry and charge. Studio prepares and checks its 3D structure.").font(.caption).foregroundStyle(.secondary)
            } else {
                proteinTargetInput
            }
            HStack {
                Text("Design time")
                TextField("Minutes", value: $minutes, format: .number).frame(width: 90).textFieldStyle(.roundedBorder)
                Text("minutes").foregroundStyle(.secondary)
            }
            Text("Counts active run time. The current operation finishes before stopping; completed candidates are saved. Time in the queue does not count.")
                .font(.caption).foregroundStyle(.secondary)
            Text(hard ? (intention == .smallMolecule ? "RFD4 → LASErMPNN → Boltz, keeping four parents for up to seven cycles."
                         : "RFD4 → \(intention == .nanobody ? "AbMPNN" : "SolubleMPNN") → ESMFold2 Full, keeping four parents for up to seven cycles.")
                 : "Generate with RFD4 and score each native sequence.").font(.callout)
            if intention != .smallMolecule {
                Text("Target alignments are reused or requested from the MSA server. \(intention == .nanobody ? "Uses the 7XL0 framework with CDR1, CDR2 and CDR3 redesigned." : "Uses 120-residue binders.")")
                    .font(.caption).foregroundStyle(.secondary)
            }
            ForEach(issues, id: \.self) { Text($0).font(.caption).foregroundStyle(.orange) }
            if !ready { Text("Install the required engines in Engines before starting.").foregroundStyle(.orange) }
            DisclosureGroup("Memory admission") { MemoryPolicyControl() }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
    private var actions: some View {
        HStack {
                Button("Cancel", role: .cancel) { dismiss() }.disabled(targetPredictor.isRunning)
                Spacer()
                Button("Customize") { apply(); dismiss(); onSelect(.rfdiffusion) }.disabled(targetPredictor.isRunning || (useSequence && target.isEmpty))
                Button(useSequence && target.isEmpty ? "Predict target & start" : "Start design") {
                    if useSequence && target.isEmpty {
                        pendingStart = true
                        targetPredictor.predict(targetKind: .protein, sequence: sequence, smiles: "", engine: .esmfold2Full)
                    } else { startDesign() }
                }.buttonStyle(.borderedProminent)
                    .disabled(!ready || !issues.isEmpty || parsedHotspots == nil || targetPredictor.isRunning || !app.rfd4.canStartAnother)
        }
    }
    private var proteinTargetInput: some View {
        VStack(alignment: .leading, spacing: 10) {
            Picker("Provide target as", selection: $useSequence) {
                Text("Structure file").tag(false)
                Text("Sequence").tag(true)
            }.pickerStyle(.segmented).disabled(targetPredictor.isRunning)
                .onChange(of: useSequence) { _, _ in target = ""; targetPredictor.reset() }
            if useSequence {
                ProteinChainInputView(text: $sequence, startingAt: 1,
                                      placeholder: "Target B[:target C…]", minimumLength: 5)
                    .disabled(targetPredictor.isRunning)
                    .onChange(of: sequence) { _, _ in target = ""; targetPredictor.reset() }
                Text("Separate chains with : . ESMFold2 Full predicts the complete target assembly first. Targets keep chains B, C, D…; chain A is reserved for your design.")
                    .font(.caption).foregroundStyle(.secondary)
                Text("Uses Boltz's shared per-sequence MSA cache and server lookup. Missing requested alignments stop the run. Target preparation is separate from the design-time budget.")
                    .font(.caption).foregroundStyle(.secondary)
                if targetPredictor.isRunning {
                    HStack { ProgressView().controlSize(.small); Text("Preparing target through the job queue…") }
                    Button("Stop target preparation") { pendingStart = false; targetPredictor.cancel() }
                }
                if case .failed(let message) = targetPredictor.phase { Text(message).font(.caption).foregroundStyle(.red) }
            } else {
                HStack {
                    Text(target.isEmpty ? "Target structure" : URL(fileURLWithPath: target).lastPathComponent).lineLimit(1)
                    Spacer()
                    Button("Choose PDB or CIF…") {
                        let panel = NSOpenPanel(); panel.canChooseDirectories = false
                        panel.allowedContentTypes = [.init(filenameExtension: "pdb")!, .init(filenameExtension: "cif")!, .init(filenameExtension: "mmcif")!]
                        if panel.runModal() == .OK, let url = panel.url { target = url.path }
                    }
                }
                DisclosureGroup("Select target chains") {
                    TextField("All protein chains, or a comma-separated selection", text: $chain)
                }
            }
            TextField("Hotspots (optional), e.g. B32 C55", text: $hotspots).textFieldStyle(.roundedBorder)
                .disabled(targetPredictor.isRunning)
            Text("Use source residue numbering. Bare numbers are accepted for a single target chain.").font(.caption).foregroundStyle(.secondary)
            if parsedHotspots == nil { Text("Use positive residue numbers or chain-qualified residues such as B32 C55.").foregroundStyle(.orange) }
        }
    }
    private func startDesign() {
        apply()
        let current = app.projects.first { $0.id == project.id } ?? project
        app.rfd4.start(request: request, project: current, name: "\(intention.label) · \(hard ? "hard" : "easy")")
        dismiss(); onSelect(.rfdiffusion)
    }

    private func apply() {
        app.updateProject(id: project.id) {
            $0.rfd4 = request; $0.diffusionEngine = "rfd4"; $0.designIntention = intention; $0.preferredMode = .rfdiffusion
        }
    }
}

struct CustomWorkflowSheet: View {
    @EnvironmentObject var app: AppState
    @Environment(\.dismiss) private var dismiss
    let project: Project
    let intention: DesignIntention
    let onSelect: (WorkspaceMode) -> Void
    @State private var route: DesignWorkflowRoute = .rfd4
    @State private var task: RFD4Task = .monomer
    @State private var search: DesignSearchPolicy = .native
    @State private var assess = false
    @State private var showMotifBeta = false
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                StudioArtwork(name: intention.artwork).frame(width: 72, height: 72)
                VStack(alignment: .leading) {
                    Text(intention.label).font(.title2.bold())
                    Text("Build your workflow").foregroundStyle(.secondary)
                }
            }
            Picker("Starting method", selection: $route) {
                ForEach(intention.routes, id: \.self) { Text($0.label).tag($0) }
            }
            if route == .rfd4 {
                if intention.rfd4Tasks.count > 1 {
                    Picker("Operation", selection: $task) {
                        ForEach(intention.rfd4Tasks) { Text($0.label).tag($0) }
                    }
                }
                if [.protein, .nanobody, .ligand].contains(task) {
                    Picker("Sequence exploration", selection: $search) {
                        ForEach(DesignSearchPolicy.allCases) { Text($0.label).tag($0) }
                    }
                    if search == .native { Toggle("Score generated sequences", isOn: $assess) }
                    Text(task == .ligand ? "Boltz assesses binding probability and ligand confidence."
                         : "ESMFold2 Full refolds candidates. Choose another supported predictor in the next step.").font(.caption).foregroundStyle(.secondary)
                }
            }
            if intention == .motif && route == .proteinHunter {
                Text("Boltz X-token scaffolding preserves motif sequences; coordinates can move. Use RFD3 or RFD4 to constrain the motif's structure.").font(.caption).foregroundStyle(.secondary)
            }
            if intention == .motif {
                Button("Atomic motif beta · template-guided Boltz") { showMotifBeta = true }
                Text("Existing benchmark-motif pilots start from RFD3 and guide Boltz with mapped motif residues. General template-guided X-token scaffolding is not yet available.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Text("Continue to configure inputs, conditioning, search depth and assessment. Save your configured workflow as a button from the design toolbar.")
                .font(.callout).foregroundStyle(.secondary)
            HStack {
                Button("Cancel", role: .cancel) { dismiss() }
                Spacer()
                Button("Configure workflow") { configure(); dismiss(); onSelect(route.mode) }.buttonStyle(.borderedProminent)
            }
        }.padding(28).frame(width: 560)
            .onAppear { task = intention.rfd4Tasks[0] }
            .sheet(isPresented: $showMotifBeta) { MotifBetaView(project: project) }
    }
    private func configure() {
        app.updateProject(id: project.id) { p in
            p.designIntention = intention; p.preferredMode = route.mode
            switch route {
            case .rfd4:
                var r = RFD4Request(); r.task = task
                if [.protein, .nanobody, .ligand].contains(task) {
                    r = RecommendedDesign.request(intention: task == .nanobody ? .nanobody : task == .ligand ? .smallMolecule : .minibinder,
                                                  hard: false, minutes: 60)
                    r.count = 1; r.time_budget_minutes = nil; r.search = search; r.assess_native = assess
                }
                r.annotated_input = task == .annotated
                p.rfd4 = r; p.diffusionEngine = "rfd4"
            case .rfd3:
                p.rfd3 = RFD3Request(); p.diffusionEngine = "rfd3"
                p.rfd3.targetKind = intention == .smallMolecule ? .smallMolecule : .protein
                p.rfd3.sequenceModel = intention == .smallMolecule ? .lasermpnn : .solublempnn
                p.rfd3.designMode = intention == .motif ? .motifScaffolding : intention == .optimize ? .partialDiffusion : .deNovo
            case .proteinHunter, .rfd3Monomer:
                p.request = DesignRequest(); p.request.designType = intention == .nanobody ? .nanobody : .minibinder
                p.request.targetKind = intention == .smallMolecule ? .ligand : .protein
                p.request.postPredictors = [.esmfold2Full]
                p.request.designer = intention == .nanobody ? .abmpnn : intention == .smallMolecule ? .lasermpnn : .solublempnn
                if intention == .monomer {
                    p.request.designType = .monomer; p.request.targetSequence = ""
                    p.request.postPredictors = []; p.request.postOnlyHits = false
                    p.request.postFilters.minimumIPTM = nil; p.request.postFilters.minimumIPSAEMin = nil
                    if route == .rfd3Monomer {
                        p.request.initializationMethod = "rfd3"
                        p.request.designPredictor = .esmfold2Full
                    }
                }
                if intention == .optimize { p.request.nativeBinderMode = "partialRedesign" }
                if intention == .motif { p.request.designType = .monomer; p.request.applyTypeDefaults(); p.request.nativeBinderMode = "motifScaffolding" }
            case .nise: break
            }
        }
    }
}
