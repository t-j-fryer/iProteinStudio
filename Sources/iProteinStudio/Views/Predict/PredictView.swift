import SwiftUI
import UniformTypeIdentifiers

/// Fold sequences. No design, no optimisation loop — just prediction.
///
/// What Studio adds over running a predictor by hand is the work around the
/// folding: reusing every alignment this machine has already made, letting each
/// chain decide whether it wants one at all, and running each engine at the
/// process count and batch size that was measured fastest for it.
struct PredictView: View {
    @EnvironmentObject var app: AppState
    let project: Project
    @ObservedObject var controller: PredictionController
    @ObservedObject var installer: PipelineInstaller

    @State private var warnings: [String] = []
    @State private var parseError: String?
    @State private var isParsing = false
    @State private var setupExperience: SetupExperience = .quick

    private var request: Binding<PredictionRequest> {
        Binding(get: { app.selectedProject?.prediction ?? project.prediction },
                set: { nv in app.updateSelected { $0.prediction = nv } })
    }

    private var outputDir: URL {
        AppPaths.projectDir(project).appendingPathComponent("prediction_runs", isDirectory: true)
    }

    private var inputDir: URL {
        AppPaths.projectDir(project).appendingPathComponent("prediction_input", isDirectory: true)
    }

    var body: some View {
        if controller.isRunning || controller.outputRoot != nil {
            PredictProgressView(controller: controller)
        } else {
            form
        }
    }

