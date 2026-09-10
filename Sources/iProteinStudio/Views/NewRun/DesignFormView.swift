import SwiftUI
import UniformTypeIdentifiers

/// Guided design form. Adapts to the chosen design type (nanobody vs de-novo
/// mini-binder / peptide). Sensible defaults; advanced options tucked away.
struct DesignFormView: View {
    @EnvironmentObject var app: AppState
    let project: Project
    @ObservedObject var installer: PipelineInstaller
    @ObservedObject private var jobs = JobCenter.shared
    @ObservedObject private var run: RunController

    init(project: Project, installer: PipelineInstaller, run: RunController) {
        self.project = project
        self.installer = installer
        self.run = run
    }
    @State private var validationDestination: String?
    @State private var showAdvanced = false
    @State private var setupExperience: SetupExperience = .quick
    @State private var showTargetPrep = false
    @State private var showTargetTemplateImporter = false
    @State private var targetTemplateImportError: String?
    @StateObject private var ligandAtoms = BoltzLigandAtoms()
    @StateObject private var ligandIntelligence = LigandIntelligence()

    private var request: Binding<DesignRequest> {
        Binding(
            get: { app.projects.first(where: { $0.id == project.id })?.request ?? project.request },
            set: { nv in app.updateProject(id: project.id) { $0.request = nv } }
        )
    }

    private var type: DesignType { request.wrappedValue.designType }

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
            ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                SetupExperiencePicker(selection: $setupExperience)
                ExamplesBar { example in
                    var r = request.wrappedValue
                    r.apply(example)
                    request.wrappedValue = r
                }

                Card(title: "Design type", systemImage: "square.on.square") {
                    Picker("", selection: Binding(
                        get: { type },
                        set: { nv in
                            var r = request.wrappedValue
                            r.designType = nv
                            r.applyTypeDefaults()
                            request.wrappedValue = r
                        }
                    )) {
                        ForEach(DesignType.allCases) { Text($0.label).tag($0) }
                    }
                    .pickerStyle(.segmented).labelsHidden()
                    .accessibilityLabel("Design type")
                    Text(type.blurb).font(.caption).foregroundStyle(.secondary)
                }

