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
    @StateObject private var inspector = RFD3TargetInspector()
    @State private var showAdvanced = false

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
            if let existing = app.installer.detectedRFD3 {
                Button {
                    app.installer.linkExisting(nanoHunter: nil, rfd3: existing)
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
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header

                Card(title: "1 · What are you designing against?", systemImage: "target") {
                    targetKindPicker
                    if request.wrappedValue.targetKind == .smallMolecule {
                        ligandInput
                    } else {
                        proteinInput
                    }
                }

                if inspector.hasResult || inspector.isInspecting || inspector.error != nil {
                    Card(title: "2 · Shape the binding site", systemImage: "hand.point.up.left") {
                        conditioningSection
                    }
                }

                Card(title: "3 · Binder size", systemImage: "ruler") {
                    lengthSection
                }

                Card(title: "4 · Verify with", systemImage: "checkmark.seal") {
                    verificationSection
                }

                Card(title: "5 · Sampling", systemImage: "gauge.with.dots.needle.67percent") {
                    DisclosureGroup("Advanced sampling settings", isExpanded: $showAdvanced) {
                        samplingSection
                    }.font(.callout)
                    estimateRow
                }

                startBar
            }
            .padding(28).frame(maxWidth: 860, alignment: .leading).frame(maxWidth: .infinity)
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
                    request.wrappedValue.targetKind = nv
                    request.wrappedValue.conditions = [:]
                    request.wrappedValue.originStrategy = nv == .smallMolecule ? .com : .hotspots
                    inspector.reset()
                }
            )) {
                ForEach(RFD3TargetKind.allCases) { Text($0.label).tag($0) }
            }
            .pickerStyle(.segmented).labelsHidden().frame(width: 320)
            Text(request.wrappedValue.targetKind.blurb)
                .font(.caption).foregroundStyle(.secondary)
            Label("Sequences will be designed with \(request.wrappedValue.targetKind.sequenceModelLabel).",
                  systemImage: "info.circle")
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    @ViewBuilder private var ligandInput: some View {
        VStack(alignment: .leading, spacing: 10) {
            Picker("", selection: request.ligandSource) {
                ForEach(LigandSource.allCases) { Text($0.label).tag($0) }
            }.pickerStyle(.segmented).labelsHidden().frame(width: 340)
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
            filePicker(path: request.targetStructurePath,
                       prompt: "Choose your target structure (PDB)",
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
            Label("RFdiffusion3 designs against a structure, not a sequence. If you only have a sequence, predict it first in the design tab.",
                  systemImage: "info.circle")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
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

    private var verificationSection: some View {
        let kind = request.wrappedValue.targetKind
        return VStack(alignment: .leading, spacing: 10) {
            if kind.supportsVerification {
                Text("Designed sequences are folded back with the ligand present, scored by ligand pLDDT plus predicted binding probability, and the best ones are folded again on their own.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                LabeledContent("Sequences per backbone") {
                    Stepper(value: request.sequencesPerBackbone, in: 1...16) {
                        Text("\(request.wrappedValue.sequencesPerBackbone)").monospacedDigit()
                    }
                }
                LabeledContent("Keep the best") {
                    Stepper(value: request.verification.topN, in: 10...500, step: 10) {
                        Text("\(request.wrappedValue.verification.topN)").monospacedDigit()
                    }
                }

                Divider().padding(.vertical, 2)
                Toggle("Also fold the best designs on their own, without the ligand",
                       isOn: request.verification.runApoCheck)
                    .toggleStyle(.checkbox)
                Text("Comparing the two tells you whether the binding site is already formed before the ligand arrives, or only assembles around it.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                Label("Folding uses Boltz-2 with steering potentials and the affinity head. That combination is fixed: it is the only backend with an affinity head, and the ranking metric needs it.",
                      systemImage: "info.circle")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                let folds = request.wrappedValue.numDesigns * request.wrappedValue.sequencesPerBackbone
                Label("That is \(folds) folds with affinity enabled, which will dominate the run time — expect days, not hours, at this scale.",
                      systemImage: "clock")
                    .font(.caption).foregroundStyle(folds > 1000 ? .orange : .secondary)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                LabeledContent("Sequences per backbone") {
                    Stepper(value: request.sequencesPerBackbone, in: 1...16) {
                        Text("\(request.wrappedValue.sequencesPerBackbone)").monospacedDigit()
                    }
                }
                Label("Protein-target runs stop after sequence design. Folding a designed complex needs a target MSA that can't be built from an RFdiffusion3 spec alone — take the sequences to the Iterative design tab to check them.",
                      systemImage: "exclamationmark.triangle.fill")
                    .font(.callout).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
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
        return VStack(alignment: .leading, spacing: 8) {
            ForEach(issues, id: \.self) { issue in
                Label(issue, systemImage: "exclamationmark.triangle.fill")
                    .font(.callout).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack {
                if !r.isRunnable {
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
                .disabled(!r.isRunnable || !issues.isEmpty)
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

    private let stageOrder: [(String, String)] = [
        ("validate", "Target"), ("fixtures", "Length bins"), ("backbones", "Backbones"),
        ("mpnn", "Sequences"), ("predict-holo", "Folding"), ("score", "Ranking"),
        ("predict-apo", "Apo folding"), ("rmsd", "Preorganisation"),
    ]

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
                Label(message, systemImage: "exclamationmark.triangle.fill")
                    .font(.callout).foregroundStyle(.orange)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if !controller.log.isEmpty {
                Text("Log").font(.headline)
                ScrollView {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(Array(controller.log.suffix(200).enumerated()), id: \.offset) { _, line in
                            Text(line)
                                .font(.system(.caption, design: .monospaced))
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    .padding(8)
                }
                .frame(maxHeight: 220)
                .background(RoundedRectangle(cornerRadius: 8).fill(.background))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
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