    private var form: some View {
        VStack(spacing: 0) {
            ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                SetupExperiencePicker(selection: $setupExperience)
                ExamplesBar(kinds: [.protein]) { example in
                    request.wrappedValue.apply(example)
                    parse()
                }
                Card(title: "1 · Sequences", systemImage: "text.alignleft") { sequencesSection }
                Card(title: "2 · How to fold them", systemImage: "square.on.square") { pairingSection }
                if setupExperience == .advanced {
                    Card(title: "3 · Alignments", systemImage: "square.stack.3d.down.right") { msaSection }
                }
                Card(title: "4 · Engines", systemImage: "cpu") { engineSection }
                if setupExperience == .advanced {
                    Card(title: "5 · Sampling & throughput", systemImage: "gauge.with.dots.needle.67percent") { throughputSection }
                } else {
                    Label("Alignments are reused automatically; measured throughput settings remain selected.",
                          systemImage: "checkmark.seal")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .padding(28).frame(maxWidth: 860, alignment: .leading).frame(maxWidth: .infinity)
            }
            Divider()
            startBar.padding(.horizontal, 28).padding(.vertical, 14)
                .background(.bar)
        }
        .onAppear { normalizeEngineOptions() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Predict").font(.largeTitle.bold())
            Text("Fold sequences you already have. Nothing is designed or optimised here.")
                .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: Sequences

    private var sequencesSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Paste folds — one per line or FASTA record. Separate chains within one fold with a colon.")
                .font(.caption).foregroundStyle(.secondary)
            SequenceEditor(text: Binding(
                get: { request.wrappedValue.pastedSequences },
                set: { value in
                    request.wrappedValue.pastedSequences = value
                    if !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        request.wrappedValue.sequenceFile = ""
                    }
                }
            ), placeholder: "Paste sequences or FASTA…")
            if pastedInputIsOneFold {
                ProteinChainSummaryView(text: request.wrappedValue.pastedSequences,
                                        startingAt: 0, minimumLength: 1)
            }

            HStack {
                Button("Choose a FASTA or CSV…") {
                    let panel = NSOpenPanel()
                    panel.allowedContentTypes = [.commaSeparatedText, .plainText,
                                                 UTType(filenameExtension: "fasta") ?? .plainText]
                    panel.allowsMultipleSelection = false
                    if panel.runModal() == .OK, let url = panel.url {
                        request.wrappedValue.sequenceFile = url.path
                        request.wrappedValue.pastedSequences = ""
                    }
                }
                if !request.wrappedValue.sequenceFile.isEmpty {
                    Text((request.wrappedValue.sequenceFile as NSString).lastPathComponent)
                        .font(.caption).lineLimit(1).truncationMode(.middle)
                    Button("Clear") { request.wrappedValue.sequenceFile = "" }.controlSize(.small)
                }
                Spacer()
                Button { parse() } label: {
                    Label("Read & assign chains", systemImage: "arrow.right.doc.on.clipboard")
                }
                .disabled(isParsing || (request.wrappedValue.pastedSequences.isEmpty
                                        && request.wrappedValue.sequenceFile.isEmpty))
                if isParsing { ProgressView().controlSize(.small) }
            }

            Text("A CSV can carry a partner per row. Column names are matched loosely — binder / sequence / seq, and target / partner / chain_b — and a smiles column makes the partner a small molecule.")
                .font(.caption2).foregroundStyle(.tertiary)
                .fixedSize(horizontal: false, vertical: true)

            if let parseError {
                Label(parseError, systemImage: "exclamationmark.triangle.fill")
                    .font(.callout).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            ForEach(warnings, id: \.self) { warning in
                Label(warning, systemImage: "info.circle").font(.caption2).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !request.wrappedValue.jobs.isEmpty { jobList }
        }
    }

    private var pastedInputIsOneFold: Bool {
        let input = request.wrappedValue.pastedSequences
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !input.isEmpty, !input.contains(">") else { return false }
        return input.split(whereSeparator: \.isNewline).count == 1
    }

    private var jobList: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("\(request.wrappedValue.jobs.count) fold(s) ready").font(.callout.weight(.medium))
            ScrollView {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(request.wrappedValue.jobs.prefix(60)) { job in
                        DisclosureGroup {
                            VStack(alignment: .leading, spacing: 3) {
                                ForEach(job.chains) { chain in
                                    HStack(alignment: .firstTextBaseline) {
                                        Text("Chain \(chain.id)").font(.caption2.weight(.semibold))
                                        Text(chain.kind == "protein" ? chain.sequence : chain.smiles)
                                            .font(.system(.caption2, design: .monospaced))
                                            .textSelection(.enabled).lineLimit(2)
                                    }
                                }
                            }.padding(.vertical, 3)
                        } label: {
                            HStack {
                                Text(job.name).font(.system(.caption, design: .monospaced))
                                Spacer()
                                Text(job.summary).font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                    }
                    if request.wrappedValue.jobs.count > 60 {
                        Text("…and \(request.wrappedValue.jobs.count - 60) more")
                            .font(.caption2).foregroundStyle(.tertiary)
                    }
                }.padding(8)
            }
            .frame(maxHeight: 160)
            .background(RoundedRectangle(cornerRadius: 8).fill(.background))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
        }
    }

    // MARK: Pairing

