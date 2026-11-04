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
                    // These are shared molecule inputs, not generator-specific flags.
                    if value == "rfd3", p.rfd4.task == .ligand, p.rfd4.source.isEmpty, !p.rfd4.annotated_input {
                        p.rfd3.targetKind = .smallMolecule; p.rfd3.ligandSource = .smiles
                        p.rfd3.sequenceModel = .lasermpnn
                        p.rfd3.smiles = p.rfd4.ligand_smiles
                        p.rfd3.attachmentAtom = p.rfd4.ligand_attachment_atom
                        p.rfd3.attachmentLinkerAtom = p.rfd4.ligand_attachment_linker_atom
                        p.rfd3.ligandIsConjugated = p.rfd4.ligand_is_conjugated ?? false
                        p.rfd3.searchPDB = p.rfd4.ligand_search_pdb ?? true
                        p.rfd3.conditions = (p.rfd4.ligand_atom_conditions ?? [:]).mapValues { Set($0.compactMap(AtomCondition.init(rawValue:))) }
                        p.rfd3.conformerPlan = (p.rfd4.ligand_conformers ?? []).map { ConformerChoice(label: $0.label, path: $0.path, weight: $0.weight) }
                    } else if value == "rfd4", p.rfd3.targetKind == .smallMolecule, p.rfd3.ligandSource == .smiles, p.rfd3.designMode == .deNovo {
                        p.rfd4.task = .ligand; p.rfd4.source = ""; p.rfd4.annotated_input = false
                        p.rfd4.sequence_model = "lasermpnn"
                        if !p.rfd4.selectionMetrics.contains(p.rfd4.selectedMetric) { p.rfd4.selection_metric = nil }
                        p.rfd4.ligand_smiles = p.rfd3.smiles
                        p.rfd4.ligand_attachment_atom = p.rfd3.attachmentAtom
                        p.rfd4.ligand_attachment_linker_atom = p.rfd3.attachmentLinkerAtom
                        p.rfd4.ligand_is_conjugated = p.rfd3.ligandIsConjugated
                        p.rfd4.ligand_search_pdb = p.rfd3.searchPDB
                        p.rfd4.ligand_atom_conditions = p.rfd3.conditions.mapValues { $0.map(\.rawValue).sorted() }
                        p.rfd4.ligand_conformers = p.rfd3.conformerPlan.isEmpty ? nil : p.rfd3.conformerPlan.map { RFD4Conformer(label: $0.label, path: $0.path, weight: $0.weight) }
                    }
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
    private let setupExperience: SetupExperience = .advanced
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack(spacing: 14) {
                    StudioArtwork(name: project.designIntention?.artwork ?? "backbone").frame(width: 68, height: 68)
                    VStack(alignment: .leading, spacing: 5) {
                        Text("Backbone design").font(.largeTitle.weight(.semibold))
                        Text("Configure your target, binding site and design workflow.").foregroundStyle(.secondary)
                    }
                }
                Card(title: "Backbone generator", systemImage: "cube.transparent") {
                    Picker("Generate with", selection: engine) {
                        Text("RFD4").tag("rfd4")
                        if project.designIntention?.routes.contains(.rfd3) ?? true {
                            Text("RFdiffusion3").tag("rfd3")
                        }
                    }.pickerStyle(.menu)
                    Text("The generator changes the conditioning, sequence design and search options below.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if engine.wrappedValue == "rfd4" {
                    RFD4ConfigurationFields(project: project, controller: app.rfd4, installer: installer, setupExperience: .constant(setupExperience))
                } else {
                    RFD3ConfigurationFields(project: project, controller: controller, installer: installer, setupExperience: .constant(setupExperience))
                }
            }.padding(28).frame(maxWidth: 860, alignment: .leading).frame(maxWidth: .infinity)
        }
    }
}