                Color.clear.frame(height: 0).id("target")
                Card(title: "1 · Your target", systemImage: "target") {
                    Picker("", selection: Binding(
                        get: { request.wrappedValue.targetKind },
                        set: { nv in
                            var r = request.wrappedValue
                            r.targetKind = nv
                            r.reconcileTargetKind()
                            request.wrappedValue = r
                        }
                    )) {
                        ForEach(TargetKind.allCases) { Text($0.label).tag($0) }
                    }
                    .pickerStyle(.segmented).labelsHidden().frame(width: 320)
                    .accessibilityLabel("Target type")

                    if request.wrappedValue.targetKind == .protein {
                        Text("Paste the protein target. Separate subunits with a colon; Studio reserves chain A for the designed binder and assigns targets B, C, D…")
                            .font(.callout).foregroundStyle(.secondary)
                        ProteinChainInputView(text: request.targetSequence, startingAt: 1,
                                              placeholder: "Target chain B[:target chain C…]",
                                              minimumLength: 5)
                        VStack(alignment: .leading, spacing: 7) {
                            HStack {
                                Button {
                                    showTargetTemplateImporter = true
                                } label: {
                                    Label(request.wrappedValue.hasTargetTemplate
                                          ? "Replace target template"
                                          : "Guide target fold with PDB/CIF",
                                          systemImage: "cube.transparent")
                                }
                                if request.wrappedValue.hasTargetTemplate {
                                    Text(URL(fileURLWithPath: request.wrappedValue.targetTemplatePath).lastPathComponent)
                                        .font(.caption.monospaced()).lineLimit(1)
                                    Button("Remove") {
                                        request.wrappedValue.targetTemplatePath = ""
                                        request.wrappedValue.targetTemplateMode = .guide
                                    }
                                    .buttonStyle(.borderless)
                                }
                            }
                            Text("Optional. Guides the target chains toward an experimental or trusted predicted structure during each design cycle. Binder chain A is never templated, and independent checks remain untemplated.")
                                .font(.caption2).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                            if let error = request.wrappedValue.targetTemplateCompatibilityError {
                                Label(error, systemImage: "exclamationmark.triangle.fill")
                                    .font(.caption).foregroundStyle(.orange)
                            }
                            if let error = targetTemplateImportError {
                                Label(error, systemImage: "exclamationmark.triangle.fill")
                                    .font(.caption).foregroundStyle(.orange)
                            }
                        }
                        HStack {
                            Text("Length: \(TemplateWriter.clean(request.wrappedValue.targetSequence).count) aa")
                                .font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            TextField("Epitope hotspots (e.g. 32 55)", text: request.epitopeResidues)
                                .textFieldStyle(.roundedBorder).frame(width: 240)
                                .help("Bare residue numbers use the first target chain (B). For multimers use chain-qualified residues such as C55. Boltz and Protenix Constraint v0.5 can apply these residues.")
                                .disabled(!request.wrappedValue.supportsEpitopePocket)
                                .onChange(of: request.wrappedValue.epitopeResidues) { _, _ in
                                    var r = request.wrappedValue
                                    r.reconcilePredictors()
                                    request.wrappedValue = r
                                }
                        }
                        if request.wrappedValue.hasInvalidEpitopeResidues {
                            Label("Use residue numbers such as 32 55, or target-chain residues such as B32 C55.",
                                  systemImage: "exclamationmark.triangle.fill")
                                .font(.caption).foregroundStyle(.orange)
                        } else if request.wrappedValue.selectedDesignPredictors.count > 1 {
                            Text("Epitope guidance depends on each selected engine; see Prediction & checking below.")
                                .font(.caption).foregroundStyle(.secondary)
                        } else if request.wrappedValue.hasEpitopeSteering {
                            Label(request.wrappedValue.designPredictor == .protenixConstraint
                                  ? "Protenix Constraint will condition the proposal on its trained 8 Å token-centre pocket prior (the upstream and validated default). This is not a heavy-atom contact; the initial paired test found weak pocket steering, so it does not prove that the binder reached this epitope or that it binds."
                                  : (type == .nanobody
                                     ? "Boltz will steer the binder pocket and the centre of CDR3 toward these target residues."
                                     : "Boltz will steer the binder pocket toward these target residues."),
                                  systemImage: "scope")
                                .font(.caption).foregroundStyle(.secondary)
                        } else if request.wrappedValue.hasEnteredEpitopeResidues {
                            Label("Hotspots are saved but are not applied by \(request.wrappedValue.designPredictor.label). Choose Boltz or Protenix Constraint v0.5 to enable epitope guidance.",
                                  systemImage: "info.circle")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Button { showTargetPrep = true } label: {
                            Label("Prepare target — predict & pick hotspots", systemImage: "scope")
                        }
                        .disabled(TemplateWriter.clean(request.wrappedValue.targetSequence).count < 10)
                    } else {
                        Text("Paste a SMILES string for the small molecule you want to bind. Design uses LigandMPNN, which is ligand-aware.")
                            .font(.callout).foregroundStyle(.secondary)
                        TextField("Ligand SMILES, e.g. C=CC1=C(C)C2=N…", text: request.targetSmiles)
                            .textFieldStyle(.roundedBorder)
                            .font(.system(.body, design: .monospaced))
                        SmilesView(smiles: request.wrappedValue.targetSmiles)
                            .frame(height: 200)
                            .background(RoundedRectangle(cornerRadius: 8).fill(.background))
                            .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
                        Button { showTargetPrep = true } label: {
                            Label("Predict 3D structure of this ligand", systemImage: "cube.transparent")
                        }
                        .disabled(request.wrappedValue.targetSmiles.trimmingCharacters(in: .whitespaces).isEmpty)

                        if !request.wrappedValue.targetSmiles.trimmingCharacters(in: .whitespaces).isEmpty {
                            Divider().padding(.vertical, 4)
                            LigandTargetingView(
                                request: request,
                                atoms: ligandAtoms,
                                intelligence: ligandIntelligence,
                                outputDir: AppPaths.projectDir(project)
                                    .appendingPathComponent("ligand", isDirectory: true))
                        }
                    }
                }

                Color.clear.frame(height: 0).id("binder")
                if type.usesScaffold {
                    Card(title: "2 · Nanobody scaffolds & budget", systemImage: "cube") {
                        Text("Select the VHH frameworks to explore. CDR loops are redesigned within each selected framework.")
                            .font(.callout).foregroundStyle(.secondary)
                        ScaffoldPicker(request: request)
                    }
                    Card(title: "3 · What to design", systemImage: "slider.horizontal.3") {
                        CDRPicker(cdrs: request.cdrs)
                        if setupExperience == .advanced {
                            Divider().padding(.vertical, 4)
                            DesignerPicker(designer: request.designer,
                                           allowed: request.wrappedValue.allowedDesigners,
                                           installer: installer)
                            Divider().padding(.vertical, 4)
                            MPNNTemperatureControl(request: request)
                        }
                    }
                } else {
                    Card(title: "2 · Binder size & fold", systemImage: "ruler") {
                        BinderSizePicker(request: request)
                        Divider().padding(.vertical, 4)
                        SecondaryStructureControl(request: request,
                                                  advanced: setupExperience == .advanced)
                    }
                    if setupExperience == .advanced {
                        Card(title: "3 · Designer", systemImage: "slider.horizontal.3") {
                        DesignerPicker(designer: request.designer,
                                       allowed: request.wrappedValue.allowedDesigners,
                                       installer: installer)
                        Divider().padding(.vertical, 4)
                        MPNNTemperatureControl(request: request)
                        }
                    }
                }

                Color.clear.frame(height: 0).id("models")
                Card(title: "4 · Prediction & checking", systemImage: "checkmark.seal") {
                    PredictorPicker(request: request, installer: installer)
                }

                Card(title: "5 · Run settings", systemImage: "gauge.with.dots.needle.67percent") {
                    RunSettings(request: request)
                    if setupExperience == .advanced {
                        DisclosureGroup("Advanced", isExpanded: $showAdvanced) {
                            AdvancedSettings(request: request, projectDir: AppPaths.projectDir(project))
                        }.font(.callout)
                    }
                }
            }
            .padding(28).frame(maxWidth: 820, alignment: .leading).frame(maxWidth: .infinity)
            }
            .onChange(of: validationDestination) { _, field in
                if let field { proxy.scrollTo(field, anchor: .top); validationDestination = nil }
            }
            }
            Divider()
            startBar.padding(.horizontal, 28).padding(.vertical, 14)
                .background(.bar)
        }
        .sheet(isPresented: $showTargetPrep) {
            TargetPrepView(
                targetKind: request.wrappedValue.targetKind,
                targetSequence: request.wrappedValue.targetSequence,
                targetSmiles: request.wrappedValue.targetSmiles,
                onUse: { residues in
                    var r = request.wrappedValue
                    r.epitopeResidues = residues.joined(separator: " ")
                    r.reconcilePredictors()
                    request.wrappedValue = r
                },
                onClose: { showTargetPrep = false }
            )
        }
        .fileImporter(isPresented: $showTargetTemplateImporter,
                      allowedContentTypes: [.data], allowsMultipleSelection: false) { result in
            importTargetTemplate(result)
        }
    }

    private func importTargetTemplate(_ result: Result<[URL], Error>) {
        do {
            guard let source = try result.get().first else { return }
            let ext = source.pathExtension.lowercased()
            guard ["pdb", "cif", "mmcif"].contains(ext) else {
                throw NHError.message("Choose a .pdb, .cif, or .mmcif structure file.")
            }
            let accessed = source.startAccessingSecurityScopedResource()
            defer { if accessed { source.stopAccessingSecurityScopedResource() } }
            let directory = AppPaths.projectDir(project)
                .appendingPathComponent("target_templates", isDirectory: true)
            try AppPaths.fm.createDirectory(at: directory, withIntermediateDirectories: true)
            let destination = directory.appendingPathComponent("target-\(UUID().uuidString).\(ext)")
            try AppPaths.fm.copyItem(at: source, to: destination)
            var updated = request.wrappedValue
            updated.targetTemplatePath = destination.path
            updated.targetTemplateMode = .guide
            request.wrappedValue = updated
            targetTemplateImportError = nil
        } catch {
            targetTemplateImportError = error.localizedDescription
        }
    }

    private var quickModelSummary: String {
        let r = request.wrappedValue
        let checks = r.effectivePostPredictors.isEmpty
            ? "no extra checker"
            : r.effectivePostPredictors.map(\.label).joined(separator: ", ")
        return "\(r.designer.label) designs; \(r.designEngineSummary) guide each cycle; \(checks)."
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(project.name).font(.largeTitle.bold())
            Text("Set up your design run, then press Start.").foregroundStyle(.secondary)
        }
    }

    private var startBar: some View {
        let willQueue = !jobs.active.isEmpty || run.isRunning || app.rfd3.isRunning || app.prediction.isRunning || app.nise.isRunning
        let missingComponents = request.wrappedValue.requiredComponents.filter {
            !installer.isUsable($0)
        }
        return HStack(spacing: 12) {
            let r = request.wrappedValue
            if !r.isRunnable || r.ligandAtomsStale || !missingComponents.isEmpty {
                Label(missingReason(r, missingComponents: missingComponents), systemImage: "info.circle")
                    .font(.callout).foregroundStyle(.secondary)
            } else if willQueue {
                Label("Your settings will be saved. This run will wait until the active job releases the GPU.", systemImage: "hourglass")
                    .font(.callout).foregroundStyle(.secondary)
            }
            if let issue = r.validationIssues.first {
                Button("Review field") { validationDestination = issue.field }
                    .accessibilityLabel("Review \(issue.field): \(issue.message)")
            }
            Spacer()
            RunNameField(project: project, mode: .iterative)
            Button {
                app.metrics.stop()
                let current = app.projects.first(where: { $0.id == project.id }) ?? project
                app.run.start(project: current, name: current.runNames[WorkspaceMode.iterative.rawValue] ?? "")
                if let root = app.run.campaignRoot { app.metrics.start(root: root) }
            } label: {
                Label(willQueue ? "Add to Queue" : "Start Design Run", systemImage: willQueue ? "text.badge.plus" : "play.fill").frame(minWidth: 200)
            }
            .buttonStyle(.borderedProminent).controlSize(.large)
            .accessibilityLabel(willQueue ? "Add Protein Hunter run to queue" : "Start Protein Hunter run")
            .accessibilityIdentifier("start-iterative-run")
            .disabled(!r.isRunnable || r.ligandAtomsStale || !missingComponents.isEmpty || !run.canStartAnother)
        }
        .padding(.top, 6)
    }

    private func missingReason(_ r: DesignRequest, missingComponents: [InstallComponent] = []) -> String {
        if let issue = r.validationIssues.first { return issue.message }
        if !missingComponents.isEmpty { return "Install \(missingComponents.map(\.label).joined(separator: ", ")) in Engines before starting." }
        return "Review the highlighted settings before starting."
    }

}