    private var pairingSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Picker("", selection: request.pairing) {
                ForEach(PairingMode.allCases) { Text($0.label).tag($0) }
            }.pickerStyle(.segmented).labelsHidden()
                .accessibilityLabel("Pairing mode")
            Text(request.wrappedValue.pairing.blurb)
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if request.wrappedValue.pairing == .shared {
                Text("Partner").font(.callout.weight(.medium))
                SequenceEditor(text: request.partnerSequence, placeholder: "Partner protein sequence…")
                ProteinChainSummaryView(text: request.wrappedValue.partnerSequence,
                                        startingAt: 0, minimumLength: 5,
                                        showsAssignedIDs: false)
                Text("Separate partner subunits with a colon. Their final chain IDs follow the query chains and are shown after you read the batch.")
                    .font(.caption2).foregroundStyle(.secondary)
                HStack {
                    Text("…or a small molecule").font(.caption).foregroundStyle(.secondary)
                    TextField("SMILES", text: request.partnerSmiles)
                        .textFieldStyle(.roundedBorder)
                        .font(.system(.caption, design: .monospaced))
                }
            }
            Text("Changing this needs the sequences read again.")
                .font(.caption2).foregroundStyle(.tertiary)
        }
    }

    // MARK: Alignments

    private var msaSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Alignments are usually the slow part, and they are a per-chain decision — a designed binder and its natural target want opposite treatment.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            policyPicker("Your sequences", selection: request.binderMSA)
            if request.wrappedValue.pairing != .monomer {
                policyPicker("Their partner", selection: request.partnerMSA)
            }

            Divider().padding(.vertical, 2)
            Toggle("Only use alignments already on this Mac", isOn: request.offlineOnly)
                .toggleStyle(.checkbox).font(.callout)
                .accessibilityLabel("Only use cached alignments")
            Text("Every alignment this app or a design run has ever made is reused automatically either way. This just refuses to make new ones, and stops rather than folding without.")
                .font(.caption2).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func policyPicker(_ title: String, selection: Binding<MSAPolicy>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.callout.weight(.medium))
            Picker("", selection: selection) {
                ForEach(MSAPolicy.allCases) { Text($0.label).tag($0) }
            }.pickerStyle(.segmented).labelsHidden().frame(width: 320)
                .accessibilityLabel("Alignment policy for \(title)")
            Text(selection.wrappedValue.blurb)
                .font(.caption2).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: Engines

    private var engineSection: some View {
        let boltzSelected = request.wrappedValue.includesBoltz
        let containsLigand = request.wrappedValue.containsLigand
        return VStack(alignment: .leading, spacing: 8) {
            ForEach(Predictor.predictionChoices) { predictor in
                engineRow(predictor)
            }
            Text("IntelliFold uses its validated PyTorch/Metal implementation. AlphaFold 3 and IntelliFold JAX are not offered because their Metal paths failed same-input quality control.")
                .font(.caption2).foregroundStyle(.tertiary)
                .fixedSize(horizontal: false, vertical: true)
            if request.wrappedValue.effectivePredictors.contains(where: {
                $0 == .intellifold
            }) {
                Picker("IntelliFold model", selection: request.intellifoldModel) {
                    ForEach(IntelliFoldModel.allCases) { model in
                        Text(model.label).tag(model)
                    }
                }
                .pickerStyle(.menu)
                Text("The choice applies to IntelliFold PyTorch predictions in this batch.")
                    .font(.caption2).foregroundStyle(.secondary)
            }
            Divider().padding(.vertical, 2)
            Text("Boltz-2 options").font(.callout.weight(.medium))
            Toggle("Boltz steering potentials", isOn: request.useBoltzPotentials)
                .toggleStyle(.checkbox).font(.callout)
                .disabled(!boltzSelected)
                .accessibilityLabel("Boltz steering potentials")
                .accessibilityHint(boltzSelected
                    ? "Applies only to folds run with Boltz-2"
                    : "Select Boltz-2 to enable steering potentials")
            Toggle("Predict binding strength for small molecules", isOn: request.runAffinityHead)
                .toggleStyle(.checkbox).font(.callout)
                .disabled(!boltzSelected || !containsLigand)
                .accessibilityLabel("Predict small-molecule binding strength")
                .accessibilityHint(!boltzSelected
                    ? "Select Boltz-2 to enable binding-strength prediction"
                    : "A parsed fold must contain a small molecule")
            Text(boltzOptionsExplanation(boltzSelected: boltzSelected,
                                         containsLigand: containsLigand))
                .font(.caption2).foregroundStyle(.secondary)
        }
    }

    @ViewBuilder private func engineRow(_ predictor: Predictor) -> some View {
        let installed = installer.isUsable(predictor.component)
        Toggle(isOn: Binding(
            get: { request.wrappedValue.effectivePredictors.contains(predictor) },
            set: { on in
                var list = request.wrappedValue.predictors
                if on { list.append(predictor.checkingVariant) }
                else { list.removeAll { $0.runnerValue == predictor.runnerValue } }
                var updated = request.wrappedValue
                updated.predictors = list
                updated.normalizeEngineOptions()
                request.wrappedValue = updated
            })) {
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 6) {
                    Text(predictor.label)
                    if request.wrappedValue.intellifoldModel == .v2
                        && predictor == .intellifold {
                        Text("not benchmarked").font(.caption).foregroundStyle(.secondary)
                    } else {
                        Text(predictor.speed(in: .batched).label)
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if !installed {
                        Label("not installed", systemImage: "exclamationmark.circle")
                            .font(.caption2).foregroundStyle(.orange)
                    }
                }
                Text(predictor.blurb).font(.caption2).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .toggleStyle(.checkbox)
        .accessibilityLabel(predictor.label)
        .disabled(!installed && !request.wrappedValue.effectivePredictors.contains(predictor))
    }

    private func boltzOptionsExplanation(boltzSelected: Bool, containsLigand: Bool) -> String {
        if !boltzSelected {
            return "Select Boltz-2 to use either option. They do not apply to IntelliFold or OpenFold-3."
        }
        if !containsLigand {
            return "Steering applies to Boltz-2. Binding strength also needs at least one parsed fold containing a small molecule."
        }
        return "These settings apply only to the Boltz-2 portion of this batch; other selected engines keep their own defaults."
    }

    private func normalizeEngineOptions() {
        var updated = request.wrappedValue
        let original = updated
        updated.normalizeEngineOptions()
        if updated != original { request.wrappedValue = updated }
    }

    // MARK: Throughput

    private var throughputSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Sampling").font(.callout.weight(.semibold))
            Text("More seeds and diffusion samples explore more stochastic outputs. They multiply work and disk use; one of each is normally enough for a first pass.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 8) {
                GridRow {
                    Text("Seeds per fold").font(.callout)
                    EditableIntStepper(value: request.numberOfSeeds, in: 1...20,
                                       accessibilityLabel: "Seeds per fold")
                }
                GridRow {
                    Text("Diffusion samples").font(.callout)
                    HStack(spacing: 7) {
                        EditableIntStepper(value: request.diffusionSamples, in: 0...20,
                                           accessibilityLabel: "Diffusion samples")
                        if request.wrappedValue.diffusionSamples == 0 {
                            Text("existing engine defaults").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            Text("At 0, Studio preserves validated engine defaults: Boltz-2, IntelliFold, Protenix Constraint and OpenFold-3 use one diffusion sample; Protenix v2 and Mini use five. Boltz supports diffusion samples but only one model seed per fold; additional seeds apply to the other engines.")
                .font(.caption2).foregroundStyle(.tertiary)
                .fixedSize(horizontal: false, vertical: true)
            Divider().padding(.vertical, 2)
            Text("Folds are grouped by size so a compiled shape is reused, and each engine runs at the process count and batch size measured fastest for it. Leave these alone unless you have a reason.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 8) {
                GridRow {
                    Text("Concurrent processes").font(.callout)
                    HStack(spacing: 7) {
                        EditableIntStepper(value: request.maxParallel, in: 0...8,
                                           accessibilityLabel: "Concurrent processes")
                        if request.wrappedValue.maxParallel == 0 {
                            Text("measured optimum").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
                GridRow {
                    Text("Folds per model load").font(.callout)
                    HStack(spacing: 7) {
                        EditableIntStepper(value: request.batchSize, in: 0...32,
                                           accessibilityLabel: "Folds per model load")
                        if request.wrappedValue.batchSize == 0 {
                            Text("measured optimum").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            if request.wrappedValue.maxParallel != 0 || request.wrappedValue.batchSize != 0 {
                Label("Overriding these discards the per-engine measurements — Boltz saturates the GPU with one process, IntelliFold wants four.",
                      systemImage: "exclamationmark.triangle")
                    .font(.caption).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            let fullV2Selected = request.wrappedValue.intellifoldModel == .v2
                && request.wrappedValue.effectivePredictors.contains {
                    $0 == .intellifold
                }
            if !request.wrappedValue.jobs.isEmpty, fullV2Selected {
                Label("No time estimate: full IntelliFold v2 has not been benchmarked on this Mac yet.",
                      systemImage: "clock")
                    .font(.callout).foregroundStyle(.secondary)
            } else if !request.wrappedValue.jobs.isEmpty {
                Label("Rough estimate: at least \(formatted(request.wrappedValue.estimatedSeconds(in: .batched))) of folding, plus any new alignments.",
                      systemImage: "clock")
                    .font(.callout).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
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
        let anotherWorkflowIsRunning = app.run.isRunning || app.rfd3.isRunning
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
                    Label("Finish or stop the active \(app.rfd3.isRunning ? "RFdiffusion3" : "iterative design") run before starting prediction.",
                          systemImage: "hourglass")
                        .font(.callout).foregroundStyle(.secondary)
                } else if r.jobs.isEmpty {
                    Label("Read some sequences to continue.", systemImage: "info.circle")
                        .font(.callout).foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    controller.start(request: r, outputDir: outputDir)
                } label: {
                    Label("Fold \(r.jobs.count) sequence\(r.jobs.count == 1 ? "" : "s")",
                          systemImage: "play.fill").frame(minWidth: 200)
                }
                .buttonStyle(.borderedProminent).controlSize(.large)
                .accessibilityLabel("Start prediction run for \(r.jobs.count) sequence\(r.jobs.count == 1 ? "" : "s")")
                .accessibilityIdentifier("start-prediction-run")
                .disabled(!r.isRunnable || !issues.isEmpty || !missingComponents.isEmpty
                          || anotherWorkflowIsRunning)
            }
        }
        .padding(.top, 6)
    }

    private func parse() {
        isParsing = true
        parseError = nil
        warnings = []
        controller.buildJobs(request: request.wrappedValue,
                             workDir: inputDir) { jobs, notes, error in
            isParsing = false
            parseError = error
            warnings = notes
            var updated = request.wrappedValue
            updated.jobs = jobs
            updated.parsedInputSignature = jobs.isEmpty ? "" : updated.inputSignature
            updated.normalizeEngineOptions()
            request.wrappedValue = updated
        }
    }
}

/// Live progress for a running batch.
struct PredictProgressView: View {
    @ObservedObject var controller: PredictionController
    @State private var showResults = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Folding").font(.title2.bold())
                    Text(controller.currentMessage).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
                if controller.isRunning {
                    Button("Stop", role: .destructive) { controller.cancel() }
                } else {
                    Button("Back") { controller.outputRoot = nil; controller.phase = .idle }
                }
            }
            ProgressView(value: controller.progress).progressViewStyle(.linear)

            if let hits = controller.cacheHits {
                Label(hits, systemImage: "arrow.triangle.2.circlepath")
                    .font(.callout).foregroundStyle(.green)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if case .failed(let message) = controller.phase {
                ActionableErrorCard(title: "Prediction needs attention", message: message,
                                    retryTitle: "Retry failed work", retry: controller.retry,
                                    output: controller.outputRoot, log: controller.log)
            }

            if case .failed = controller.phase {
                EmptyView()
            } else {
                TechnicalLogDisclosure(lines: controller.log)
            }

            if let root = controller.outputRoot {
                HStack {
                    if !controller.isRunning {
                        Button { showResults = true } label: {
                            Label("View Results", systemImage: "cube.transparent")
                        }
                        .buttonStyle(.borderedProminent)
                        .accessibilityIdentifier("view-prediction-results")
                    }
                    Button { NSWorkspace.shared.activateFileViewerSelecting([root]) } label: {
                        Label("Reveal Folder", systemImage: "folder")
                    }
                    .controlSize(.small)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(28).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .sheet(isPresented: $showResults) {
            if let root = controller.outputRoot {
                RunResultsView(root: root, workflow: .prediction)
            }
        }
    }
}