struct RFD4ConfigurationFields: View {
    @Environment(\.openWindow) private var openWindow
    @EnvironmentObject var app: AppState
    let project: Project
    @ObservedObject var controller: RFD4Controller
    @ObservedObject var installer: PipelineInstaller
    @State private var name = ""
    @Binding var setupExperience: SetupExperience
    @State private var hotspotText = ""
    @State private var hotspotError: String?
    @State private var checkpointText = "8, 15"
    @State private var checkpointError: String?
    @State private var targetFromSequence = false
    @State private var targetSequence = ""
    @State private var targetEngine: TargetEngine = .esmfold2Full
    @StateObject private var targetPredictor = TargetPredictor()
    @State private var customCDRs = false
    @StateObject private var numericValidation = NumericInputValidation()
    @StateObject private var ligandIntelligence = LigandIntelligence(useRFD4Runtime: true)
    @StateObject private var ligandInspector = RFD3TargetInspector(useRFD4Runtime: true)
    @State private var showEpitope = false
    @State private var showMotif = false
    @State private var pickedResidues: [String] = []
    @State private var showTargetSurface = true
    @State private var extraLength = 100
    @State private var proposedLigandConditions: [String: [String]]?
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
            Group {
                VStack(alignment: .leading, spacing: 20) {
                    startingStructures
                    if value.task == .motif && !value.annotated_input { motifForm }
                    if value.task == .ligand && !value.ligand_smiles.isEmpty && value.source.isEmpty { ligandPreparation }
                    if [.protein, .nanobody].contains(value.task) && !value.annotated_input { epitopeForm }
                    conditionsForm
                    if value.canSearch { searchForm }
                    if setupExperience == .advanced && value.canSearch { nativeSearchForm }
                    if value.needsPrediction && value.task != .ligand { hitFilters }
                    executionForm
                    ForEach(value.validationIssues, id: \.self) { Text($0).foregroundStyle(.orange) }
                    if !ready { Text("Install the selected generator, sequence designer and predictor in Engines.").foregroundStyle(.orange) }
                    progressSection
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            Divider()
            startBar
        }.environment(\.numericInputValidation, numericValidation)
        .onAppear { synchronizeTextInputs() }
        .sheet(isPresented: $showMotif) {
            RFD4MotifEditor(source: value.source, initial: value.motif) { motif in
                request.wrappedValue.motif = motif
                request.wrappedValue.contig = ""
                request.wrappedValue.hotspots = []; request.wrappedValue.hotspot_residues = nil
                request.wrappedValue.conditions.removeAll { ["C_CRD", "C_CRDGRP", "C_SEQ", "C_IDX"].contains($0.condition) }
            }
        }
        .sheet(isPresented: $showEpitope) {
            VStack(alignment: .leading, spacing: 12) {
                Text("Choose the target epitope").font(.title2)
                Text("Click target residues to add or remove contact hotspots. Residues retain their input chain IDs and numbering.")
                Toggle("Show target surface", isOn: $showTargetSurface)
                TargetStructureView(structurePath: value.source, selected: $pickedResidues, showSurface: showTargetSurface)
                Text(pickedResidues.joined(separator: ", ")).textSelection(.enabled)
                HStack {
                    Button("Cancel") { showEpitope = false }
                    Spacer()
                    Button("Use selected residues") { updateHotspots(pickedResidues.joined(separator: " ")); synchronizeTextInputs(); showEpitope = false }
                }
            }.padding(20).frame(minWidth: 850, minHeight: 650)
        }
        .onChange(of: targetPredictor.phase) { _, phase in
            if case .done(let path) = phase { request.wrappedValue.source = path; request.wrappedValue.source_target_chain = "" }
        }
        .onChange(of: value.hotspot_residues) { _, _ in synchronizeTextInputs() }
        .onChange(of: value.hotspots) { _, _ in synchronizeTextInputs() }
        .onChange(of: value.native_checkpoints) { _, _ in synchronizeTextInputs() }
        .onChange(of: value.source) { _, _ in request.wrappedValue.motif = nil }
        .onChange(of: value.annotated_input) { _, enabled in
            if enabled { request.wrappedValue.motif = nil; targetFromSequence = false }
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
                            request.wrappedValue.scaffold_weights = nil; request.wrappedValue.selection_metric = nil
                            request.wrappedValue.length_plan = nil; request.wrappedValue.hit_filters = nil
                            targetFromSequence = false
                            request.wrappedValue.ligand_conformers = nil; request.wrappedValue.ligand_conformer = nil; request.wrappedValue.ligand_atom_conditions = nil
                            request.wrappedValue.ligand_attachment_atom = nil; request.wrappedValue.ligand_attachment_linker_atom = nil; request.wrappedValue.ligand_is_conjugated = nil; request.wrappedValue.ligand_search_pdb = nil
                            if task == .ligand { request.wrappedValue.predictor = "boltz" }
                            request.wrappedValue.motif = nil
                            request.wrappedValue.annotated_input = task == .annotated
                            if task == .nanobody, let scaffold = scaffolds.first(where: { $0.id == "7xl0_vobarilizumab" }) {
                                request.wrappedValue.scaffold_id = scaffold.id
                                request.wrappedValue.cdr_ranges = scaffold.cdrRanges
                                request.wrappedValue.scaffold_msa = "auto"
                            }
                        }
                        if value.task == .ligand {
                            field("Molecule SMILES", text: request.ligand_smiles).onChange(of: value.ligand_smiles) { _, _ in
                                ligandIntelligence.reset(); ligandInspector.reset()
                                request.wrappedValue.ligand_conformers = nil; request.wrappedValue.ligand_atom_conditions = nil
                                request.wrappedValue.ligand_attachment_atom = nil; request.wrappedValue.ligand_attachment_linker_atom = nil
                            }
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
                            } else {
                                StudioFormField("Families") {
                                    EditableIntStepper(value: request.count, in: 1...10000,
                                        accessibilityLabel: "Families", showsStepper: false)
                                }
                                Text("Independent starting structures. Enter a whole number from 1 to 10,000.")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
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
                        if value.task != .monomer && value.task != .motif {
                            field("Target chains in input structure", text: request.source_target_chain, hint: "Leave empty to retain all protein chains.")
                            if setupExperience == .advanced {
                            HStack { field("Designed chain ID", text: request.binder_chain); field("First target chain ID", text: request.target_chain) }
                            Text("Automatic assembly uses designed chain A and target chains B, C, D… These are output labels, not epitope residues.").font(.caption).foregroundStyle(.secondary)
                            if value.scaffold_id == nil { Toggle("Input is an RFD4 annotated CIF", isOn: request.annotated_input) }
                            Text("Annotated inputs retain native atom conditions, motifs and expandable segments. Their conditions are checked before a job is queued.").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        if value.task == .motif {
                            Toggle("Use an already annotated RFD4 CIF", isOn: request.annotated_input)
                            Text("For an ordinary structure, choose the motif below. Annotated CIFs already contain native motif and scaffold conditions.").font(.caption).foregroundStyle(.secondary)
                        }
                        if value.task == .partial {
                            Slider(value: request.partial_fraction, in: 0.01...1) { Text("Partial diffusion") }
                            Text("Diffuse \(value.partial_fraction, format: .percent.precision(.fractionLength(0))) of the trajectory.")
                        }
                        if value.task == .inverse { Text("Keep the supplied backbone and generate its sequence and local atom representation.").font(.caption) }
                    }.padding(8)
                }
    }
    private var motifForm: some View {
        Card(title: "Motif residues, atoms and scaffold", systemImage: "scope") {
            VStack(alignment: .leading, spacing: 8) {
                Text("Provide a structure, or predict one from a sequence above. Choose the residues and exact atoms to preserve, then set the generated scaffold segments and native geometry/index controls.")
                Button(value.motif == nil ? "Choose motif residues and atoms…" : "Edit motif residues and atoms…") { showMotif = true }
                    .disabled(value.source.isEmpty || targetPredictor.isRunning)
                if let motif = value.motif {
                    Text(motif.residues.map { $0.id + " [" + $0.atoms.joined(separator: ", ") + "]" }.joined(separator: "; "))
                        .font(.caption.monospaced()).textSelection(.enabled)
                    Text("Geometry conditioning: " + (motif.coordinate_mode == "absolute" ? "absolute coordinates" : "relative group") + " · " + (motif.fix_sequence ? "fixed residue identities" : "backbone-only sequence redesign") + " · " + (motif.unindexed ? "free sequence placement" : "indexed placement"))
                        .font(.caption).foregroundStyle(.secondary)
                    Button("Clear motif") { request.wrappedValue.motif = nil }
                }
                Text("The guided form scaffolds residues from one protein chain. Native annotated CIFs remain available for multi-chain, ligand or metal motifs. Applying a guided selection replaces manual motif layout, geometry conditions and protein-binder hotspots.").font(.caption).foregroundStyle(.secondary)
            }
        }
    }
    private var ligandRequest: Binding<RFD3Request> {
        Binding(get: {
            var shared = RFD3Request()
            shared.smiles = value.ligand_smiles
            shared.attachmentAtom = value.ligand_attachment_atom
            shared.attachmentLinkerAtom = value.ligand_attachment_linker_atom
            shared.ligandIsConjugated = value.ligand_is_conjugated ?? false
            shared.searchPDB = value.ligand_search_pdb ?? true
            shared.numDesigns = value.count
            shared.conformerPlan = (value.ligand_conformers ?? []).map { ConformerChoice(label: $0.label, path: $0.path, weight: $0.weight) }
            shared.conditions = (value.ligand_atom_conditions ?? [:]).mapValues { Set($0.compactMap(AtomCondition.init(rawValue:))) }
            return shared
        }, set: { shared in
            var updated = value
            updated.ligand_attachment_atom = shared.attachmentAtom
            updated.ligand_attachment_linker_atom = shared.attachmentLinkerAtom
            updated.ligand_search_pdb = shared.searchPDB
            updated.ligand_is_conjugated = shared.ligandIsConjugated
            updated.ligand_conformers = shared.conformerPlan.isEmpty ? nil : shared.conformerPlan.map { RFD4Conformer(label: $0.label, path: $0.path, weight: $0.weight) }
            updated.ligand_atom_conditions = shared.conditions.mapValues { $0.map(\.rawValue).sorted() }
            request.wrappedValue = updated
        })
    }
    private var ligandPreparation: some View {
        Card(title: "Molecule shapes and binding site", systemImage: "sparkles.rectangle.stack") {
            VStack(alignment: .leading, spacing: 12) {
                LigandIntelligenceView(intelligence: ligandIntelligence, request: ligandRequest,
                    outputDir: AppPaths.projectDir(project).appendingPathComponent("rfd4/assets/conformers"), atomLabels: ligandInspector.atomLabels,
                    allocationExplanation: "Starts are interleaved across the selected shapes and lengths. Each selected shape/length input is checked before submission.")
                Button("Inspect atoms for binding-site conditions") { proposedLigandConditions = nil; ligandInspector.inspectLigand(smiles: value.ligand_smiles) }
                Text("Inspect reads atom names and chemical roles from your SMILES and opens the condition checklist. It does not select conditions or run a design.")
                    .font(.caption).foregroundStyle(.secondary)
                if ligandInspector.isInspecting { ProgressView() }
                if let error = ligandInspector.error { Text(error).foregroundStyle(.orange) }
                if ligandInspector.hasResult {
                    Text("Bury/expose use RFD4’s native solvent-accessibility bins. Hotspot asks for a contact; donor/acceptor describe the ligand atom. These conditions guide generation, not the predictor’s ranking score.").font(.caption).foregroundStyle(.secondary)
                    Button("Preview suggested atom conditions") {
                        let exposed = Set(ligandIntelligence.analysis?.core.presentationAtoms ?? [])
                        proposedLigandConditions = ligandInspector.suggestedConditions(presentationAtomIndices: exposed).mapValues { $0.map(\.rawValue).sorted() }
                    }
                    .disabled((value.ligand_is_conjugated ?? false) && ligandIntelligence.analysis == nil)
                    Text("Suggestions propose buried non-polar atoms, donor/acceptor roles for your supplied chemical state, and exposure of an analysed linker. They do not guess hotspots. Review the proposal before replacing your selections.")
                        .font(.caption).foregroundStyle(.secondary)
                    if (value.ligand_is_conjugated ?? false) && ligandIntelligence.analysis == nil {
                        Text("Analyse the selected core-to-linker bond before requesting suggestions.").font(.caption).foregroundStyle(.secondary)
                    }
                    if let proposal = proposedLigandConditions {
                        Text(AtomCondition.allCases.map { condition in
                            "\(condition.label): \(proposal.values.filter { $0.contains(condition.rawValue) }.count)"
                        }.joined(separator: " · ")).font(.caption)
                        HStack {
                            Button("Apply suggestions") { request.wrappedValue.ligand_atom_conditions = proposal; proposedLigandConditions = nil }
                            Button("Cancel suggestions") { proposedLigandConditions = nil }
                        }
                    }
                    ScrollView {
                    VStack(alignment: .leading, spacing: 6) {
                    ForEach(ligandInspector.sites, id: \.name) { site in
                        HStack {
                            Text(site.name).frame(width: 70, alignment: .leading)
                            ForEach(AtomCondition.allCases) { condition in
                                Toggle(condition.label, isOn: Binding(get: { value.ligand_atom_conditions?[site.name]?.contains(condition.rawValue) ?? false }, set: { on in
                                    var selected = Set(value.ligand_atom_conditions?[site.name] ?? [])
                                    if on {
                                        if condition == .exposed { selected = [] } else { selected.remove("exposed") }
                                        selected.insert(condition.rawValue)
                                    } else { selected.remove(condition.rawValue) }
                                    var conditions = value.ligand_atom_conditions ?? [:]; conditions[site.name] = selected.sorted()
                                    request.wrappedValue.ligand_atom_conditions = conditions
                                })).toggleStyle(.checkbox)
                            }
                        }
                    }
                    }
                    }.frame(maxHeight: 260)
                }
            }.padding(8)
        }
        .onAppear {
            if !ligandInspector.hasResult && !ligandInspector.isInspecting && !(value.ligand_atom_conditions ?? [:]).isEmpty {
                ligandInspector.inspectLigand(smiles: value.ligand_smiles)
            }
        }
        .onChange(of: value.ligand_smiles) { _, _ in proposedLigandConditions = nil }
        .onChange(of: value.ligand_attachment_atom) { _, _ in proposedLigandConditions = nil }
        .onChange(of: value.ligand_attachment_linker_atom) { _, _ in proposedLigandConditions = nil }
        .onChange(of: value.ligand_atom_conditions) { _, _ in proposedLigandConditions = nil }
    }
    private var epitopeForm: some View {
        Card(title: "Target binding site", systemImage: "target") {
            VStack(alignment: .leading, spacing: 8) {
                field("Epitope residues / hotspots (optional)", text: $hotspotText, hint: "Input chain and residue number, e.g. B32 C55")
                    .onChange(of: hotspotText) { _, text in updateHotspots(text) }
                Text("These residues request contacts during backbone generation. Leave empty if no epitope is known. They do not replace the search selection metric.").font(.caption).foregroundStyle(.secondary)
                Button("Select residues on target structure…") {
                    pickedResidues = value.hotspot_residues ?? []; showEpitope = true
                }.disabled(value.source.isEmpty)
                if let hotspotError { Text(hotspotError).foregroundStyle(.orange) }
            }.padding(8)
        }
    }
    @ViewBuilder private var conditionsForm: some View {
                if !value.annotated_input && value.task != .monomer {
                    DisclosureGroup("Native conditions and retained segments") {
                        VStack(alignment: .leading, spacing: 8) {
                            if value.task != .protein && value.scaffold_id == nil && value.motif == nil {
                                field("Retained residues and generated segments", text: request.contig, hint: "Optional for de novo design")
                            }
                            Text("Leave segments empty for de novo protein or ligand binders. Studio derives them from the selected target chain.").font(.caption)
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
                        Toggle("Use optimized GPU operations (default for new jobs)", isOn: request.optimized_kernels)
                        Text("Combines GPU operations while preserving the model, weights and sampling steps. The tested outputs were identical to the standard implementation, including sequences and coordinates. This is a speed option; biological accuracy was not independently compared.").font(.caption)
                        Text("Reference comparisons run during developer validation, not during your design job. Each requested design is generated once; completed outputs are checked for finite values, sequence identity and complete sampling before reuse.").font(.caption).foregroundStyle(.secondary)
                        DisclosureGroup("Measured speed and output agreement") {
                            VStack(alignment: .leading, spacing: 6) {
                                Text("M4 Max · 40 GPU cores · 64 GB · warmed 64/128-residue generation")
                                    .font(.caption.weight(.semibold))
                                Text("Triangle operations: 5.5–12.9% less generation time in the seven consistently faster test settings. One other setting was inconclusive. The added pair operations saved a further 8.2–12.2% against that triangle baseline in a separate test. These are separate comparisons, not a measured combined speedup.")
                                Text("All saved output tensors matched exactly in those comparisons (0 Å coordinate difference). For a 216-token SUMO–binder first-call check, standard/optimized generation took 41.50/41.67 seconds: identical outputs, but no speed advantage in that single comparison.")
                                Text("These timings exclude model loading, input preparation, export and downstream prediction. They do not establish a whole-workflow speedup or unchanged binding success across targets. Sources: Lab Books 0502, 0506 and 0514; details in docs/RFD4.md.")
                            }.font(.caption).foregroundStyle(.secondary)
                        }
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
                .buttonStyle(.borderedProminent).disabled(!numericValidation.invalidEditors.isEmpty || !ready || !value.validationIssues.isEmpty || !controller.canStartAnother || hotspotError != nil || checkpointError != nil || (targetFromSequence && targetPredictor.cifPath != value.source) || targetPredictor.isRunning)
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
                        Text("Boltz evaluates the selected objective. Structure profile: 3 recycles, 25 steps; affinity: 50 steps. The input molecule must match the requested graph, charge and stereochemistry.").font(.caption)
                    } else { Text("Protein rollouts use the structure predictor, alignment and selection objective chosen above.").font(.caption) }
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
                                ForEach(RFD4Predictor.allCases.filter { $0.family == family && (value.task != .ligand || $0 == .boltz || (!value.native_search && $0.family == "ESMFold2")) }) { option in
                                    Text(option.label + (installer.isUsable(option.component) ? "" : " · install in Engines")).tag(option.rawValue)
                                }
                            }
                        }
                    }
                    .onChange(of: value.predictor) { _, _ in
                        if !value.selectionMetrics.contains(value.selectedMetric) { request.wrappedValue.selection_metric = value.selectionMetrics.first }
                    }
                    Group {
                        Picker("Select candidates by (higher is better)", selection: Binding(get: { value.selectedMetric }, set: { request.wrappedValue.selection_metric = $0 })) {
                            ForEach(value.selectionMetrics, id: \.self) { metric in Text(RFD4Request.metricLabel(metric)).tag(metric) }
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
                        file("Target sequence alignment (MSA)", path: request.target_msa, singleSequence: true)
                        Text("Related protein sequences help the predictor model the target. Automatic reuses a cached alignment or requests one from the configured MSA server. Choose… imports an A3M file; Single sequence explicitly uses no evolutionary alignment. This does not align structures or select an epitope.").font(.caption).foregroundStyle(.secondary)
                        if value.task == .nanobody {
                            file("Framework sequence alignment (MSA)", path: request.scaffold_msa, singleSequence: true)
                            Text("The framework’s related sequences guide nanobody prediction. Redesigned CDR positions are masked so the starting CDR sequences do not guide the prediction. Automatic resolves the correct alignment separately for each selected framework.").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if value.task == .nanobody && value.scaffold_weights == nil { cdrFields }
                    Text("Selection maximizes " + RFD4Request.metricLabel(value.selectedMetric) + ". All proposals are saved. A missing requested metric stops selection. These scores guide design; independent validation remains separate.").font(.caption)
                }
            }.padding(8)
        }
    }

