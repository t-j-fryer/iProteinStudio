import SwiftUI
import UniformTypeIdentifiers

/// The RFdiffusion3 tab: generate binder backbones against a protein or a small
/// molecule, design sequences onto them, and verify with independent predictors.
///
/// Two deliberate constraints shape this screen:
///
/// * The conditioning vocabulary is read out of the target, never typed. An atom
///   name that does not exist would produce an unconditioned design that looks
///   like a success.
/// * Sampling settings default to measured optima and say so. Batch size in
///   particular must not be derived from free memory: peak footprint barely
///   moved between batch 1 and 32 while throughput collapsed above 8.
struct RFD3View: View {
    @EnvironmentObject var app: AppState
    let project: Project
    @ObservedObject var controller: RFD3Controller
    @ObservedObject var installer: PipelineInstaller
    @StateObject private var inspector = RFD3TargetInspector()
    @StateObject private var intelligence = LigandIntelligence()
    @State private var showAdvanced = false
    @State private var setupExperience: SetupExperience = .quick
    @State private var showTargetPrep = false
    @State private var proposedConditions: [String: Set<AtomCondition>]?

    private var request: Binding<RFD3Request> {
        Binding(
            get: { app.selectedProject?.rfd3 ?? project.rfd3 },
            set: { nv in app.updateSelected { $0.rfd3 = nv } }
        )
    }

    var body: some View {
        Group {
            if controller.isRunning || controller.campaignRoot != nil {
                RFD3ProgressView(controller: controller)
            } else if let reason = RFD3Controller.unavailableReason {
                unavailable(reason)
            } else {
                form
            }
        }
        .onChange(of: request.wrappedValue.attachmentAtom) { _, _ in
            proposedConditions = nil
        }
        .onChange(of: request.wrappedValue.attachmentLinkerAtom) { _, _ in
            proposedConditions = nil
        }
    }

    // MARK: Unavailable

