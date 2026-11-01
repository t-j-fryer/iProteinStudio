import SwiftUI
import AppKit

struct DiffusionView: View {
    @EnvironmentObject var app: AppState
    let project: Project
    @ObservedObject var controller: RFD3Controller
    @ObservedObject var installer: PipelineInstaller
    private var engine: Binding<String> {
        Binding(get: { app.projects.first(where: { $0.id == project.id })?.diffusionEngine ?? project.diffusionEngine },
                set: { value in app.updateProject(id: project.id) { p in
                    p.diffusionEngine = value
                    if value == "rfd3", let intention = p.designIntention {
                        let kind: RFD3TargetKind = intention == .smallMolecule ? .smallMolecule : .protein
                        if p.rfd3.targetKind != kind {
                            p.rfd3.targetKind = kind
                            p.rfd3.sequenceModel = kind == .smallMolecule ? .lasermpnn : .solublempnn
                        }
                        p.rfd3.designMode = intention == .motif ? .motifScaffolding : intention == .optimize ? .partialDiffusion : .deNovo
                    }
                } })
    }
    var body: some View {
        VStack(spacing: 0) {
            if project.designIntention?.routes.contains(.rfd3) ?? true {
            Picker("Generator", selection: engine) {
                Text("RFdiffusion3").tag("rfd3")
                Text("RFD4").tag("rfd4")
            }.pickerStyle(.segmented).padding()
            }
            if engine.wrappedValue == "rfd4" {
                RFD4View(project: project, controller: app.rfd4, installer: installer)
            } else { RFD3View(project: project, controller: controller, installer: installer) }
        }
    }
}

struct RFD4View: View {
    @Environment(\.openWindow) private var openWindow
    @EnvironmentObject var app: AppState
    let project: Project
    @ObservedObject var controller: RFD4Controller
    @ObservedObject var installer: PipelineInstaller
    @State private var name = ""
    @State private var setupExperience: SetupExperience = .quick
    @State private var hotspotText = ""
    @State private var hotspotError: String?
    @State private var checkpointText = "8, 15"
    @State private var checkpointError: String?
    @State private var targetFromSequence = false
    @State private var targetSequence = ""
    @State private var targetEngine: TargetEngine = .esmfold2Full
    @StateObject private var targetPredictor = TargetPredictor()
    @State private var customCDRs = false
    @State private var extraLength = 100
    private var scaffolds: [Scaffold] { ScaffoldCatalog.load() }

