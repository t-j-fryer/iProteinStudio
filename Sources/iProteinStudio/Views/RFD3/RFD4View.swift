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
                    executionForm
                    ForEach(value.validationIssues, id: \.self) { Text($0).foregroundStyle(.orange) }
                    if !ready { Text("Install the selected generator, sequence designer and predictor in Engines.").foregroundStyle(.orange) }
                    progressSection
                }.padding(28).frame(maxWidth: 860, alignment: .leading).frame(maxWidth: .infinity)
            }
            Divider()
            startBar
        }.onAppear { synchronizeTextInputs() }
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
                            if task == .ligand { request.wrappedValue.predictor = "boltz" }
                            request.wrappedValue.annotated_input = [.nanobody, .motif, .annotated].contains(task)
                        }
                        if value.task == .ligand {
                            TextField("Molecule SMILES", text: request.ligand_smiles)
                            Text("One molecule with explicit stereochemistry and charge. A checked 3D conformer is prepared when no structure is supplied.").font(.caption).foregroundStyle(.secondary)
                            DisclosureGroup("Use an existing molecule structure") { file("Molecule CIF", path: request.source) }
                        } else if value.task != .monomer { file("Source structure", path: request.source) }
                        if value.task == .nanobody {
                            Picker("Framework", selection: Binding(get: { value.scaffold_id ?? "custom" }, set: {
                                request.wrappedValue.scaffold_id = $0 == "custom" ? nil : $0
                                request.wrappedValue.annotated_input = $0 == "custom"
                                if $0 != "custom" {
                                    request.wrappedValue.contig = ""; request.wrappedValue.conditions = []
                                    request.wrappedValue.cdr_ranges = "CDR1:26-33,CDR2:51-57,CDR3:97-110"
                                    request.wrappedValue.scaffold_msa = "auto"
                                }
                            })) {
                                Text("7XL0 · vobarilizumab").tag("7xl0_vobarilizumab")
                                Text("Custom framework in input").tag("custom")
                            }
                        }
                        if value.starting_structures.isEmpty {
                            if [.monomer, .protein, .ligand].contains(value.task) {
                                Stepper("Generated length: \(value.length)", value: request.length, in: 1...2000)
                            }
                            Toggle("Stop after a design time", isOn: Binding(get: { value.time_budget_minutes != nil }, set: {
                                request.wrappedValue.time_budget_minutes = $0 ? 60 : nil
                                request.wrappedValue.count = $0 ? 10000 : 1
                            }))
                            if value.time_budget_minutes != nil {
                                TextField("Active minutes", value: Binding(get: { value.time_budget_minutes ?? 60 }, set: { request.wrappedValue.time_budget_minutes = $0 }), format: .number)
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
                        if setupExperience == .advanced { TextField("Generation seed", value: request.seed, format: .number) }
                        if value.task != .monomer {
                            TextField("Target chains in source (blank = all proteins)", text: request.source_target_chain)
                            if setupExperience == .advanced {
                            HStack { TextField("Binder chain", text: request.binder_chain); TextField("Target chain", text: request.target_chain) }
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
                                TextField("Retained residues and generated segments (optional)", text: request.contig)
                            }
                            Text("Leave segments empty for de novo protein or ligand binders. Studio derives them from the selected target chain.").font(.caption)
                            TextField("Hotspots, e.g. B32 C55", text: $hotspotText)
                                .onChange(of: hotspotText) { _, text in updateHotspots(text) }
                            if let hotspotError { Text(hotspotError).foregroundStyle(.orange) }
                            ForEach(Array(value.conditions.indices), id: \.self) { index in
                                HStack {
                                    Picker("Condition", selection: request.conditions[index].condition) {
                                        ForEach(RFD4Condition.names, id: \.self) { Text($0).tag($0) }
                                    }
                                    TextField("Value", text: request.conditions[index].value)
                                    TextField("e.g. sel('A/*/[10-20]')", text: request.conditions[index].selection)
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
                        Toggle("Use qualified Metal pair kernels", isOn: request.optimized_kernels)
                        Text("When enabled, the first structure is also generated with the reference implementation. Every output tensor must agree exactly before continuing.").font(.caption)
                        MemoryPolicyControl()
                    }.padding(8)
                }
    }
    private var startBar: some View {
        HStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                if let minutes = value.time_budget_minutes { Text("\(minutes, format: .number) active minutes").font(.headline) }
                else { Text("\(value.count) families · \(value.predictions) assessments").font(.headline) }
                TextField("Run name", text: $name).frame(maxWidth: 280)
            }
            Spacer()
            Button("Start RFD4 run") { controller.start(request: value, project: project, name: name) }
                .buttonStyle(.borderedProminent).disabled(!ready || !value.validationIssues.isEmpty || !controller.canStartAnother || hotspotError != nil || checkpointError != nil)
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
                        if controller.phase == .finished { RFD4ResultsView(root: output) }
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
                    TextField("Checkpoint steps", text: $checkpointText).onChange(of: checkpointText) { _, text in
                        let values = text.split(whereSeparator: { $0 == "," || $0.isWhitespace }).map { Int($0) }
                        checkpointError = values.contains(where: { $0 == nil }) ? "Use integer checkpoint steps." : nil
                        if checkpointError == nil { request.wrappedValue.native_checkpoints = values.compactMap { $0 } }
                    }
                    if let checkpointError { Text(checkpointError).foregroundStyle(.orange) }
                    if value.task == .ligand {
                        TextField("Exact ligand SMILES", text: request.ligand_smiles)
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
                        if value.task != .ligand {
                            Text("ESMFold2 Full").tag("esmfold2-full-mlx")
                            Text("ESMFold2 Fast").tag("esmfold2-fast-mlx")
                            Text("ESMFold2Fast-600M").tag("esmfold2-600-mlx")
                        }
                        Text("Boltz-2").tag("boltz")
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
                        TextField("Sequence temperature", value: request.temperature, format: .number)
                        if value.task != .ligand { TextField("Exclude amino acids", text: request.omit_amino_acids) }
                    }
                    if value.task != .ligand && !["esmfold2-fast-mlx", "esmfold2-600-mlx"].contains(value.predictor) {
                        file("Target alignment", path: request.target_msa, singleSequence: true)
                        if value.task == .nanobody { file("Scaffold alignment", path: request.scaffold_msa, singleSequence: true) }
                    }
                    if value.task == .nanobody { TextField("CDR ranges (1-based)", text: request.cdr_ranges) }
                    Text(value.task == .ligand ? "Selection uses P(bind) + ligand pLDDT/100. All proposals are saved. Search scores are design feedback; independent validation remains separate." : "Selection uses the minimum directional ipSAE. All proposals remain saved. Scores used to choose parents are design feedback; independent validation remains a separate step.").font(.caption)
                }
            }.padding(8)
        }
    }
    private func file(_ title: String, path: Binding<String>, singleSequence: Bool = false) -> some View {
        HStack {
            Text(title)
            Text(path.wrappedValue == "auto" ? "Automatic alignment" : path.wrappedValue == "empty" ? "Single sequence" : URL(fileURLWithPath: path.wrappedValue).lastPathComponent).foregroundStyle(.secondary)
            Button("Choose…") {
                let panel = NSOpenPanel(); panel.canChooseDirectories = false
                if panel.runModal() == .OK, let url = panel.url { path.wrappedValue = url.path }
            }
            if singleSequence { Button("Automatic") { path.wrappedValue = "auto" }; Button("Single sequence") { path.wrappedValue = "empty" } }
        }
    }
}