    private func field(_ title: String, text: Binding<String>, hint: String = "") -> some View {
        StudioFormField(title, explanation: hint) { TextField(title, text: text).accessibilityLabel(title) }
    }
    private var targetInput: some View {
        VStack(alignment: .leading, spacing: 10) {
            if ([.protein, .nanobody, .motif].contains(value.task) && !value.annotated_input) || (value.task == .nanobody && value.scaffold_id != nil) {
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
                Text(value.task == .motif ? "Supply the structure containing your motif. Selected residues and atoms define the motif; the rest of the source is not automatically retained." : value.task == .nanobody && value.scaffold_id != nil ? "Supply the protein you want the nanobody to bind. Studio adds the selected framework; this file is not the nanobody framework." : "Supply the target protein or protein assembly. Target chains are retained together during design.").font(.caption).foregroundStyle(.secondary)
            }
            if [.protein, .nanobody].contains(value.task) {
                DisclosureGroup("Targets containing ligands or other molecules") {
                    Text("Include the target protein and its bound small molecules in the source PDB or CIF. All non-water ligand instances are retained through generation and every prediction. Studio saves their chemistry and atom identities and checks the complete predicted assembly. SolubleMPNN and AbMPNN redesign protein sequences; they do not model ligand interactions. Covalently attached ligands and DNA/RNA need a separate workflow.").font(.caption).foregroundStyle(.secondary)
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
            Toggle("Use multiple catalogue frameworks", isOn: Binding(get: { value.scaffold_weights != nil }, set: { enabled in
                request.wrappedValue.scaffold_weights = enabled ? [value.scaffold_id ?? "7xl0_vobarilizumab": 1] : nil
                if enabled { request.wrappedValue.annotated_input = false; request.wrappedValue.scaffold_msa = "auto"; request.wrappedValue.conditions = []; request.wrappedValue.contig = ""; customCDRs = false }
            }))
            if let weights = value.scaffold_weights {
                Text("Select any frameworks and set their relative share of starting families. Equal weights give equal focus; 2 versus 1 gives twice the focus. Starts are interleaved, including timed runs. Each framework keeps its own CDR boundaries.").font(.caption).foregroundStyle(.secondary)
                ForEach(scaffolds) { scaffold in
                    HStack {
                        Toggle(scaffold.displayName, isOn: Binding(get: { value.scaffold_weights?[scaffold.id] != nil }, set: { enabled in
                            if enabled { request.wrappedValue.scaffold_weights?[scaffold.id] = 1 }
                            else { request.wrappedValue.scaffold_weights?.removeValue(forKey: scaffold.id) }
                            if let first = request.wrappedValue.scaffold_weights?.keys.sorted().first { request.wrappedValue.scaffold_id = first }
                        }))
                        if weights[scaffold.id] != nil {
                            if value.time_budget_minutes == nil { Text("\(value.frameworkCounts[scaffold.id] ?? 0) starts").font(.caption).foregroundStyle(.secondary) }
                            Stepper("Weight: \(weights[scaffold.id] ?? 1)", value: Binding(get: { value.scaffold_weights?[scaffold.id] ?? 1 }, set: { request.wrappedValue.scaffold_weights?[scaffold.id] = $0 }), in: 1...100)
                        }
                    }
                }
            } else {
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
            if !path.wrappedValue.isEmpty && path.wrappedValue != "auto" && path.wrappedValue != "empty" { Button("Clear") { path.wrappedValue = "" } }
            if singleSequence { Button("Automatic") { path.wrappedValue = "auto" }; Button("Single sequence") { path.wrappedValue = "empty" } }
        }
    }
}