    private func unavailable(_ reason: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "shippingbox")
                .font(.system(size: 48)).foregroundStyle(.secondary)
            Text("RFdiffusion3 isn't ready").font(.title2.bold())
            Text(reason)
                .foregroundStyle(.secondary).multilineTextAlignment(.center)
                .frame(maxWidth: 420).fixedSize(horizontal: false, vertical: true)
            if let existing = installer.detectedRFD3 {
                Button {
                    installer.linkExisting(nanoHunter: nil, rfd3: existing)
                } label: {
                    Label("Use the RFdiffusion3 at \(existing.lastPathComponent)", systemImage: "link")
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding(40).frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: Form

    private var form: some View {
        VStack(spacing: 0) {
            ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                SetupExperiencePicker(selection: $setupExperience)
                ExamplesBar { example in
                    request.wrappedValue.apply(example)
                    inspector.reset()
                    intelligence.reset()
                }

                Card(title: "1 · What are you designing against?", systemImage: "target") {
                    targetKindPicker
                    if request.wrappedValue.targetKind == .smallMolecule {
                        ligandInput
                    } else {
                        proteinInput
                    }
                }

                if request.wrappedValue.targetKind == .smallMolecule,
                   request.wrappedValue.ligandSource == .smiles,
                   !request.wrappedValue.smiles.trimmingCharacters(in: .whitespaces).isEmpty {
                    Card(title: "2 · Understand the molecule", systemImage: "sparkles.rectangle.stack") {
                        LigandIntelligenceView(
                            intelligence: intelligence,
                            request: request,
                            outputDir: AppPaths.projectDir(project)
                                .appendingPathComponent("rfd3/assets/conformers", isDirectory: true),
                            atomLabels: inspector.atomLabels)
                    }
                }

                if inspector.hasResult || inspector.isInspecting || inspector.error != nil {
                    Card(title: "3 · Shape the binding site", systemImage: "hand.point.up.left") {
                        conditioningSection
                    }
                }

                Card(title: "4 · Binder size", systemImage: "ruler") {
                    lengthSection
                }

                if setupExperience == .advanced {
                    Card(title: "5 · Sequence design", systemImage: "textformat.abc") {
                        sequenceDesignSection
                    }
                } else {
                    Label("\(request.wrappedValue.sequenceModel.label) will design \(request.wrappedValue.sequencesPerBackbone) sequence(s) per backbone using its recommended temperatures.",
                          systemImage: "textformat.abc")
                        .font(.caption).foregroundStyle(.secondary)
                }

                Card(title: "6 · Verify with", systemImage: "checkmark.seal") {
                    verificationSection
                }

                if setupExperience == .advanced {
                    Card(title: "7 · Sampling", systemImage: "gauge.with.dots.needle.67percent") {
                        DisclosureGroup("Advanced sampling settings", isExpanded: $showAdvanced) {
                            samplingSection
                        }.font(.callout)
                        estimateRow
                    }
                } else {
                    Card(title: "7 · Run estimate", systemImage: "clock") { estimateRow }
                }
            }
            .padding(28).frame(maxWidth: 860, alignment: .leading).frame(maxWidth: .infinity)
            }
            Divider()
            startBar.padding(.horizontal, 28).padding(.vertical, 14)
                .background(.bar)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .clipped()
        .sheet(isPresented: $showTargetPrep) {
            TargetPrepView(
                targetKind: .protein,
                targetSequence: request.wrappedValue.targetSequence,
                targetSmiles: "",
                onUse: { residues in
                    // Hotspots picked on the structure become RFdiffusion3
                    // hotspot conditioning directly.
                    var conditions = request.wrappedValue.conditions
                    for residue in residues {
                        conditions[residue, default: []].insert(.hotspot)
                    }
                    request.wrappedValue.conditions = conditions
                    if !residues.isEmpty { request.wrappedValue.originStrategy = .hotspots }
                },
                onStructure: { cif in
                    // Adopt the prediction as the design target so the user never
                    // has to go looking for the file.
                    invalidateInspectedTarget(clearProteinMetadata: true)
                    // Target Prep uses the same reserved-binder convention as
                    // both design workflows: target subunits are B, C, D…
                    let ids = ProteinSequenceInput.chains(
                        request.wrappedValue.targetSequence, startingAt: 1
                    ).map(\.id)
                    request.wrappedValue.targetChain = ids.joined(separator: ",")
                    request.wrappedValue.targetStructurePath = cif
                },
                onClose: { showTargetPrep = false }
            )
        }
    }

    // MARK: Sequence design

    private var sequenceDesignSection: some View {
        let kind = request.wrappedValue.targetKind
        return VStack(alignment: .leading, spacing: 12) {
            Text("Backbones carry no sequence. This step decides what each one is actually made of.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            Picker("Inverse folder", selection: Binding(
                get: { request.wrappedValue.sequenceModel },
                set: { nv in
                    var r = request.wrappedValue
                    r.sequenceModel = nv
                    r.sequenceTemperature = nv.defaultTemperature
                    r.firstShellTemperature = nv.defaultFirstShellTemperature
                    request.wrappedValue = r
                }
            )) {
                ForEach(kind.sequenceModels) { Text($0.label).tag($0) }
            }
            .pickerStyle(.segmented).labelsHidden()

            Text(request.wrappedValue.sequenceModel.blurb)
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if !installer.isUsable(request.wrappedValue.sequenceModel.component) {
                Label("\(request.wrappedValue.sequenceModel.label) isn't installed yet — add it from Setup.",
                      systemImage: "exclamationmark.triangle.fill")
                    .font(.caption).foregroundStyle(.orange)
            }

            LabeledContent("Sequences per backbone") {
                EditableIntStepper(value: Binding(
                    get: { request.wrappedValue.sequencesPerBackbone },
                    set: { value in
                        request.wrappedValue.sequencesPerBackbone = value
                        request.wrappedValue.reconcileSelectionBudget()
                    }
                ), in: 1...16, accessibilityLabel: "Sequences per backbone")
            }

            Divider().padding(.vertical, 2)
            Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 8) {
                GridRow {
                    Text("Temperature").font(.callout)
                    Slider(value: request.sequenceTemperature, in: 0.05...1.0, step: 0.05).frame(width: 200)
                    Text(String(format: "%.2f", request.wrappedValue.sequenceTemperature))
                        .font(.callout.monospacedDigit()).frame(width: 44, alignment: .trailing)
                }
                if request.wrappedValue.sequenceModel == .lasermpnn {
                    GridRow {
                        Text("Binding site").font(.callout)
                        Slider(value: request.firstShellTemperature, in: 0.1...2.0, step: 0.1).frame(width: 200)
                        Text(String(format: "%.2f", request.wrappedValue.firstShellTemperature))
                            .font(.callout.monospacedDigit()).frame(width: 44, alignment: .trailing)
                    }
                }
            }
            Text(request.wrappedValue.sequenceModel == .lasermpnn
                 ? "Higher explores more sequences. LASErMPNN also places side chains, so the pocket has its own temperature — raise it to loosen packing, lower it to tighten."
                 : "Higher explores more sequences; lower keeps close to what the model thinks is most likely.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("RFdiffusion3").font(.largeTitle.bold())
            Text("Generate binder backbones from scratch, then design sequences onto them and check them with an independent model.")
                .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: Target

    private var targetKindPicker: some View {
        VStack(alignment: .leading, spacing: 6) {
            Picker("", selection: Binding(
                get: { request.wrappedValue.targetKind },
                set: { nv in
                    var r = request.wrappedValue
                    r.targetKind = nv
                    r.conditions = [:]
                    r.targetContig = ""
                    r.structureTargetSequence = ""
                    r.attachmentAtom = nil
                    r.attachmentLinkerAtom = nil
                    r.ligandIsConjugated = false
                    r.conformerPlan = []
                    r.originStrategy = nv == .smallMolecule ? .com : .hotspots
                    r.reconcileSequenceModel()
                    r.reconcileVerification()
                    request.wrappedValue = r
                    inspector.reset()
                    intelligence.reset()
                }
            )) {
                ForEach(RFD3TargetKind.allCases) { Text($0.label).tag($0) }
            }
            .pickerStyle(.segmented).labelsHidden().frame(width: 320)
            .accessibilityLabel("RFdiffusion3 target type")
            Text(request.wrappedValue.targetKind.blurb)
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    @ViewBuilder private var ligandInput: some View {
        VStack(alignment: .leading, spacing: 10) {
            Picker("", selection: Binding(
                get: { request.wrappedValue.ligandSource },
                set: { value in
                    invalidateInspectedTarget(clearProteinMetadata: false)
                    request.wrappedValue.ligandSource = value
                    request.wrappedValue.attachmentAtom = nil
                    request.wrappedValue.attachmentLinkerAtom = nil
                    request.wrappedValue.ligandIsConjugated = false
                }
            )) {
                ForEach(LigandSource.allCases) { Text($0.label).tag($0) }
            }.pickerStyle(.segmented).labelsHidden().frame(width: 340)
                .accessibilityLabel("Ligand input type")
            Text(request.wrappedValue.ligandSource.blurb)
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if request.wrappedValue.ligandSource == .smiles {
                TextField("SMILES, e.g. O=C(NCCO)c1ccc…", text: Binding(
                    get: { request.wrappedValue.smiles },
                    set: { value in
                        if value != request.wrappedValue.smiles {
                            invalidateInspectedTarget(clearProteinMetadata: false)
                            request.wrappedValue.smiles = value
                            request.wrappedValue.attachmentAtom = nil
                            request.wrappedValue.attachmentLinkerAtom = nil
                        }
                    }
                ))
                    .textFieldStyle(.roundedBorder).font(.system(.body, design: .monospaced))
                HStack {
                    Text("Component code").font(.callout)
                    TextField("LG1", text: request.componentCode)
                        .textFieldStyle(.roundedBorder).frame(width: 80)
                        .font(.system(.body, design: .monospaced))
                    Text("A 1–3 character name for this molecule. Avoid \"LIG\".")
                        .font(.caption).foregroundStyle(.secondary)
                }
                LigandAtomPicker(
                    smiles: request.wrappedValue.smiles,
                    attachmentAtom: request.attachmentAtom,
                    attachmentLinkerAtom: request.attachmentLinkerAtom,
                    coreAtoms: intelligence.analysis?.core.coreAtoms ?? [],
                    presentationAtoms: intelligence.analysis?.core.presentationAtoms ?? [],
                    atomLabels: inspector.atomLabels,
                    allowsAttachmentPicking: false
                )
                    .frame(height: 180)
                    .background(RoundedRectangle(cornerRadius: 8).fill(.background))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
                Label("RFdiffusion3 can't read SMILES directly, so Studio builds a 3D conformer and a proper chemical-component definition for it.",
                      systemImage: "wand.and.stars")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                filePicker(path: request.ligandStructurePath,
                           prompt: "Choose a PDB containing your ligand",
                           types: [.init(filenameExtension: "pdb") ?? .data],
                           onChoose: { invalidateInspectedTarget(clearProteinMetadata: false) })
                HStack {
                    Text("Ligand residue name").font(.callout)
                    TextField("e.g. FHE", text: Binding(
                        get: { request.wrappedValue.ligandResidueName },
                        set: { value in
                            if value != request.wrappedValue.ligandResidueName {
                                invalidateInspectedTarget(clearProteinMetadata: false)
                                request.wrappedValue.ligandResidueName = value
                            }
                        }
                    ))
                        .textFieldStyle(.roundedBorder).frame(width: 100)
                        .font(.system(.body, design: .monospaced))
                }
                TextField("Ligand SMILES (required for sequence design and verification)",
                          text: request.smiles)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(.body, design: .monospaced))
                Text("The PDB supplies the exact 3D pose; the SMILES supplies bond order and chemistry to the sequence designer and folding pipeline.")
                    .font(.caption2).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            inspectButton
        }
    }

    @ViewBuilder private var proteinInput: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("RFdiffusion3 designs against a 3D structure. Paste a sequence and Studio will predict one, or choose a structure you already have.")
                .font(.callout).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            ProteinChainInputView(text: request.targetSequence, startingAt: 1,
                                  placeholder: "Target chain B[:target chain C…]",
                                  minimumLength: 5)
                .onChange(of: request.wrappedValue.targetSequence) { _, value in
                    guard case .success(let chains) = ProteinSequenceInput.parse(
                        value, startingAt: 1, minimumLength: 5
                    ) else { return }
                    let assigned = chains.map(\.id).joined(separator: ",")
                    if request.wrappedValue.targetStructurePath.isEmpty,
                       request.wrappedValue.targetChain != assigned {
                        invalidateInspectedTarget(clearProteinMetadata: true)
                        request.wrappedValue.targetChain = assigned
                    }
                }
            HStack {
                Text("\(request.wrappedValue.targetChains.reduce(0) { $0 + $1.sequence.count }) aa total")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button { showTargetPrep = true } label: {
                    Label("Predict structure & pick hotspots", systemImage: "scope")
                }
                .disabled(request.wrappedValue.targetChains.isEmpty)
            }

            Divider().padding(.vertical, 2)
            filePicker(path: request.targetStructurePath,
                       prompt: "…or choose a structure file (PDB or mmCIF)",
                       types: [.init(filenameExtension: "pdb") ?? .data,
                               .init(filenameExtension: "cif") ?? .data,
                               .init(filenameExtension: "mmcif") ?? .data],
                       onChoose: {
                           invalidateInspectedTarget(clearProteinMetadata: true)
                           // An external structure may use any chain names.
                           // Empty means “inspect the first chain” and is
                           // replaced with the chain(s) actually read below.
                           request.wrappedValue.targetChain = ""
                       })
            HStack {
                Text("Chains").font(.callout)
                TextField("B,C", text: Binding(
                    get: { request.wrappedValue.targetChain },
                    set: { value in
                        if value != request.wrappedValue.targetChain {
                            invalidateInspectedTarget(clearProteinMetadata: true)
                            request.wrappedValue.targetChain = value
                        }
                    }
                ))
                    .textFieldStyle(.roundedBorder).frame(width: 90)
                    .font(.system(.body, design: .monospaced))
                if !inspector.chains.isEmpty {
                    Text("Available: \(inspector.chains.joined(separator: ", "))")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            if !request.wrappedValue.targetContig.isEmpty {
                Text("Using residues \(request.wrappedValue.targetContig)")
                    .font(.caption).foregroundStyle(.secondary)
            }
            inspectButton
        }
    }

    private var inspectButton: some View {
        HStack {
            Button {
                let r = request.wrappedValue
                switch r.targetKind {
                case .smallMolecule:
                    if r.ligandSource == .smiles { inspector.inspectLigand(smiles: r.smiles) }
                    else { inspector.inspectLigandFile(path: r.ligandStructurePath, residueName: r.ligandResidueName) }
                case .protein:
                    inspector.inspectProtein(path: r.targetStructurePath,
                                             chains: r.selectedTargetChainIDs,
                                             expectedChainCount: max(1,
                                                ProteinSequenceInput.chains(
                                                    r.targetSequence, startingAt: 1
                                                ).count))
                }
            } label: {
                Label(inspector.hasResult ? "Re-read target" : "Read target",
                      systemImage: "magnifyingglass")
            }
            .disabled(inspector.isInspecting || !request.wrappedValue.isRunnable)
            if inspector.isInspecting { ProgressView().controlSize(.small) }
            if let error = inspector.error {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .onChange(of: inspector.suggestedContig) { _, contig in
            if !contig.isEmpty {
                request.wrappedValue.targetContig = contig
            }
        }
        .onChange(of: inspector.selectedChains) { _, chains in
            if !chains.isEmpty {
                request.wrappedValue.targetChain = chains.joined(separator: ",")
            }
        }
        .onChange(of: inspector.suggestedSequence) { _, sequence in
            guard !sequence.isEmpty else { return }
            request.wrappedValue.structureTargetSequence = sequence
            if TemplateWriter.clean(request.wrappedValue.targetSequence).isEmpty {
                request.wrappedValue.targetSequence = sequence
            }
        }
    }

    private func filePicker(path: Binding<String>, prompt: String, types: [UTType],
                            onChoose: (() -> Void)? = nil) -> some View {
        HStack {
            Text(path.wrappedValue.isEmpty ? prompt : (path.wrappedValue as NSString).lastPathComponent)
                .font(.callout)
                .foregroundStyle(path.wrappedValue.isEmpty ? .secondary : .primary)
                .lineLimit(1).truncationMode(.middle)
            Spacer()
            Button("Choose…") {
                let panel = NSOpenPanel()
                panel.allowedContentTypes = types
                panel.allowsMultipleSelection = false
                panel.canChooseDirectories = false
                if panel.runModal() == .OK, let url = panel.url {
                    onChoose?()
                    path.wrappedValue = url.path
                }
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 8).fill(.quaternary.opacity(0.3)))
    }

    private func invalidateInspectedTarget(clearProteinMetadata: Bool) {
        request.wrappedValue.conditions = [:]
        proposedConditions = nil
        intelligence.reset()
        request.wrappedValue.conformerPlan = []
        if clearProteinMetadata {
            request.wrappedValue.targetContig = ""
            request.wrappedValue.structureTargetSequence = ""
        }
        inspector.reset()
    }

    // MARK: Conditioning

    private var conditioningSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            if inspector.isInspecting {
                HStack { ProgressView().controlSize(.small); Text("Reading your target…") }
            } else if inspector.hasResult {
                HStack {
                    Text(request.wrappedValue.targetKind == .smallMolecule
                         ? "\(inspector.sites.count) heavy atoms"
                         : "\(inspector.sites.count) residues across chain\(request.wrappedValue.selectedTargetChainIDs.count == 1 ? "" : "s") \(request.wrappedValue.selectedTargetChainIDs.joined(separator: ", "))")
                        .font(.callout).foregroundStyle(.secondary)
                    if let charge = inspector.formalCharge, charge != 0 {
                        Text("· formal charge \(charge > 0 ? "+" : "")\(charge)")
                            .font(.callout).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button {
                        proposedConditions = inspector.suggestedConditions(
                            presentationAtomIndices: suggestionPresentationAtoms)
                    } label: {
                        Label("Preview suggestions", systemImage: "sparkles")
                    }
                    .disabled(needsLinkerAnalysisForSuggestions)
                    Button("Clear") {
                        request.wrappedValue.conditions = [:]
                        proposedConditions = nil
                    }
                }
                Text(request.wrappedValue.targetKind == .smallMolecule
                     ? "Bury controls solvent accessibility and asks for pocket packing. Hotspot asks for a nearby protein contact (typically within 4.5 Å) without requiring enclosure. Ligand donor/acceptor describes the selected ligand atom, not the protein partner."
                     : "Hotspots steer the binder to one face of your target. Picking none lets it bind anywhere.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                ForEach(inspector.warnings, id: \.self) { warning in
                    Label(warning, systemImage: "info.circle")
                        .font(.caption2).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if needsLinkerAnalysisForSuggestions {
                    Label("Analyse the directed core-to-linker bond in section 2 before previewing suggestions, so linker atoms can be exposed instead of buried.",
                          systemImage: "arrow.up.circle")
                        .font(.caption).foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if let proposedConditions {
                    suggestionPreview(proposedConditions)
                }

                siteTable
                originSection
            }
        }
    }

    private var conditionChoices: [AtomCondition] {
        request.wrappedValue.targetKind == .smallMolecule
            ? AtomCondition.allCases
            : AtomCondition.proteinCases
    }

    private var siteTable: some View {
        ScrollView {
            VStack(spacing: 0) {
                ForEach(inspector.sites) { site in
                    HStack(spacing: 10) {
                        Text(site.name)
                            .font(.system(.callout, design: .monospaced))
                            .frame(width: 66, alignment: .leading)
                        if let index = site.atomIndex {
                            Text("#\(index)")
                                .font(.system(.caption2, design: .monospaced))
                                .foregroundStyle(.tertiary)
                                .frame(width: 34, alignment: .leading)
                        }
                        Text(site.element)
                            .font(.caption).foregroundStyle(.secondary)
                            .frame(width: 40, alignment: .leading)
                        ForEach(conditionChoices) { condition in
                            Toggle(condition.label, isOn: binding(for: site.name, condition: condition))
                                .toggleStyle(.button).controlSize(.small)
                                .help(condition.help)
                        }
                        Spacer()
                        if !site.suggestionReasons.isEmpty {
                            Image(systemName: "sparkles")
                                .font(.caption2).foregroundStyle(.tertiary)
                                .help(site.suggestionReasons
                                    .sorted { $0.key.rawValue < $1.key.rawValue }
                                    .map { "\($0.key.label): \($0.value)" }
                                    .joined(separator: "\n"))
                        }
                    }
                    .padding(.vertical, 3).padding(.horizontal, 8)
                    .background(request.wrappedValue.conditions[site.name]?.isEmpty == false
                                ? Color.accentColor.opacity(0.08) : Color.clear)
                }
            }
        }
        .frame(maxHeight: 260)
        .background(RoundedRectangle(cornerRadius: 8).fill(.background))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
    }

    private var suggestionPresentationAtoms: Set<Int> {
        Set(intelligence.analysis?.core.presentationAtoms ?? [])
    }

    private var needsLinkerAnalysisForSuggestions: Bool {
        request.wrappedValue.targetKind == .smallMolecule &&
            request.wrappedValue.attachmentAtom != nil &&
            request.wrappedValue.attachmentLinkerAtom != nil &&
            intelligence.analysis == nil
    }

    private func suggestionPreview(_ proposal: [String: Set<AtomCondition>]) -> some View {
        let counts = Dictionary(uniqueKeysWithValues: AtomCondition.allCases.map { condition in
            (condition, proposal.values.filter { $0.contains(condition) }.count)
        })
        return VStack(alignment: .leading, spacing: 8) {
            Label("Review before applying", systemImage: "eye")
                .font(.callout.weight(.semibold))
            Text(AtomCondition.allCases.compactMap { condition in
                let count = counts[condition] ?? 0
                return count > 0 ? "\(condition.label): \(count)" : nil
            }.joined(separator: " · "))
                .font(.caption).foregroundStyle(.secondary)
            Text("Non-polar core atoms are proposed as buried; RDKit assigns donor/acceptor roles for the exact tautomer and protonation supplied. An explicitly selected linker side is exposed. Hotspots are never guessed because they specify the contact location you want.")
                .font(.caption2).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            HStack {
                Button("Apply suggestions") {
                    request.wrappedValue.conditions = proposal
                    proposedConditions = nil
                }.buttonStyle(.borderedProminent)
                Button("Cancel") { proposedConditions = nil }
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.accentColor.opacity(0.08)))
    }

    /// Bury and expose are mutually exclusive: an atom cannot be both, and the
    /// pinned Foundry build silently let the later selection erase the earlier
    /// one, so the UI enforces it rather than relying on the patch.
    private func binding(for site: String, condition: AtomCondition) -> Binding<Bool> {
        Binding(
            get: { request.wrappedValue.conditions[site]?.contains(condition) ?? false },
            set: { on in
                var set = request.wrappedValue.conditions[site] ?? []
                if on {
                    if condition == .buried { set.remove(.exposed) }
                    if condition == .exposed { set.remove(.buried) }
                    set.insert(condition)
                } else {
                    set.remove(condition)
                }
                if set.isEmpty { request.wrappedValue.conditions.removeValue(forKey: site) }
                else { request.wrappedValue.conditions[site] = set }
            }
        )
    }

    private var originSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Divider().padding(.vertical, 4)
            Text("Centre the design on").font(.headline)
            Picker("", selection: request.originStrategy) {
                ForEach(OriginStrategy.allCases) { Text($0.label).tag($0) }
            }.pickerStyle(.segmented).labelsHidden().frame(width: 420)
                .accessibilityLabel("Design centre strategy")
            Text(request.wrappedValue.originStrategy.blurb)
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if request.wrappedValue.originStrategy == .explicit {
                HStack(spacing: 8) {
                    ForEach(0..<3, id: \.self) { i in
                        TextField(["X", "Y", "Z"][i], value: Binding(
                            get: { request.wrappedValue.originXYZ.indices.contains(i) ? request.wrappedValue.originXYZ[i] : 0 },
                            set: { nv in
                                var xyz = request.wrappedValue.originXYZ
                                while xyz.count < 3 { xyz.append(0) }
                                xyz[i] = nv
                                request.wrappedValue.originXYZ = xyz
                            }
                        ), format: .number)
                        .textFieldStyle(.roundedBorder).frame(width: 80)
                    }
                }
            }
        }
    }

    // MARK: Length

    private var lengthSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 10) {
                GridRow {
                    Text("Shortest")
                    EditableIntStepper(value: request.minLength,
                                       in: 20...min(400, request.wrappedValue.maxLength),
                                       suffix: "aa", accessibilityLabel: "Shortest binder length")
                }
                GridRow {
                    Text("Longest")
                    EditableIntStepper(value: request.maxLength,
                                       in: request.wrappedValue.minLength...500,
                                       suffix: "aa", accessibilityLabel: "Longest binder length")
                }
                GridRow {
                    Text("How many designs")
                    EditableIntStepper(value: Binding(
                        get: { request.wrappedValue.numDesigns },
                        set: { value in
                            request.wrappedValue.numDesigns = value
                            request.wrappedValue.reconcileSelectionBudget()
                        }
                    ), in: 1...5000, step: 10, accessibilityLabel: "Number of designs")
                }
            }
            Toggle("Prefer structured folds over loopy ones", isOn: request.preferStructured)
                .toggleStyle(.checkbox)
            Text("On by default. De-novo binders otherwise come out loop-heavy, which tends to fold and express badly.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            Divider().padding(.vertical, 2)
            Label {
                Text("Lengths are spread across \(request.wrappedValue.binLengths.count) batches: \(binSummary). Designs within a batch share a length; different batches use different lengths.")
            } icon: {
                Image(systemName: "square.stack.3d.up")
            }
            .font(.caption).foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
            Text("That split isn't cosmetic — the model can only batch trajectories that share a shape, so one batch is one length.")
                .font(.caption2).foregroundStyle(.tertiary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var binSummary: String {
        let lengths = request.wrappedValue.binLengths
        if lengths.count <= 6 { return lengths.map(String.init).joined(separator: ", ") + " aa" }
        let head = lengths.prefix(3).map(String.init).joined(separator: ", ")
        return "\(head) … \(lengths.last ?? 0) aa"
    }

    // MARK: Verification

    private var extraCheckChoices: [Predictor] {
        // For a protein target Boltz is one option among several, so it appears
        // in the list like everything else rather than being pinned above it.
        request.wrappedValue.targetKind == .smallMolecule
            ? Predictor.checkChoices.filter { $0 != .boltz && $0 != .boltzPotentials }
            : Predictor.checkChoices
    }

    /// Boltz, pinned, for small-molecule campaigns.
    @ViewBuilder private func boltzCard(isLigand: Bool) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("Boltz-2 — always used", systemImage: "checkmark.circle.fill")
                .font(.callout.weight(.medium)).foregroundStyle(.green)
            Text("It is the only engine with a binding-affinity head, and the ranking needs it.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            Toggle("Use steering potentials", isOn: request.verification.useBoltzPotentials)
                .toggleStyle(.checkbox)
            Text("Physically cleaner poses, roughly twice the time. Worth it for a pocket.")
                .font(.caption2).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            Toggle("Predict binding probability, P(bind)", isOn: request.verification.runAffinityHead)
                .toggleStyle(.checkbox)
            Text(request.wrappedValue.verification.runAffinityHead
                 ? "Designs are ranked on ligand pLDDT plus P(bind) — the combined metric."
                 : "Without it, designs are ranked on ligand pLDDT alone.")
                .font(.caption2).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 8).fill(.green.opacity(0.08)))
    }

    /// Protein targets: nothing is mandatory. The affinity head is trained on
    /// small molecules, so the reason Boltz is pinned for a ligand simply does
    /// not apply here — pick whichever engines you want.
    @ViewBuilder private var proteinPredictorCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Pick one or more engines").font(.callout.weight(.medium))
            Text("Nothing is compulsory here. The binding-affinity head is trained on small molecules, so it plays no part in a protein campaign and Boltz has no special claim — designs are ranked on confidence.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Toggle("Use Boltz steering potentials, if Boltz is selected",
                   isOn: request.verification.useBoltzPotentials)
                .toggleStyle(.checkbox).font(.callout)
                .disabled(!request.wrappedValue.verification.usesBoltz(for: .protein))
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 8).fill(.quaternary.opacity(0.3)))
    }

    /// One optional second-opinion predictor. Extracted from the section body so
    /// the type checker can cope, and so the row reads as one idea.
    /// All four engines can now drive the RFdiffusion3 checker. OpenFold-3's
    /// query JSON and runner YAML used to be buildable only from inside
    /// `nanohunter_run.sh`; those builders were extracted to standalone scripts
    /// and verified to produce byte-identical output, so there is one definition
    /// of each conversion rather than two.
    private func isWiredForRFD3(_ p: Predictor) -> Bool { true }

    @ViewBuilder private func checkerRow(_ p: Predictor) -> some View {
        let installed = installer.isUsable(p.component)
        let wired = isWiredForRFD3(p)
        Toggle(isOn: Binding(
            get: { request.wrappedValue.verification
                .effectiveExtraPredictors(for: request.wrappedValue.targetKind)
                .contains(p.checkingVariant) },
            set: { on in
                var r = request.wrappedValue
                if on { r.verification.extraPredictors.append(p.checkingVariant) }
                else { r.verification.extraPredictors.removeAll { $0.checkingVariant == p.checkingVariant } }
                r.reconcileVerification()
                request.wrappedValue = r
            }
        )) {
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 6) {
                    Text(p.label)
                    if request.wrappedValue.verification.intellifoldModel == .v2
                        && p == .intellifold {
                        Text("not benchmarked").font(.caption).foregroundStyle(.secondary)
                    } else {
                        Text(p.speed(in: .batched).label)
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if !installed {
                        Label("not installed", systemImage: "exclamationmark.circle")
                            .font(.caption2).foregroundStyle(.orange)
                    } else if !wired {
                        Label("not yet available here", systemImage: "wrench.and.screwdriver")
                            .font(.caption2).foregroundStyle(.secondary)
                    }
                }
                Text(p.blurb)
                    .font(.caption2).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .toggleStyle(.checkbox)
        .disabled((!installed && !request.wrappedValue.verification
            .effectiveExtraPredictors(for: request.wrappedValue.targetKind)
            .contains(p.checkingVariant)) || !wired)
        .help(p.caveat.isEmpty ? p.blurb : p.caveat)
    }

    private var verificationSection: some View {
        let kind = request.wrappedValue.targetKind
        let isLigand = kind == .smallMolecule
        let folds = request.wrappedValue.numDesigns * request.wrappedValue.sequencesPerBackbone
        return VStack(alignment: .leading, spacing: 12) {
            Text(isLigand
                 ? "Designed sequences are folded back with the ligand present and ranked. Every fold here is a real cost — this stage dominates the run."
                 : "Designed sequences are folded back with the target present and ranked. Studio generates the target's MSA once, on the first prediction, and reuses it for the rest of the campaign.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if isLigand {
                // Boltz is mandatory only because the ranking metric needs
                // P(bind), and Boltz is the only engine with an affinity head.
                boltzCard(isLigand: true)
            } else {
                proteinPredictorCard
            }

            // --- Optional second opinions ---
            VStack(alignment: .leading, spacing: 6) {
                Text("Add an independent second opinion").font(.callout.weight(.medium))
                Text("Agreement between two unrelated models is much stronger evidence than a high score from one. Each one you add re-folds every design again, so pick deliberately.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                ForEach(extraCheckChoices) { checkerRow($0) }
                if request.wrappedValue.verification.effectiveExtraPredictors(for: kind).contains(where: {
                    $0 == .intellifold
                }) {
                    Picker("IntelliFold model", selection: request.verification.intellifoldModel) {
                        ForEach(IntelliFoldModel.allCases) { model in
                            Text(model.label).tag(model)
                        }
                    }
                    .pickerStyle(.menu)
                }
            }

            Divider().padding(.vertical, 2)
            LabeledContent("Keep the best") {
                let limit = min(500, request.wrappedValue.totalDesignedSequences)
                EditableIntStepper(value: request.verification.topN, in: 1...limit,
                                   step: limit >= 10 ? 10 : 1,
                                   accessibilityLabel: "Number of designs to keep")
            }
            if isLigand {
                Toggle("Also fold the best designs without the ligand",
                       isOn: request.verification.runApoCheck)
                    .toggleStyle(.checkbox)
                Text("Comparing the two tells you whether the pocket is already formed before the ligand arrives, or only assembles around it.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            let engines = max(1, request.wrappedValue.verification.allPredictors(for: kind).count)
            let apoFolds = isLigand && request.wrappedValue.verification.runApoCheck
                ? request.wrappedValue.verification.topN : 0
            let totalFolds = folds * engines + apoFolds
            Label("\(totalFolds) folds in total\(apoFolds > 0 ? " (including \(apoFolds) apo checks)" : ""). This stage will dominate the run — expect days, not hours, at this scale.",
                  systemImage: "clock")
                .font(.caption)
                .foregroundStyle(totalFolds > 1000 ? .orange : .secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: Sampling

    private var samplingSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 10) {
                GridRow {
                    Text("Batch size")
                    EditableIntStepper(value: request.batchSize, in: 1...32,
                                       accessibilityLabel: "RFdiffusion3 batch size")
                }
                GridRow {
                    Text("Concurrent queues")
                    EditableIntStepper(value: request.queuesPerBin, in: 1...4,
                                       accessibilityLabel: "Concurrent RFdiffusion3 queues")
                }
                GridRow {
                    Text("Diffusion steps")
                    EditableIntStepper(value: request.timesteps, in: 20...500, step: 10,
                                       accessibilityLabel: "Diffusion steps")
                }
                GridRow {
                    Text("Length bins")
                    EditableIntStepper(value: request.numBins, in: 1...30,
                                       accessibilityLabel: "Length bins")
                }
            }
            if request.wrappedValue.queuesPerBin != 2 {
                Label("Two concurrent queues is the measured optimum: it beat running them one after another by about 19%, and four queues were slower than two even with plenty of memory free.",
                      systemImage: "exclamationmark.triangle")
                    .font(.caption).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                Text("Batch 4 across 2 queues is the production setting. Batch size is fixed from measurement, not from free memory — memory use barely changed across batch sizes while speed fell off sharply past the optimum, and the optimum drops as the ligand and binder get bigger.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.top, 8)
    }

    private var estimateRow: some View {
        Label {
            Text("Backbone generation alone: roughly \(formatted(request.wrappedValue.estimatedBackboneSeconds)). Sequence design and folding add to that.")
        } icon: {
            Image(systemName: "clock")
        }
        .font(.callout).foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
    }

    private func formatted(_ seconds: Double) -> String {
        if seconds < 90 { return "\(Int(seconds.rounded())) s" }
        if seconds < 5400 { return String(format: "%.0f min", seconds / 60) }
        return String(format: "%.1f hours", seconds / 3600)
    }

    // MARK: Start

    private var startBar: some View {
        let r = request.wrappedValue
        let issues = r.validationIssues
        let anotherWorkflowIsRunning = app.run.isRunning || app.prediction.isRunning
        let missingComponents = r.requiredComponents.filter {
            installer.components[$0] != nil && !installer.isUsable($0)
        }
        return VStack(alignment: .leading, spacing: 8) {
            ForEach(issues, id: \.self) { issue in
                Label(issue, systemImage: "exclamationmark.triangle.fill")
                    .font(.callout).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !missingComponents.isEmpty {
                Label("Install \(missingComponents.map(\.label).joined(separator: ", ")) in Setup before starting.",
                      systemImage: "exclamationmark.triangle.fill")
                    .font(.callout).foregroundStyle(.orange)
            }
            HStack {
                if anotherWorkflowIsRunning {
                    Label("Finish or stop the active \(app.prediction.isRunning ? "prediction" : "iterative design") run before starting RFdiffusion3.",
                          systemImage: "hourglass")
                        .font(.callout).foregroundStyle(.secondary)
                } else if !r.isRunnable {
                    Label("Add your target above to continue.", systemImage: "info.circle")
                        .font(.callout).foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    controller.start(project: app.selectedProject ?? project, request: r)
                } label: {
                    Label("Start RFdiffusion3 Run", systemImage: "play.fill").frame(minWidth: 220)
                }
                .buttonStyle(.borderedProminent).controlSize(.large)
                .accessibilityLabel("Start RFdiffusion3 run")
                .accessibilityIdentifier("start-rfdiffusion3-run")
                .disabled(!r.isRunnable || !issues.isEmpty || !missingComponents.isEmpty
                          || anotherWorkflowIsRunning)
            }
        }
        .padding(.top, 6)
    }
}

/// Live progress for a running campaign.
///
/// A small-molecule campaign is detached and can run for days, so this view is
/// driven by polled counts from the RFD3 repo's own status script rather than by
/// streamed stdout — the app may not have been running when most of the work
/// happened.
struct RFD3ProgressView: View {
    @ObservedObject var controller: RFD3Controller

    private var stageOrder: [(String, String)] {
        if controller.isProteinCampaign {
            return [("fixtures", "Length bins"), ("backbones", "Backbones"),
                    ("mpnn", "Sequences"), ("msa", "Alignment"),
                    ("predict", "Folding"), ("score", "Ranking")]
        }
        return [("validate", "Target"), ("fixtures", "Length bins"), ("backbones", "Backbones"),
                ("mpnn", "Sequences"), ("predict-holo", "Folding"), ("score", "Ranking"),
                ("predict-apo", "Apo folding"), ("rmsd", "Preorganisation")]
    }

    private let countLabels: [(String, String)] = [
        ("backbones", "Backbones"), ("sequences", "Sequences"),
        ("holo_predictions", "Folds with ligand"), ("top", "Selected"),
        ("apo_predictions", "Apo folds"), ("rmsd_rows", "Preorganisation"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("RFdiffusion3 campaign").font(.title2.bold())
                    Text(controller.currentMessage).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
                if controller.isRunning {
                    Button("Refresh") { controller.refreshStatus() }
                    Button("Stop", role: .destructive) { controller.cancel() }
                } else {
                    Button("Back") { controller.campaignRoot = nil; controller.phase = .idle }
                }
            }

            ProgressView(value: controller.progress).progressViewStyle(.linear)

            HStack(spacing: 6) {
                ForEach(stageOrder, id: \.0) { key, label in
                    let done = controller.completedStages.contains(key)
                    let active = controller.currentStage == key
                    Text(label)
                        .font(.caption)
                        .padding(.horizontal, 8).padding(.vertical, 4)
                        .background(RoundedRectangle(cornerRadius: 6)
                            .fill(active ? Color.accentColor.opacity(0.25)
                                         : (done ? Color.green.opacity(0.18) : Color.gray.opacity(0.12))))
                }
            }

            if controller.isRunning {
                Label("This campaign keeps running if you quit Studio — it is detached and holds the Mac awake. Reopen this workspace to check on it.",
                      systemImage: "moon.zzz")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if !controller.counts.isEmpty {
                LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 3), spacing: 10) {
                    ForEach(countLabels, id: \.0) { key, label in
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(controller.counts[key] ?? 0)")
                                .font(.title3.bold()).monospacedDigit()
                            Text(label).font(.caption2).foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                        .background(RoundedRectangle(cornerRadius: 8).fill(.quaternary.opacity(0.3)))
                    }
                }
            }

            if case .failed(let message) = controller.phase {
                ActionableErrorCard(title: "RFdiffusion3 needs attention", message: message,
                                    retryTitle: "Resume campaign", retry: controller.retry,
                                    output: controller.campaignRoot, log: controller.log)
            }

            if case .finished = controller.phase, let root = controller.campaignRoot {
                RFD3ResultsSummary(root: root)
            }

            if !controller.log.isEmpty, controller.phase != .finished {
                if case .failed = controller.phase { EmptyView() }
                else { TechnicalLogDisclosure(lines: controller.log) }
            }

            if let root = controller.campaignRoot {
                Button {
                    NSWorkspace.shared.activateFileViewerSelecting([root])
                } label: {
                    Label("Show campaign folder", systemImage: "folder")
                }
                .controlSize(.small)
            }
            Spacer(minLength: 0)
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .onAppear { controller.refreshStatus() }
    }
}

private struct RFD3ResultsSummary: View {
    let root: URL
    @State private var showResults = false

    private var rows: [[String: Any]] {
        let url = root.appendingPathComponent("analysis/top100_manifest.json")
        guard let data = try? Data(contentsOf: url),
              let payload = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
        else { return [] }
        return payload
    }

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: "checkmark.seal.fill")
                .font(.title).foregroundStyle(.green)
            VStack(alignment: .leading, spacing: 3) {
                Text("Ranked results are ready").font(.headline)
                Text(summary).font(.callout).foregroundStyle(.secondary)
            }
            Spacer()
            Button { showResults = true } label: {
                Label("View Results", systemImage: "cube.transparent")
            }
            .buttonStyle(.borderedProminent)
            .accessibilityIdentifier("view-rfd3-results")
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: 12).fill(Color.green.opacity(0.09)))
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Ranked RFdiffusion3 results ready. \(summary)")
        .sheet(isPresented: $showResults) {
            RunResultsView(root: root, workflow: .rfdiffusion3)
        }
    }

    private var summary: String {
        guard let first = rows.first else { return "Open the campaign folder to inspect its outputs." }
        let score = first["score"] as? Double
        let metric = first["mean_iptm"] != nil ? "mean iPTM" : "score"
        if let score { return "\(rows.count) selected design(s); top \(metric) \(String(format: "%.3f", score))." }
        return "\(rows.count) selected design(s)."
    }
}