// MARK: - Building blocks

struct Card<Content: View>: View {
    let title: String; let systemImage: String
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(title, systemImage: systemImage).font(.title3.bold())
            content
        }
        .padding(18).frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 12).fill(.quaternary.opacity(0.4)))
    }
}

struct SequenceEditor: View {
    @Binding var text: String
    let placeholder: String
    var body: some View {
        ZStack(alignment: .topLeading) {
            if text.isEmpty { Text(placeholder).foregroundStyle(.tertiary).padding(8) }
            TextEditor(text: $text)
                .font(.system(.body, design: .monospaced)).frame(minHeight: 72)
                .scrollContentBackground(.hidden).padding(4)
        }
        .background(RoundedRectangle(cornerRadius: 8).fill(.background))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
        .accessibilityLabel(placeholder)
        .accessibilityHint("Enter an amino-acid sequence using one-letter codes")
    }
}

struct ScaffoldPicker: View {
    @EnvironmentObject var app: AppState
    @Binding var request: DesignRequest
    private var rows: [NanobodyScaffoldAllocation] {
        let selected = request.allocatedScaffolds
        let catalog = app.scaffolds.map { scaffold in
            selected.first(where: { $0.id == scaffold.id }) ?? .init(id: scaffold.id,
                name: scaffold.displayName, sequence: scaffold.sequence, trajectories: 0)
        }
        return catalog + selected.filter { item in !catalog.contains { $0.id == item.id } }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Total trajectories per engine")
                if request.equalScaffoldBudgets {
                    EditableIntStepper(value: $request.numDesigns,
                        in: max(1, request.allocatedScaffolds.count)...(10_000 * max(1, request.allocatedScaffolds.count)),
                        accessibilityLabel: "Total trajectories across nanobody scaffolds per engine")
                } else {
                    Text("\(request.numDesigns)").monospacedDigit()
                    Text("sum of scaffold budgets").font(.caption).foregroundStyle(.secondary)
                }
            }
            Toggle("Split trajectories equally", isOn: Binding(
                get: { request.equalScaffoldBudgets },
                set: { request.setEqualScaffoldBudgets($0) }))
            Text(request.equalScaffoldBudgets
                 ? "The total is shared across selected scaffolds. Any remainder goes to the first selected scaffolds. Selecting more scaffolds raises the total if needed to give each at least one trajectory."
                 : "Edit each scaffold’s budget below. The total updates automatically; changing the selection preserves the other custom budgets.")
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                Button("Select all") {
                    for scaffold in app.scaffolds {
                        request.setScaffold(id: scaffold.id, name: scaffold.displayName,
                                            sequence: scaffold.sequence, selected: true)
                    }
                }
                Button("Clear selection") {
                    request.scaffoldSelections = []
                    if !request.equalScaffoldBudgets { request.numDesigns = 0 }
                }
                Spacer()
                Text("\(request.allocatedScaffolds.count) selected").font(.caption)
            }
            ForEach(rows) { scaffold in
                let selected = request.allocatedScaffolds.contains { $0.id == scaffold.id }
                HStack(alignment: .top) {
                    Toggle(isOn: Binding(get: { selected }, set: {
                        request.setScaffold(id: scaffold.id, name: scaffold.name,
                                            sequence: scaffold.sequence, selected: $0)
                    })) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(app.scaffolds.first { $0.id == scaffold.id }?.displayName ?? scaffold.name)
                            if let catalog = app.scaffolds.first(where: { $0.id == scaffold.id }) {
                                Text(catalog.recommendedUse).font(.caption).foregroundStyle(.secondary)
                                if selected && catalog.sequence != scaffold.sequence {
                                    Text("Using the framework sequence saved in this workspace.").font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }.toggleStyle(.checkbox)
                    Spacer()
                    if selected {
                        if request.equalScaffoldBudgets {
                            Text("\(scaffold.trajectories) trajectories").monospacedDigit().font(.callout)
                        } else {
                            EditableIntStepper(value: Binding(get: {
                                request.allocatedScaffolds.first { $0.id == scaffold.id }?.trajectories ?? 1
                            }, set: { request.setScaffoldBudget(id: scaffold.id, trajectories: $0) }),
                            in: 1...10_000, suffix: "trajectories",
                            accessibilityLabel: "Trajectories for \(scaffold.name)")
                        }
                    }
                }
            }
            Text("For example: 70 trajectories across seven selected scaffolds gives 10 each. Each selected engine receives this same allocation, with separate results for every engine and scaffold.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .onAppear {
            if request.scaffoldSelections == nil {
                var selected = request.allocatedScaffolds
                for i in selected.indices {
                    if let catalog = app.scaffolds.first(where: { $0.id == selected[i].id }) {
                        selected[i].name = catalog.displayName
                    }
                }
                request.scaffoldSelections = selected
            }
        }
    }
}

