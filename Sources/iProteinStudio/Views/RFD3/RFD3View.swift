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
                                .appendingPathComponent("rfd3/assets/conformers", isDirectory: true))
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
        .sheet(isPresented: $showTargetPrep) {
            TargetPrepView(
                targetKind: .protein,
                targetSequence: request.wrappedValue.targetSequence,
                targetSmiles: "",
                onUse: { residues in
                    // Hotspots picked on the structure become RFdiffusion3
                    // hotspot conditioning directly.
                    var conditions = request.wrappedValue.conditions
                    let chain = request.wrappedValue.targetChain
                    for residue in residues {
                        conditions["\(chain)\(residue)", default: []].insert(.hotspot)
                    }
                    request.wrappedValue.conditions = conditions
                    if !residues.isEmpty { request.wrappedValue.originStrategy = .hotspots }
                },
                onStructure: { cif in
                    // Adopt the prediction as the design target so the user never
                    // has to go looking for the file.
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
                Stepper(value: request.sequencesPerBackbone, in: 1...16) {
                    Text("\(request.wrappedValue.sequencesPerBackbone)").monospacedDigit()
                }
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
                    r.originStrategy = nv == .smallMolecule ? .com : .hotspots
                    r.reconcileSequenceModel()
                    request.wrappedValue = r
                    inspector.reset()
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
            Picker("", selection: request.ligandSource) {
                ForEach(LigandSource.allCases) { Text($0.label).tag($0) }
            }.pickerStyle(.segmented).labelsHidden().frame(width: 340)
                .accessibilityLabel("Ligand input type")
            Text(request.wrappedValue.ligandSource.blurb)
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if request.wrappedValue.ligandSource == .smiles {
                TextField("SMILES, e.g. O=C(NCCO)c1ccc…", text: request.smiles)
                    .textFieldStyle(.roundedBorder).font(.system(.body, design: .monospaced))
                HStack {
                    Text("Component code").font(.callout)
                    TextField("LG1", text: request.componentCode)
                        .textFieldStyle(.roundedBorder).frame(width: 80)
                        .font(.system(.body, design: .monospaced))
                    Text("A 1–3 character name for this molecule. Avoid \"LIG\".")
                        .font(.caption).foregroundStyle(.secondary)
                }
                SmilesView(smiles: request.wrappedValue.smiles)
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
                           types: [.init(filenameExtension: "pdb") ?? .data])
                HStack {
                    Text("Ligand residue name").font(.callout)
                    TextField("e.g. FHE", text: request.ligandResidueName)
                        .textFieldStyle(.roundedBorder).frame(width: 100)
                        .font(.system(.body, design: .monospaced))
                }
            }

            inspectButton
        }
    }

    @ViewBuilder private var proteinInput: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("RFdiffusion3 designs against a 3D structure. Paste a sequence and Studio will predict one, or choose a structure you already have.")
                .font(.callout).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            SequenceEditor(text: request.targetSequence, placeholder: "Target sequence…")
            HStack {
                Text("\(TemplateWriter.clean(request.wrappedValue.targetSequence).count) aa")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button { showTargetPrep = true } label: {
                    Label("Predict structure & pick hotspots", systemImage: "scope")
                }
                .disabled(TemplateWriter.clean(request.wrappedValue.targetSequence).count < 10)
            }

            Divider().padding(.vertical, 2)
            filePicker(path: request.targetStructurePath,
                       prompt: "…or choose a structure file (PDB)",
                       types: [.init(filenameExtension: "pdb") ?? .data])
            HStack {
                Text("Chain").font(.callout)
                TextField("B", text: request.targetChain)
                    .textFieldStyle(.roundedBorder).frame(width: 60)
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
                    inspector.inspectProtein(path: r.targetStructurePath, chain: r.targetChain)
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
            if !contig.isEmpty && request.wrappedValue.targetContig.isEmpty {
                request.wrappedValue.targetContig = contig
            }
        }
    }

    private func filePicker(path: Binding<String>, prompt: String, types: [UTType]) -> some View {
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
                if panel.runModal() == .OK, let url = panel.url { path.wrappedValue = url.path }
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 8).fill(.quaternary.opacity(0.3)))
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
                         : "\(inspector.sites.count) residues in chain \(request.wrappedValue.targetChain)")
                        .font(.callout).foregroundStyle(.secondary)
                    if let charge = inspector.formalCharge, charge != 0 {
                        Text("· formal charge \(charge > 0 ? "+" : "")\(charge)")
                            .font(.callout).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button {
                        request.wrappedValue.conditions = inspector.suggestedConditions()
                    } label: {
                        Label("Suggest for me", systemImage: "sparkles")
                    }
                    Button("Clear") { request.wrappedValue.conditions = [:] }
                }
                Text(request.wrappedValue.targetKind == .smallMolecule
                     ? "Buried atoms get protein packed around them; exposed atoms stay reachable — keep linkers and conjugation handles exposed or you'll design a binder you can't attach anything to."
                     : "Hotspots steer the binder to one face of your target. Picking none lets it bind anywhere.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                ForEach(inspector.warnings, id: \.self) { warning in
                    Label(warning, systemImage: "info.circle")
                        .font(.caption2).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
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
                        Text(site.element)
                            .font(.caption).foregroundStyle(.secondary)
                            .frame(width: 40, alignment: .leading)
                        ForEach(conditionChoices) { condition in
                            Toggle(condition.label, isOn: binding(for: site.name, condition: condition))
                                .toggleStyle(.button).controlSize(.small)
                                .help(condition.help)
                        }
                        Spacer()
                        if let reason = site.suggestionReason {
                            Image(systemName: "sparkles")
                                .font(.caption2).foregroundStyle(.tertiary).help(reason)
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
                    Stepper(value: request.minLength, in: 20...400) {
                        Text("\(request.wrappedValue.minLength) aa").monospacedDigit()
                    }
                }
                GridRow {
                    Text("Longest")
                    Stepper(value: request.maxLength, in: request.wrappedValue.minLength...500) {
                        Text("\(request.wrappedValue.maxLength) aa").monospacedDigit()
                    }
                }
                GridRow {
                    Text("How many designs")
                    Stepper(value: request.numDesigns, in: 1...5000, step: 10) {
                        Text("\(request.wrappedValue.numDesigns)").monospacedDigit()
                    }
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
            get: { request.wrappedValue.verification.extraPredictors.contains(p) },
            set: { on in
                var v = request.wrappedValue.verification
                if on { v.extraPredictors.append(p) } else { v.extraPredictors.removeAll { $0 == p } }
                request.wrappedValue.verification = v
            }
        )) {
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 6) {
                    Text(p.label)
                    if request.wrappedValue.verification.intellifoldModel == .v2
                        && (p == .intellifold || p == .intellifoldJAX) {
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
        .disabled(!installed || !wired)
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
                if request.wrappedValue.verification.extraPredictors.contains(where: {
                    $0 == .intellifold || $0 == .intellifoldJAX
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
                Stepper(value: request.verification.topN, in: 10...500, step: 10) {
                    Text("\(request.wrappedValue.verification.topN)").monospacedDigit()
                }
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
            Label("\(folds * engines) folds in total. This stage will dominate the run — expect days, not hours, at this scale.",
                  systemImage: "clock")
                .font(.caption)
                .foregroundStyle(folds * engines > 1000 ? .orange : .secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: Sampling

    private var samplingSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 10) {
                GridRow {
                    Text("Batch size")
                    Stepper(value: request.batchSize, in: 1...32) {
                        Text("\(request.wrappedValue.batchSize)").monospacedDigit()
                    }
                }
                GridRow {
                    Text("Concurrent queues")
                    Stepper(value: request.queuesPerBin, in: 1...4) {
                        Text("\(request.wrappedValue.queuesPerBin)").monospacedDigit()
                    }
                }
                GridRow {
                    Text("Diffusion steps")
                    Stepper(value: request.timesteps, in: 20...500, step: 10) {
                        Text("\(request.wrappedValue.timesteps)").monospacedDigit()
                    }
                }
                GridRow {
                    Text("Length bins")
                    Stepper(value: request.numBins, in: 1...30) {
                        Text("\(request.wrappedValue.numBins)").monospacedDigit()
                    }
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
        return VStack(alignment: .leading, spacing: 8) {
            ForEach(issues, id: \.self) { issue in
                Label(issue, systemImage: "exclamationmark.triangle.fill")
                    .font(.callout).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
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
                .disabled(!r.isRunnable || !issues.isEmpty || anotherWorkflowIsRunning)
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
                Label("This campaign keeps running if you quit Studio — it is detached and holds the Mac awake. Reopen this project to check on it.",
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
            Button { NSWorkspace.shared.activateFileViewerSelecting([root.appendingPathComponent("analysis")]) } label: {
                Label("Open Results", systemImage: "list.number")
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: 12).fill(Color.green.opacity(0.09)))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Ranked RFdiffusion3 results ready. \(summary)")
    }

    private var summary: String {
        guard let first = rows.first else { return "Open the campaign folder to inspect its outputs." }
        let score = first["score"] as? Double
        let metric = first["mean_iptm"] != nil ? "mean iPTM" : "score"
        if let score { return "\(rows.count) selected design(s); top \(metric) \(String(format: "%.3f", score))." }
        return "\(rows.count) selected design(s)."
    }
}