    private var request: Binding<RFD4Request> {
        Binding(get: { app.projects.first(where: { $0.id == project.id })?.rfd4 ?? project.rfd4 },
                set: { value in app.updateProject(id: project.id) { $0.rfd4 = value } })
    }
    private var value: RFD4Request { request.wrappedValue }
    private var ready: Bool { value.requiredComponents.allSatisfy { installer.isUsable($0) } }
    private var tasks: [RFD4Task] {
        let intention = app.projects.first(where: { $0.id == project.id })?.designIntention
        let choices = intention?.rfd4Tasks ?? RFD4Task.allCases
        return choices.contains(value.task) ? choices : choices + [value.task]
    }
    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    header
                    SetupExperiencePicker(selection: $setupExperience)
                    startingStructures
                    conditionsForm
                    if value.canSearch { searchForm }
                    if setupExperience == .advanced && value.canSearch { nativeSearchForm }
                    if value.needsPrediction && value.task != .ligand { hitFilters }
                    executionForm
                    ForEach(value.validationIssues, id: \.self) { Text($0).foregroundStyle(.orange) }
                    if !ready { Text("Install the selected generator, sequence designer and predictor in Engines.").foregroundStyle(.orange) }
                    progressSection
                }.padding(28).frame(maxWidth: 860, alignment: .leading).frame(maxWidth: .infinity)
            }
            Divider()
            startBar
        }.onAppear { synchronizeTextInputs() }
        .onChange(of: targetPredictor.phase) { _, phase in
            if case .done(let path) = phase { request.wrappedValue.source = path; request.wrappedValue.source_target_chain = "" }
        }
        .onChange(of: value.hotspot_residues) { _, _ in synchronizeTextInputs() }
        .onChange(of: value.hotspots) { _, _ in synchronizeTextInputs() }
        .onChange(of: value.native_checkpoints) { _, _ in synchronizeTextInputs() }
    }
    private var header: some View {
        HStack(spacing: 16) {
            StudioArtwork(name: project.designIntention?.artwork ?? "backbone").frame(width: 68, height: 68)
            VStack(alignment: .leading, spacing: 5) {
                Text("RFD4").font(.largeTitle.weight(.semibold))
                Text("Generate structures and sequences, then explore and assess your candidates.").foregroundStyle(.secondary)
            }
        }
    }
    private func synchronizeTextInputs() {
        hotspotText = (value.hotspots.map(String.init) + (value.hotspot_residues ?? [])).joined(separator: ", ")
        checkpointText = value.native_checkpoints.map(String.init).joined(separator: ", ")
    }
    private func updateHotspots(_ text: String) {
        guard let parsed = RecommendedDesign.hotspots(text) else {
            hotspotError = "Use positive residue numbers or chain-qualified residues such as B32 C55."
            return
        }
        hotspotError = nil
        var updated = value; updated.hotspots = parsed.numbers; updated.hotspot_residues = parsed.qualified
        request.wrappedValue = updated
    }

    private var startingStructures: some View {
                Card(title: "1 · Starting structures", systemImage: "cube.transparent") {
                    VStack(alignment: .leading, spacing: 10) {
                        Picker("Design task", selection: request.task) {
                            ForEach(tasks) { Text($0.label).tag($0) }
                        }.onChange(of: value.task) { _, task in
                            request.wrappedValue.search = .native
                            request.wrappedValue.assess_native = false
                            request.wrappedValue.native_search = false
                            request.wrappedValue.sequence_model = task == .ligand ? "lasermpnn" : task == .nanobody ? "abmpnn" : "solublempnn"
                            request.wrappedValue.scaffold_id = nil
                            request.wrappedValue.length_plan = nil; request.wrappedValue.hit_filters = nil
                            targetFromSequence = false
                            if task == .ligand { request.wrappedValue.predictor = "boltz" }
                            request.wrappedValue.annotated_input = [.motif, .annotated].contains(task)
                            if task == .nanobody, let scaffold = scaffolds.first(where: { $0.id == "7xl0_vobarilizumab" }) {
                                request.wrappedValue.scaffold_id = scaffold.id
                                request.wrappedValue.cdr_ranges = scaffold.cdrRanges
                                request.wrappedValue.scaffold_msa = "auto"
                            }
                        }
                        if value.task == .ligand {
                            field("Molecule SMILES", text: request.ligand_smiles)
                            Text("One molecule with explicit stereochemistry and charge. A checked 3D conformer is prepared when no structure is supplied.").font(.caption).foregroundStyle(.secondary)
                            DisclosureGroup("Use an existing molecule structure") { file("Molecule CIF", path: request.source) }
                        } else if value.task != .monomer { targetInput }
                        if value.task == .nanobody { frameworkPicker }
                        if value.starting_structures.isEmpty {
                            if [.monomer, .protein, .ligand].contains(value.task) {
                                lengthForm
                            }
                            Toggle("Stop after a design time", isOn: Binding(get: { value.time_budget_minutes != nil }, set: {
                                request.wrappedValue.time_budget_minutes = $0 ? 60 : nil
                                request.wrappedValue.count = $0 ? 10000 : 1
                            }))
                            if value.time_budget_minutes != nil {
                                StudioFormField("Active design time (minutes)") { TextField("Minutes", value: Binding(get: { value.time_budget_minutes ?? 60 }, set: { request.wrappedValue.time_budget_minutes = $0 }), format: .number) }
                                Text("Finishes the current operation and saves completed candidates. Queue time is excluded.").font(.caption).foregroundStyle(.secondary)
                            } else { Stepper("Families: \(value.count)", value: request.count, in: 1...10000) }
                        } else {
                            Text("\(value.starting_structures.count) imported structures, one per family")
                            Button("Generate new structures") { request.wrappedValue.starting_structures = []; request.wrappedValue.count = 1 }
                        }
                        if value.canSearch {
                            Button("Refine existing structures…") {
                                let panel = NSOpenPanel(); panel.allowsMultipleSelection = true
                                panel.canChooseDirectories = false
                                if panel.runModal() == .OK {
                                    request.wrappedValue.starting_structures = panel.urls.map(\.path)
                                    request.wrappedValue.count = panel.urls.count
                                    request.wrappedValue.search = .iterative
                                }
                            }
                        }
                        if setupExperience == .advanced { StudioFormField("Generation seed") { TextField("Seed", value: request.seed, format: .number) }.help("Sets the random starting point for reproducible generation. Each family uses the next seed.") }
                        if value.task != .monomer {
                            field("Target chains in input structure", text: request.source_target_chain, hint: "Leave empty to retain all protein chains.")
                            if setupExperience == .advanced {
                            HStack { field("Designed chain ID", text: request.binder_chain); field("First target chain ID", text: request.target_chain) }
                            Text("Automatic assembly uses designed chain A and target chains B, C, D… These are output labels, not epitope residues.").font(.caption).foregroundStyle(.secondary)
                            if value.scaffold_id == nil { Toggle("Input is an RFD4 annotated CIF", isOn: request.annotated_input) }
                            Text("Annotated inputs retain native atom conditions, motifs and expandable segments. Their conditions are checked before a job is queued.").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        if value.task == .partial {
                            Slider(value: request.partial_fraction, in: 0.01...1) { Text("Partial diffusion") }
                            Text("Diffuse \(value.partial_fraction, format: .percent.precision(.fractionLength(0))) of the trajectory.")
                        }
                        if value.task == .inverse { Text("Keep the supplied backbone and generate its sequence and local atom representation.").font(.caption) }
                    }.padding(8)
                }
    }
    @ViewBuilder private var conditionsForm: some View {
                if !value.annotated_input && value.task != .monomer {
                    DisclosureGroup("Native conditions and retained segments") {
                        VStack(alignment: .leading, spacing: 8) {
                            if value.task != .protein && value.scaffold_id == nil {
                                field("Retained residues and generated segments", text: request.contig, hint: "Optional for de novo design")
                            }
                            Text("Leave segments empty for de novo protein or ligand binders. Studio derives them from the selected target chain.").font(.caption)
                            field("Epitope residues / hotspots (optional)", text: $hotspotText, hint: "Input chain and residue number, e.g. B32 C55")
                                .onChange(of: hotspotText) { _, text in updateHotspots(text) }
                            if let hotspotError { Text(hotspotError).foregroundStyle(.orange) }
                            ForEach(Array(value.conditions.indices), id: \.self) { index in
                                HStack {
                                    Picker("Condition", selection: request.conditions[index].condition) {
                                        ForEach(RFD4Condition.names, id: \.self) { Text($0).tag($0) }
                                    }
                                    field("Condition value", text: request.conditions[index].value)
                                    field("Atom selection", text: request.conditions[index].selection, hint: "e.g. sel('A/*/[10-20]')")
                                    Button("Remove") { request.wrappedValue.conditions.remove(at: index) }
                                }
                            }
                            if value.scaffold_id == nil && setupExperience == .advanced { Button("Add condition") { request.wrappedValue.conditions.append(RFD4Condition()) } }
                        }.padding(8)
                    }
                }
    }
    private var executionForm: some View {
                DisclosureGroup("Execution") {
                    VStack(alignment: .leading, spacing: 8) {
                        Toggle("Use optimized GPU operations (checked against reference)", isOn: request.optimized_kernels)
                        Text("Uses custom Metal operations for pair representations inside RFD4. The first structure in each generation stage (and at each new length) is generated twice to check exact agreement with the standard implementation; a mismatch stops the run. This adds an initial checking cost and is not an accuracy setting.").font(.caption)
                        MemoryPolicyControl()
                    }.padding(8)
                }
    }
    private var startBar: some View {
        HStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                if let minutes = value.time_budget_minutes { Text("\(minutes, format: .number) active minutes").font(.headline) }
                else { Text("\(value.count) families · \(value.predictions) assessments").font(.headline) }
                field("Run name (optional)", text: $name).frame(maxWidth: 280)
            }
            Spacer()
            Button("Start RFD4 run") { controller.start(request: value, project: project, name: name) }
                .buttonStyle(.borderedProminent).disabled(!ready || !value.validationIssues.isEmpty || !controller.canStartAnother || hotspotError != nil || checkpointError != nil || (targetFromSequence && targetPredictor.cifPath != value.source) || targetPredictor.isRunning)
        }.padding(.horizontal, 28).padding(.vertical, 14).background(.bar)
    }
    private var progressLog: String { controller.log.suffix(60).joined(separator: "\n") }
    @ViewBuilder private var progressSection: some View {
                if controller.projectSlug == project.slug {
                    Text(controller.currentMessage).textSelection(.enabled)
                    if controller.isRunning { Button("Stop run", action: controller.cancel) }
                    if case .failed(let error) = controller.phase {
                        Text(error).foregroundStyle(.red)
                        Button("Retry saved run", action: controller.retry)
                    }
                    if let output = controller.outputRoot {
                        Button("Open run files") { NSWorkspace.shared.open(output) }
                        Button("View live results") {
                            openWindow(value: RunResultsWindowRequest(root: output, workflow: .rfd4))
                        }
                        Text("Completed structures appear automatically in the results window while the run continues.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if !controller.log.isEmpty {
                        DisclosureGroup("Progress log") { Text(progressLog).font(.system(.caption, design: .monospaced)).textSelection(.enabled) }
                    }
                }
    }
    private var nativeSearchForm: some View {
        GroupBox("Search during RFD4 diffusion") {
            VStack(alignment: .leading, spacing: 10) {
                Toggle("Native rollout beam search", isOn: request.native_search).onChange(of: value.native_search) { _, active in
                    if active {
                        request.wrappedValue.search = .native; request.wrappedValue.assess_native = false
                        if value.task == .ligand { request.wrappedValue.predictor = "boltz" }
                    }
                }
                if value.native_search {
                    Text("Branch a partial diffusion trajectory, finish and score its rollouts, then continue the selected states using RFD4's native search implementation.").font(.caption)
                    Stepper("Beam width: \(value.native_beam_width)", value: request.native_beam_width, in: 1...16)
                    Stepper("Branches per state: \(value.native_branches)", value: request.native_branches, in: 1...16)
                    Slider(value: request.native_partial_fraction, in: 0.05...0.95) { Text("Partial trajectory fraction") }
                    Text("Partial trajectory: \(value.native_partial_fraction, format: .percent.precision(.fractionLength(0)))")
                    field("Diffusion checkpoint steps", text: $checkpointText).onChange(of: checkpointText) { _, text in
                        let values = text.split(whereSeparator: { $0 == "," || $0.isWhitespace }).map { Int($0) }
                        checkpointError = values.contains(where: { $0 == nil }) ? "Use integer checkpoint steps." : nil
                        if checkpointError == nil { request.wrappedValue.native_checkpoints = values.compactMap { $0 } }
                    }
                    if let checkpointError { Text(checkpointError).foregroundStyle(.orange) }
                    if value.task == .ligand {
                        field("Exact ligand SMILES", text: request.ligand_smiles)
                        Text("Boltz score: P(bind) + ligand pLDDT/100. Structure profile: 3 recycles, 25 steps; affinity: 50 steps. The input molecule must match the requested graph, charge and stereochemistry.").font(.caption)
                    } else { Text("Protein rollouts use the structure predictor and alignment selected above; the minimum directional ipSAE selects survivors.").font(.caption) }
                    Text("Completed families resume from receipts. An interrupted family replays from its recorded seed and checks every cached rollout identity before reusing its score.").font(.caption)
                }
            }.padding(8)
        }
    }
    private var searchForm: some View {
        Card(title: "2 · Sequence exploration and assessment", systemImage: "arrow.triangle.branch") {
            VStack(alignment: .leading, spacing: 10) {
                Picker("Search", selection: request.search) { ForEach(DesignSearchPolicy.allCases) { Text($0.label).tag($0) } }.disabled(value.native_search)
                if value.search == .native && !value.native_search { Toggle("Assess generated sequences", isOn: request.assess_native) }
                if value.needsPrediction {
                    Picker("Structure predictor", selection: request.predictor) {
                        ForEach(RFD4Predictor.families, id: \.self) { family in
                            Section(family) {
                                ForEach(RFD4Predictor.allCases.filter { $0.family == family && (value.task != .ligand || $0 == .boltz) }) { option in
                                    Text(option.label + (installer.isUsable(option.component) ? "" : " · install in Engines")).tag(option.rawValue)
                                }
                            }
                        }
                    }
                    if value.search != .native {
                        Picker("Sequence designer", selection: request.sequence_model) {
                            if value.task == .ligand { Text("LASErMPNN").tag("lasermpnn") }
                            else if value.task == .nanobody { Text("AbMPNN").tag("abmpnn") }
                            else { Text("SolubleMPNN").tag("solublempnn"); Text("ProteinMPNN").tag("proteinmpnn") }
                        }
                        if value.search != .fixed { Stepper("Cycles: \(value.cycles)", value: request.cycles, in: 1...100) }
                        if value.search != .iterative { Stepper("Proposals per parent: \(value.proposals)", value: request.proposals, in: 1...64) }
                        if value.search == .beam { Stepper("Surviving parents: \(value.beam_width)", value: request.beam_width, in: 1...64) }
                        StudioFormField("Sequence sampling temperature") { TextField("Temperature", value: request.temperature, format: .number) }.help("Controls sequence diversity: lower values favour the designer’s most likely amino acids; higher values sample more broadly.")
                        if value.task != .ligand { field("Excluded amino acids", text: request.omit_amino_acids, hint: "One-letter codes; C excludes cysteine. Empty allows all amino acids.") }
                    }
                    if value.task != .ligand && !["esmfold2-fast-mlx", "esmfold2-600-mlx"].contains(value.predictor) {
                        file("Target alignment", path: request.target_msa, singleSequence: true)
                        if value.task == .nanobody { file("Scaffold alignment", path: request.scaffold_msa, singleSequence: true) }
                    }
                    if value.task == .nanobody { cdrFields }
                    Text(value.task == .ligand ? "Selection uses P(bind) + ligand pLDDT/100. All proposals are saved. Search scores are design feedback; independent validation remains separate." : "Selection uses the minimum directional ipSAE. All proposals remain saved. Scores used to choose parents are design feedback; independent validation remains a separate step.").font(.caption)
                }
            }.padding(8)
        }
    }

    private func field(_ title: String, text: Binding<String>, hint: String = "") -> some View {
        StudioFormField(title, explanation: hint) { TextField(title, text: text).accessibilityLabel(title) }
    }
    private var targetInput: some View {
        VStack(alignment: .leading, spacing: 10) {
            if ([.protein, .nanobody].contains(value.task) && !value.annotated_input) || (value.task == .nanobody && value.scaffold_id != nil) {
                Picker("Target input", selection: $targetFromSequence) {
                    Text("Structure file").tag(false)
                    Text("Predict from sequence").tag(true)
                }.pickerStyle(.segmented).disabled(targetPredictor.isRunning)
            }
            if targetFromSequence {
                ProteinChainInputView(text: $targetSequence, startingAt: 1, placeholder: "Target protein sequence; separate chains with :", minimumLength: 5)
                    .disabled(targetPredictor.isRunning)
                    .onChange(of: targetSequence) { _, _ in request.wrappedValue.source = ""; targetPredictor.reset() }
                Picker("Target structure predictor", selection: $targetEngine) {
                    ForEach(TargetEngine.allCases) { Text($0.label).tag($0) }
                }.disabled(targetPredictor.isRunning)
                    .onChange(of: targetEngine) { _, _ in request.wrappedValue.source = ""; targetPredictor.reset() }
                Text("The target is predicted once using the shared queue and alignment cache. Its saved structure is then used for design; target preparation is separate from the design time limit.").font(.caption).foregroundStyle(.secondary)
                if targetPredictor.isRunning {
                    ProgressView("Preparing target…")
                    Button("Cancel target prediction") { targetPredictor.cancel() }
                } else {
                    Button("Predict target structure") {
                        targetPredictor.predict(targetKind: .protein, sequence: targetSequence, smiles: "", engine: targetEngine)
                    }.disabled(!installer.isUsable(targetEngine.component) || (!targetEngine.isSequenceOnly && !installer.isUsable(.boltz)) || !validTargetSequence)
                }
                if case .failed(let error) = targetPredictor.phase { Text(error).foregroundStyle(.red) }
                if let path = targetPredictor.cifPath { Text("Ready: " + URL(fileURLWithPath: path).lastPathComponent).foregroundStyle(.secondary) }
            } else {
                file(value.annotated_input && value.scaffold_id == nil ? "Annotated design structure (CIF)" : "Target structure (PDB or CIF)", path: request.source)
                Text(value.task == .nanobody && value.scaffold_id != nil ? "Supply the protein you want the nanobody to bind. Studio adds the selected framework; this file is not the nanobody framework." : "Supply the target protein or protein assembly. Target chains are retained together during design.").font(.caption).foregroundStyle(.secondary)
            }
            if [.protein, .nanobody].contains(value.task) {
                DisclosureGroup("Targets containing ligands or other molecules") {
                    Text("Prediction supports protein–ligand complexes. This protein-design route currently preserves protein chains only, so ligand-containing target files are rejected rather than silently losing their context. Native annotated input can retain explicit molecular conditions; refinement of mixed targets needs separate support.").font(.caption).foregroundStyle(.secondary)
                }
            }
        }
    }
    private var validTargetSequence: Bool {
        if case .success = ProteinSequenceInput.parse(targetSequence, startingAt: 1, minimumLength: 5) { return true }
        return false
    }
    private var frameworkPicker: some View {
        VStack(alignment: .leading, spacing: 8) {
            Picker("Nanobody framework", selection: Binding(get: { value.scaffold_id ?? "custom" }, set: { id in
                var updated = value
                updated.scaffold_id = id == "custom" ? nil : id
                updated.annotated_input = id == "custom"
                if let scaffold = scaffolds.first(where: { $0.id == id }) {
                    updated.contig = ""; updated.conditions = []
                    updated.cdr_ranges = scaffold.cdrRanges; updated.scaffold_msa = "auto"
                } else { updated.cdr_ranges = ""; updated.scaffold_msa = ""; targetFromSequence = false }
                customCDRs = false; request.wrappedValue = updated
            })) {
                ForEach(scaffolds) { Text($0.displayName).tag($0.id) }
                Text("Custom framework in annotated input").tag("custom")
            }
            if let scaffold = scaffolds.first(where: { $0.id == value.scaffold_id }) {
                Text("The framework stays fixed; the three CDR loops are redesigned. CDR boundaries are loaded from the selected framework.").font(.caption).foregroundStyle(.secondary)
                if scaffold.id == "3eak_nbbcii10_fgla" { Text("3EAK CDR boundaries were transferred by sequence alignment; they have not been independently numbered.").font(.caption).foregroundStyle(.secondary) }
            }
        }
    }
    private var cdrFields: some View {
        VStack(alignment: .leading, spacing: 6) {
            if value.scaffold_id != nil {
                Text("CDR boundaries · positions in the nanobody sequence (1-based)").font(.callout)
                Text(value.cdr_ranges).font(.system(.callout, design: .monospaced)).textSelection(.enabled)
                if setupExperience == .advanced {
                    Toggle("Override the framework’s CDR boundaries", isOn: $customCDRs)
                    if customCDRs { field("Custom CDR boundaries", text: request.cdr_ranges) }
                    Button("Restore framework boundaries") {
                        if let scaffold = scaffolds.first(where: { $0.id == value.scaffold_id }) { request.wrappedValue.cdr_ranges = scaffold.cdrRanges; customCDRs = false }
                    }
                }
            } else { field("CDR boundaries (1-based, inclusive)", text: request.cdr_ranges, hint: "e.g. CDR1:26-33,CDR2:51-57,CDR3:97-110") }
            Text("Only residues in these CDR ranges are redesigned by AbMPNN. The same ranges mask the framework alignment so the original CDR sequence does not guide prediction.").font(.caption).foregroundStyle(.secondary)
        }
    }
    private var lengthForm: some View {
        VStack(alignment: .leading, spacing: 10) {
            Toggle("Use a range of design lengths", isOn: Binding(get: { value.length_plan != nil }, set: { request.wrappedValue.length_plan = $0 ? RFD4LengthPlan(minimum: min(75,value.length), maximum: value.length) : nil }))
            if let plan = value.length_plan {
                HStack {
                    StudioFormField("Minimum length (aa)") { TextField("Minimum", value: Binding(get: { value.length_plan?.minimum ?? 75 }, set: { request.wrappedValue.length_plan?.minimum = $0 }), format: .number) }
                    StudioFormField("Maximum length (aa)") { TextField("Maximum", value: Binding(get: { value.length_plan?.maximum ?? 120 }, set: { request.wrappedValue.length_plan?.maximum = $0 }), format: .number) }
                }
                Text("By default, starts are spread evenly across the range. If there are fewer starts than lengths, they span the range; lengths are interleaved in time-limited runs.").font(.caption).foregroundStyle(.secondary)
                DisclosureGroup("Custom numbers of starts per length") {
                    Toggle("Specify counts", isOn: Binding(get: { value.length_plan?.counts != nil }, set: { request.wrappedValue.length_plan?.counts = $0 ? [String(plan.minimum): value.count] : nil }))
                    if let counts = plan.counts {
                        ForEach(counts.keys.sorted { (Int($0) ?? 0) < (Int($1) ?? 0) }, id: \.self) { key in
                            HStack {
                                Stepper("\(key) aa: \(counts[key] ?? 0) starts", value: Binding(get: { value.length_plan?.counts?[key] ?? 1 }, set: { request.wrappedValue.length_plan?.counts?[key] = $0 }), in: 1...10000)
                                Button("Remove") { request.wrappedValue.length_plan?.counts?.removeValue(forKey: key) }
                            }
                        }
                        HStack {
                            StudioFormField("Additional length (aa)") { TextField("Length", value: $extraLength, format: .number) }
                            Button("Add length") { request.wrappedValue.length_plan?.counts?[String(extraLength)] = 1 }.disabled(!(plan.minimum...max(plan.minimum,plan.maximum)).contains(extraLength))
                        }
                        Button("Set total families to \(counts.values.reduce(0,+))") { request.wrappedValue.count = counts.values.reduce(0,+) }.disabled(!(1...10000).contains(counts.values.reduce(0,+)))
                    }
                }
            } else { Stepper("Design length: \(value.length) amino acids", value: request.length, in: 1...2000) }
        }
    }
    private var hitFilters: some View {
        DisclosureGroup("Hit filters") {
            VStack(alignment: .leading, spacing: 10) {
                Text("Flag candidates meeting all selected cutoffs. All candidates are saved, and these filters do not change which parents continue in the search. Missing scores fail the corresponding filter.").font(.caption).foregroundStyle(.secondary)
                hitFilter("Minimum ipSAE", key: "ipsae_min", initial: 0.5)
                hitFilter("Minimum iPTM", key: "iptm", initial: 0.5)
                hitFilter("Minimum mean complex pLDDT (0–1)", key: "complex_plddt", initial: 0.7)
            }.padding(8)
        }
    }
    private func hitFilter(_ title: String, key: String, initial: Double) -> some View {
        HStack {
            Toggle(title, isOn: Binding(get: { value.hit_filters?[key] != nil }, set: { enabled in
                var filters = value.hit_filters ?? [:]
                if enabled { filters[key] = initial } else { filters.removeValue(forKey: key) }
                request.wrappedValue.hit_filters = filters.isEmpty ? nil : filters
            }))
            if value.hit_filters?[key] != nil {
                TextField(title, value: Binding(get: { value.hit_filters?[key] ?? initial }, set: { request.wrappedValue.hit_filters?[key] = $0 }), format: .number).frame(width: 85).accessibilityLabel(title)
            }
        }
    }

    private func file(_ title: String, path: Binding<String>, singleSequence: Bool = false) -> some View {
        HStack {
            Text(title)
            Text(path.wrappedValue == "auto" ? "Automatic alignment" : path.wrappedValue == "empty" ? "Single sequence" : (path.wrappedValue.isEmpty ? "Not selected" : URL(fileURLWithPath: path.wrappedValue).lastPathComponent)).foregroundStyle(.secondary)
            Button("Choose…") {
                let panel = NSOpenPanel(); panel.canChooseDirectories = false
                if panel.runModal() == .OK, let url = panel.url { path.wrappedValue = url.path }
            }
            if singleSequence { Button("Automatic") { path.wrappedValue = "auto" }; Button("Single sequence") { path.wrappedValue = "empty" } }
        }
    }
}