struct BinderSizePicker: View {
    @Binding var request: DesignRequest
    var body: some View {
        Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 10) {
            GridRow {
                Text("Shortest")
                EditableIntStepper(value: $request.binderMinLen,
                                   in: 1...min(300, request.binderMaxLen),
                                   suffix: "aa", accessibilityLabel: "Shortest binder length")
            }
            GridRow {
                Text("Longest")
                EditableIntStepper(value: $request.binderMaxLen,
                                   in: request.binderMinLen...400,
                                   suffix: "aa", accessibilityLabel: "Longest binder length")
            }
        }
        Text("Each design gets a random length in this range.").font(.caption).foregroundStyle(.secondary)
    }
}

/// Sequence-level priors for de-novo fold exploration. The UI never describes
/// these as a structural guarantee: the resulting fold must be assessed from
/// predicted coordinates.
struct SecondaryStructureControl: View {
    @Binding var request: DesignRequest
    let advanced: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Helix-kill strength").font(.headline)
            strengthRow("Strength", value: $request.helixKill)
            Text("Reduces helix-favoring patterns in the starting sequence. Zero disables it. Later optimization cycles use normal MPNN sampling.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if let error = request.secondaryStructureCompatibilityError {
                Text(error).font(.caption).foregroundStyle(.orange)
                Button("Use initialization-only helix kill") {
                    request.secondaryStructureBias = .none
                    request.secondaryStructureBiasScope = .seedOnly
                }
            }
        }
    }

    @ViewBuilder
    private func strengthRow(_ label: String, value: Binding<Double>) -> some View {
        HStack(spacing: 10) {
            Text(label).frame(width: 150, alignment: .leading)
            Slider(value: value, in: 0...1, step: 0.05)
                .accessibilityLabel(label)
                .accessibilityValue(String(format: "%.0f percent", value.wrappedValue * 100))
            Text(String(format: "%.0f%%", value.wrappedValue * 100))
                .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                .frame(width: 40, alignment: .trailing)
        }
    }
}

struct CDRPicker: View {
    @Binding var cdrs: CDRSelection
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("CDR loops to redesign").font(.headline)
            HStack(spacing: 16) {
                Toggle("CDR1", isOn: $cdrs.cdr1)
                Toggle("CDR2", isOn: $cdrs.cdr2)
                Toggle("CDR3", isOn: $cdrs.cdr3)
            }.toggleStyle(.checkbox)
            Text("CDR3 is the main binding loop and the usual default.").font(.caption).foregroundStyle(.secondary)
        }
    }
}