struct RFD4ResultsView: View {
    let root: URL
    @State private var rows: [Row] = []
    @State private var error: String?
    @State private var budgetSummary: String?
    struct Row: Decodable, Identifiable {
        let id: String
        let family: String
        let structure: String
        let cycle: Int?
        let ipsae_min: Double?
        let score: Double?
        let parent_id: String?
    }
    var body: some View {
        VStack(alignment: .leading) {
            Text("Saved candidates").font(.headline)
            if let budgetSummary { Text(budgetSummary).font(.callout).foregroundStyle(.secondary) }
            if let error { Text(error).foregroundStyle(.red) }
            Table(rows) {
                TableColumn("Candidate", value: \.id)
                TableColumn("Family", value: \.family)
                TableColumn("Parent") { Text($0.parent_id ?? "Generated") }
                TableColumn("Cycle") { Text($0.cycle.map(String.init) ?? "—") }
                TableColumn("ipSAE") { row in Text(row.ipsae_min.map { String(format: "%.3f", $0) } ?? "Not assessed") }
                TableColumn("Search score") { row in Text(row.score.map { String(format: "%.3f", $0) } ?? "—") }
                TableColumn("Structure") { row in Button("Open") { NSWorkspace.shared.open(URL(fileURLWithPath: row.structure)) } }
            }.frame(minHeight: 240)
        }.task(id: root) {
            if let data = try? Data(contentsOf: root.appendingPathComponent("budget_result.json")),
               let result = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                budgetSummary = "\(result["reason"] as? String == "time_budget" ? "Design time reached" : "Family limit reached") · \(result["complete_families"] as? Int ?? 0) completed families · \(result["saved_candidates"] as? Int ?? 0) saved candidates."
            } else { budgetSummary = nil }
            do { rows = try JSONDecoder().decode([Row].self, from: Data(contentsOf: root.appendingPathComponent("results.json"))); error = nil }
            catch { self.error = error.localizedDescription }
        }
    }
}