struct DesignerPicker: View {
    @Binding var designer: SequenceDesigner
    var allowed: [SequenceDesigner]
    var installer: PipelineInstaller?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Sequence designer").font(.headline)
            Picker("Designer", selection: $designer) {
                ForEach(allowed) { Text($0.label).tag($0) }
            }
            .pickerStyle(.segmented)
            .onAppear { if !allowed.contains(designer) { designer = allowed.first ?? .solublempnn } }
            Text(designer.blurb).font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if designer.runsOnCPU {
                Label("Runs on the CPU — there is no Apple GPU build. It is a few seconds per design, so it is not the bottleneck.",
                      systemImage: "cpu")
                    .font(.caption2).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let installer, !installer.isUsable(designer.component) {
                Label("\(designer.label) isn't installed yet — add it from Setup.",
                      systemImage: "exclamationmark.triangle.fill")
                    .font(.caption).foregroundStyle(.orange)
            }
        }
    }
}

/// Redesign temperature. Higher explores more sequence space; lower refines what
/// is already there. Cycle 1 runs hotter than later cycles by default, which is
/// the pipeline's own behaviour rather than a Studio invention.
struct MPNNTemperatureControl: View {
    @Binding var request: DesignRequest

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Redesign temperature").font(.headline)
            Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 8) {
                GridRow {
                    Text("First cycle").font(.callout)
                    Slider(value: $request.mpnnTempCycle1, in: 0.05...1.0, step: 0.05).frame(width: 200)
                    .accessibilityLabel("First redesign sampling temperature")
                    Text(String(format: "%.2f", request.mpnnTempCycle1))
                        .font(.callout.monospacedDigit()).frame(width: 44, alignment: .trailing)
                }
                GridRow {
                    Text("Later cycles").font(.callout)
                    Slider(value: $request.mpnnTempLater, in: 0.05...1.0, step: 0.05).frame(width: 200)
                    .accessibilityLabel("Later redesign sampling temperature")
                    Text(String(format: "%.2f", request.mpnnTempLater))
                        .font(.callout.monospacedDigit()).frame(width: 44, alignment: .trailing)
                }
            }
            Text("Higher explores more sequences; lower refines the one you have. The defaults start hot (0.30) and cool to 0.10.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if request.designer == .lasermpnn {
                Divider().padding(.vertical, 2)
                Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 8) {
                    GridRow {
                        Text("LASErMPNN sequence").font(.callout)
                        Slider(value: $request.lasermpnnSeqTemp, in: 0.05...1.0, step: 0.05).frame(width: 200)
                        .accessibilityLabel("Sequence sampling temperature")
                        Text(String(format: "%.2f", request.lasermpnnSeqTemp))
                            .font(.callout.monospacedDigit()).frame(width: 44, alignment: .trailing)
                    }
                    GridRow {
                        Text("Binding site").font(.callout)
                        Slider(value: $request.lasermpnnFirstShellTemp, in: 0.1...2.0, step: 0.1).frame(width: 200)
                        .accessibilityLabel("First shell sampling temperature")
                        Text(String(format: "%.2f", request.lasermpnnFirstShellTemp))
                            .font(.callout.monospacedDigit()).frame(width: 44, alignment: .trailing)
                    }
                }
                Text("LASErMPNN chooses side-chain positions as well as residues, so the pocket has its own temperature.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

/// Design predictor + orthogonal checking predictors.
///
/// The framing matters scientifically. The design loop optimises sequences
/// against whichever predictor drives it, so that predictor's own confidence is
/// self-scored and is the number most at risk of being gamed. An independent
/// re-fold is the honest measure, so the UI presents post-prediction as
/// "checking" rather than as an optional extra, and pre-selects one.
struct PredictorPicker: View {
    @Binding var request: DesignRequest
    @ObservedObject var installer: PipelineInstaller

    private var checkChoices: [Predictor] {
        // Everything that can re-fold, minus whichever engine did the designing —
        // a predictor cannot independently check its own work.
        Predictor.iterativeCheckChoices.filter { checker in
            request.selectedDesignPredictors.contains { $0.independenceIdentity != checker.independenceIdentity }
        }
    }

    private var designChoices: [DesignEngine] {
        DesignEngine.choices + request.selectedDesignEngines.filter { !DesignEngine.choices.contains($0) }
    }

    private var allowedDesignChoices: [Predictor] {
        if request.hasTargetTemplate {
            if request.targetTemplateMode == .strong {
                return [.boltz, .boltzPotentials]
            }
            return [.boltz, .boltzPotentials, .protenixV2, .intellifold]
        }
        if request.targetKind == .ligand && !request.ligandContactAtoms.isEmpty {
            return request.ligandContactForce ? [.boltzPotentials] : [.boltz, .boltzPotentials]
        }
        return request.targetKind == .ligand
            ? Predictor.designChoices.filter { $0 != .protenixConstraint }
            : Predictor.designChoices
    }

    private var usesIntelliFold: Bool {
        request.usesIntelliFold
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // --- Design predictor ---
            VStack(alignment: .leading, spacing: 8) {
                Text("Design engines").font(.headline)
                Text("Each selected engine runs these settings for \(request.numDesigns) trajectories. Engines run in checklist order with separate results. Nanobody budgets are shared across the selected scaffolds.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                ForEach(designChoices) { p in
                    Toggle(isOn: Binding(
                        get: { request.selectedDesignEngines.contains(p) },
                        set: { request.setDesignEngine(p, selected: $0) }
                    )) {
                        HStack(spacing: 6) {
                            Text(p.label)
                            if !allowedDesignChoices.contains(p.predictor) {
                                Text("incompatible with targeting settings").font(.caption2).foregroundStyle(.orange)
                            } else if !installer.isUsable(p.component) {
                                Text("not installed").font(.caption2).foregroundStyle(.orange)
                            }
                        }
                    }
                    .toggleStyle(.checkbox)
                    .accessibilityIdentifier("design-engine-\(p.rawValue)")
                    .disabled((!allowedDesignChoices.contains(p.predictor) || !installer.isUsable(p.component))
                              && !request.selectedDesignEngines.contains(p))
                    .help(p.caveat.isEmpty ? p.blurb : p.caveat)
                }
                if request.selectedDesignPredictors.isEmpty {
                    Label("Select at least one design engine.", systemImage: "exclamationmark.circle")
                        .font(.caption).foregroundStyle(.orange)
                }
                if request.hasEnteredEpitopeResidues {
                    ForEach(request.selectedDesignEngines) { p in
                        Text(p.supportsEpitopePocket
                             ? "\(p.label) applies its supported epitope guidance."
                             : "\(p.label) folds the full target; the saved epitope hotspots are not applied.")
                            .font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }

            Divider()

            if request.targetKind == .ligand {
                LigandNessoOptionsView(options: $request.nesso,
                    explanation: "After each engine campaign finishes, rank all optimized cycle designs with NESSO and fold its top sequences. Cycle 00 starting structures are excluded. The shortlist limit applies separately to each engine campaign.")
                Divider()
            }

            // --- Orthogonal checking ---
            VStack(alignment: .leading, spacing: 8) {
                Text("Check hits with").font(.headline)
                Text("Applies to every engine campaign. Each campaign excludes its own design model from this list; that model can still check campaigns designed by other engines.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                ForEach(checkChoices) { p in
                    Toggle(isOn: Binding(
                        get: { request.effectivePostPredictors.contains(p) },
                        set: { on in
                            if on { request.postPredictors.append(p.checkingVariant) }
                            else { request.postPredictors.removeAll { $0.checkingVariant == p } }
                            request.reconcilePredictors()
                        }
                    )) {
                        HStack(spacing: 6) {
                            Text(p.label)
                            speedTag(p)
                            if !installer.isUsable(p.component) {
                                Label("not installed", systemImage: "exclamationmark.circle")
                                    .font(.caption2).foregroundStyle(.orange).labelStyle(.titleAndIcon)
                            }
                        }
                    }
                    .toggleStyle(.checkbox)
                    // A missing saved checker can still be turned off. Only
                    // turning on a checker that cannot run is blocked.
                    .disabled(!installer.isUsable(p.component)
                              && !request.effectivePostPredictors.contains(p))
                    .help(p.caveat.isEmpty ? p.blurb : p.caveat)
                }

                if request.selectedDesignEngines.count > 1 {
                    ForEach(request.selectedDesignEngines) { engine in
                        let checks = request.forDesignEngine(engine).effectivePostPredictors
                        Text("\(engine.label) designs: " + (checks.isEmpty
                             ? "no independent checker selected"
                             : "checked with " + checks.map(\.label).joined(separator: ", ")))
                            .font(.caption2)
                            .foregroundStyle(checks.isEmpty ? Color.orange : Color.secondary)
                    }
                }
                if request.effectivePostPredictors.isEmpty {
                    Label("Without an independent check you only have the design engine's own opinion of its designs.",
                          systemImage: "exclamationmark.triangle.fill")
                        .font(.caption).foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    Picker("Check checkpoints", selection: $request.postCheckScope) {
                        Text("Final only (cycle \(String(format: "%02d", request.numCycles)))")
                            .tag(PostCheckScope.finalCycle)
                        Text("All design cycles (01–\(String(format: "%02d", request.numCycles)))")
                            .tag(PostCheckScope.allCycles)
                    }
                    .pickerStyle(.segmented)
                    if request.postCheckScope == .allCycles {
                        Text("Checks every optimized checkpoint. The unoptimized cycle 00 seed is excluded.")
                            .font(.caption2).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Toggle("Only check checkpoints that pass the hit threshold", isOn: $request.postOnlyHits)
                        .toggleStyle(.checkbox).font(.callout)

                    Toggle("Also predict each binder by itself", isOn: $request.postRunBinderAlone)
                        .toggleStyle(.checkbox).font(.callout)
                    Text("Compares the binder-alone fold with its conformation in the independently predicted complex. This adds one fold per checked design and engine.")
                        .font(.caption2).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)

                    DisclosureGroup("Hit filters") {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("A hit must pass every enabled gate. Clear a field to disable it; the saved values and score engine remain in the result provenance.")
                                .font(.caption2).foregroundStyle(.secondary)
                            Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 7) {
                                designFilterRow("Minimum post iPTM", value: $request.postFilters.minimumIPTM)
                                designFilterRow("Minimum post ipSAE(min)", value: $request.postFilters.minimumIPSAEMin)
                                designFilterRow("Maximum target-aligned binder RMSD", value: $request.postFilters.maximumComplexRMSD, suffix: "Å")
                                designFilterRow("Minimum binder pLDDT", value: $request.postFilters.minimumBinderPLDDT)
                                designFilterRow("Maximum binder-alone RMSD", value: $request.postFilters.maximumBinderRMSD, suffix: "Å")
                            }
                            if !request.postRunBinderAlone {
                                Text("Binder pLDDT and binder-alone RMSD gates are ignored while binder-alone prediction is off.")
                                    .font(.caption2).foregroundStyle(.orange)
                            }
                        }.padding(.top, 6)
                    }
                }

                if request.effectivePostPredictors.contains(.intellifold) {
                    Picker("IntelliFold checking model", selection: Binding(
                        get: { request.intellifoldModel ?? .v2flash },
                        set: {
                            // Freeze design choices before changing the independent checker.
                            request.designEngines = request.selectedDesignEngines
                            request.intellifoldModel = $0
                        }
                    )) {
                        ForEach(IntelliFoldModel.allCases) { model in
                            Text(model.label).tag(model)
                        }
                    }
                    .pickerStyle(.menu)
                    Text("Applies to independent IntelliFold checks. Design Flash and Full checkpoints are selected separately above and do not check each other independently.")
                        .font(.caption2).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Divider()
            estimate
        }
    }

    @ViewBuilder private func designFilterRow(_ label: String, value: Binding<Double?>,
                                               suffix: String = "") -> some View {
        GridRow {
            Text(label).font(.caption)
            HStack(spacing: 5) {
                TextField("Off", value: value, format: .number.precision(.fractionLength(0...2)))
                    .textFieldStyle(.roundedBorder).frame(width: 72)
                if !suffix.isEmpty { Text(suffix).font(.caption).foregroundStyle(.secondary) }
            }
        }
    }

    @ViewBuilder private func predictorNote(_ p: Predictor, isDesign: Bool) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(p.blurb).font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if !p.caveat.isEmpty {
                Label(p.caveat, systemImage: "info.circle")
                    .font(.caption2).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if isDesign, !installer.isUsable(p.component) {
                let detail = installer.detail(p.component)
                Label(detail.isEmpty ? "\(p.label) is not installed yet — add it from Setup." : detail,
                      systemImage: "exclamationmark.triangle.fill")
                    .font(.caption).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// A band and a bar, not a number: the seconds move with scheduling mode,
    /// token count, recycles and machine, so a precise multiplier on screen
    /// would be false precision.
    @ViewBuilder private func speedTag(_ p: Predictor) -> some View {
        if request.intellifoldModel == .v2
            && p == .intellifold {
            Text("not benchmarked").font(.caption).foregroundStyle(.secondary)
        } else {
            let band = p.speed(in: .batched)
            HStack(spacing: 4) {
                ForEach(0..<4, id: \.self) { i in
                    RoundedRectangle(cornerRadius: 1)
                        .fill(i < band.bars ? Color.secondary : Color.secondary.opacity(0.18))
                        .frame(width: 4, height: 8)
                }
                Text(band.label).font(.caption).foregroundStyle(.secondary)
            }
            .help("Relative speed on the v2-flash reference benchmark at this engine's best schedule.")
        }
    }

    /// Prediction-only planning number: assumes every eligible checkpoint is checked,
    /// while explicitly excluding MSA generation and inverse folding.
    private var estimate: some View {
        if request.targetKind == .ligand && request.nesso.enabled {
            return AnyView(Label("No total time estimate: NESSO campaign screening has not been benchmarked on this Mac.", systemImage: "clock")
                .font(.callout).foregroundStyle(.secondary))
        }
        let fullV2Selected = request.usesFullIntelliFold
        if fullV2Selected {
            return AnyView(Label {
                Text("No time estimate: full IntelliFold v2 has not been benchmarked on this Mac yet.")
            } icon: {
                Image(systemName: "clock")
            }
            .font(.callout)
            .foregroundStyle(.secondary))
        }
        let seconds = request.estimatedPredictionSeconds
        return AnyView(Label {
            Text("Prediction-only planning estimate: \(formatted(seconds)) if every eligible checkpoint is checked. Hit gating can shorten it; MSA setup can add time.")
        } icon: {
            Image(systemName: "clock")
        }
        .font(.callout)
        .foregroundStyle(.secondary))
    }

    private func formatted(_ seconds: Double) -> String {
        if seconds < 90 { return "\(Int(seconds.rounded())) s" }
        if seconds < 5400 { return String(format: "%.0f min", seconds / 60) }
        return String(format: "%.1f h", seconds / 3600)
    }
}

struct RunSettings: View {
    @Binding var request: DesignRequest
    var body: some View {
        Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 12) {
            GridRow {
                Text("Trajectories per engine")
                if request.designType == .nanobody {
                    Text("\(request.numDesigns) across \(request.allocatedScaffolds.count) scaffolds")
                        .monospacedDigit()
                } else {
                    EditableIntStepper(value: $request.numDesigns, in: 1...96,
                                       accessibilityLabel: "Trajectories per design engine")
                }
            }
            GridRow {
                Text("Optimization cycles")
                EditableIntStepper(value: $request.numCycles, in: 1...20,
                                   accessibilityLabel: "Optimization cycles")
            }
            GridRow {
                Text("Hit threshold (iPTM)")
                HStack {
                    Slider(value: $request.hitThreshold, in: 0.3...0.95, step: 0.01).frame(width: 220)
                    .accessibilityLabel("Minimum interface confidence for a hit")
                    Text(String(format: "%.2f", request.hitThreshold)).monospacedDigit()
                }
            }
        }
        Text("\(request.selectedDesignEngines.count) engine(s) × \(request.numDesigns) trajectories each = \(request.totalTrajectories) total trajectories. This produces \(request.expectedOptimizedDesigns) optimized design structures across cycles 01–\(String(format: "%02d", request.numCycles)), plus \(request.expectedStartingStructures) unoptimized cycle-00 starting structure\(request.expectedStartingStructures == 1 ? "" : "s").")
            .font(.caption2)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
        Label("Automatic scheduling: Protenix v2 is loaded once per cycle; other engines keep one resident predictor loaded across their campaign.",
              systemImage: "bolt.fill")
            .font(.caption)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
    }
}

struct AdvancedSettings: View {
    @Binding var request: DesignRequest
    let projectDir: URL
    @StateObject private var calibration = CalibrationRunner()
    @State private var availBytes: UInt64 = SystemMemory.availableBytes()

    private var totalBytes: UInt64 { SystemMemory.totalBytes() }
    private var cpuCount: Int { ProcessInfo.processInfo.activeProcessorCount }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // --- Recovery ---
            VStack(alignment: .leading, spacing: 6) {
                Text("Recovery").font(.headline)
                Toggle("Reuse finished work if this run is restarted", isOn: $request.resumeIfPossible)
                    .toggleStyle(.checkbox).font(.callout)
                Text("Long campaigns get interrupted. With this on, completed cycles, sequences and checks are read back from disk instead of recomputed.")
                    .font(.caption2).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Divider()

            // --- Automatic scheduling ---
            VStack(alignment: .leading, spacing: 6) {
                Text("Automatic scheduling").font(.headline)
                Label("Each engine uses its existing policy: Protenix v2 uses directory waves per cycle; other engines retain a resident worker across their campaign.",
                      systemImage: "bolt.fill")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Text("Studio selects the validated policy automatically. Historical per-trajectory scheduling remains available only from the CLI for controlled diagnostics.")
                    .font(.caption2).foregroundStyle(.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Divider()

            // --- System memory ---
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text("System memory").font(.headline)
                    Spacer()
                    Button { availBytes = SystemMemory.availableBytes() } label: {
                        Image(systemName: "arrow.clockwise")
                    }.buttonStyle(.borderless).help("Refresh available memory")
                }
                HStack(spacing: 14) {
                    memStat("Total RAM", SystemMemory.gbString(totalBytes))
                    memStat("Available now", SystemMemory.gbString(availBytes))
                    memStat("CPU cores", "\(cpuCount)")
                }
                Text("Available memory (free + inactive + speculative) is what the pipeline checks against when choosing how many predictions to run at once.")
                    .font(.caption2).foregroundStyle(.secondary)
            }
            Divider()

            // --- Calibration ---
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("Calibration").font(.headline)
                    Spacer()
                    if calibration.isRunning {
                        ProgressView().controlSize(.small)
                        Button("Cancel") { calibration.cancel() }.controlSize(.small)
                    } else {
                        Button { availBytes = SystemMemory.availableBytes()
                                 calibration.run(request: request, projectDir: projectDir) } label: {
                            Label("Run calibration", systemImage: "gauge.with.dots.needle.67percent")
                        }.disabled(!request.isRunnable)
                    }
                }
                Text("Runs one heaviest-case prediction (longest binder + your target, on Boltz) to measure peak memory and confirm that the campaign fits on this Mac.")
                    .font(.caption).foregroundStyle(.secondary)
                calibrationResults
            }

            Divider()
            DisclosureGroup("What settings will actually be used") {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach((request.selectedDesignPredictors + request.effectivePostPredictors)
                        .reduce(into: [Predictor]()) { acc, p in if !acc.contains(p) { acc.append(p) } }) { p in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(p.label).font(.caption.weight(.medium))
                            ForEach(p.settingsSummary, id: \.self) { line in
                                Text("• " + line).font(.caption2).foregroundStyle(.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                    Text("Concurrency comes from the measured per-machine profile when one matches this Mac, and from a live memory check otherwise.")
                        .font(.caption2).foregroundStyle(.tertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.top, 8)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .font(.callout)

            VStack(alignment: .leading, spacing: 4) {
                Text("Design engines: \(request.designEngineSummary) · Checked with: "
                     + (request.effectivePostPredictors.isEmpty
                        ? "nothing"
                        : request.effectivePostPredictors.map(\.label).joined(separator: ", ")))
                    .font(.caption).foregroundStyle(.secondary)
                Text("Token bucketing, the JAX compile cache and per-predictor thread limits are always on — measured free wins with nothing useful to decide about them.")
                    .font(.caption2).foregroundStyle(.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.top, 6)
    }

    @ViewBuilder private var calibrationResults: some View {
        switch calibration.phase {
        case .idle: EmptyView()
        case .running:
            Text(calibration.log.last ?? "Running…").font(.caption2).foregroundStyle(.secondary).lineLimit(1)
        case .failed(let msg):
            Label(msg, systemImage: "exclamationmark.triangle.fill")
                .font(.caption).foregroundStyle(.orange).fixedSize(horizontal: false, vertical: true)
        case .done:
            VStack(alignment: .leading, spacing: 4) {
                if let n = calibration.suggestedParallel {
                    Label("Suggested: run \(n) prediction\(n == 1 ? "" : "s") at once", systemImage: "checkmark.seal.fill")
                        .font(.callout).foregroundStyle(.green)
                }
                ForEach(calibration.metrics) { m in
                    HStack {
                        Text(m.label).font(.caption).foregroundStyle(.secondary)
                        Spacer()
                        Text(m.value).font(.caption.monospacedDigit())
                    }
                }
            }
            .padding(10)
            .background(RoundedRectangle(cornerRadius: 8).fill(.quaternary.opacity(0.35)))
        }
    }

    private func memStat(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(value).font(.callout.bold()).monospacedDigit()
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(8)
        .background(RoundedRectangle(cornerRadius: 8).fill(.quaternary.opacity(0.3)))
    }
}
