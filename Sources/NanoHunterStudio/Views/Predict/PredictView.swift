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

    @State private var warnings: [String] = []
    @State private var parseError: String?
    @State private var isParsing = false

    private var request: Binding<PredictionRequest> {
        Binding(get: { app.selectedProject?.prediction ?? project.prediction },
                set: { nv in app.updateSelected { $0.prediction = nv } })
    }

    private var outputDir: URL {
        AppPaths.projectDir(project).appendingPathComponent("predictions", isDirectory: true)
    }

    var body: some View {
        if controller.isRunning || controller.outputRoot != nil {
            PredictProgressView(controller: controller)
        } else {
            form
        }
    }

    private var form: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                Card(title: "1 · Sequences", systemImage: "text.alignleft") { sequencesSection }
                Card(title: "2 · How to fold them", systemImage: "square.on.square") { pairingSection }
                Card(title: "3 · Alignments", systemImage: "square.stack.3d.down.right") { msaSection }
                Card(title: "4 · Engines", systemImage: "cpu") { engineSection }
                Card(title: "5 · Throughput", systemImage: "gauge.with.dots.needle.67percent") { throughputSection }
                startBar
            }
            .padding(28).frame(maxWidth: 860, alignment: .leading).frame(maxWidth: .infinity)
        }
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
            Text("Paste sequences — one per line, or FASTA — or choose a file.")
                .font(.caption).foregroundStyle(.secondary)
            SequenceEditor(text: request.pastedSequences, placeholder: "Paste sequences or FASTA…")

            HStack {
                Button("Choose a FASTA or CSV…") {
                    let panel = NSOpenPanel()
                    panel.allowedContentTypes = [.commaSeparatedText, .plainText,
                                                 UTType(filenameExtension: "fasta") ?? .plainText]
                    panel.allowsMultipleSelection = false
                    if panel.runModal() == .OK, let url = panel.url {
                        request.wrappedValue.sequenceFile = url.path
                    }
                }
                if !request.wrappedValue.sequenceFile.isEmpty {
                    Text((request.wrappedValue.sequenceFile as NSString).lastPathComponent)
                        .font(.caption).lineLimit(1).truncationMode(.middle)
                    Button("Clear") { request.wrappedValue.sequenceFile = "" }.controlSize(.small)
                }
                Spacer()
                Button { parse() } label: {
                    Label("Read sequences", systemImage: "arrow.right.doc.on.clipboard")
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

    private var jobList: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("\(request.wrappedValue.jobs.count) fold(s) ready").font(.callout.weight(.medium))
            ScrollView {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(request.wrappedValue.jobs.prefix(60)) { job in
                        HStack {
                            Text(job.name).font(.system(.caption, design: .monospaced))
                            Spacer()
                            Text(job.summary).font(.caption2).foregroundStyle(.secondary)
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
            Text(request.wrappedValue.pairing.blurb)
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if request.wrappedValue.pairing == .shared {
                Text("Partner").font(.callout.weight(.medium))
                SequenceEditor(text: request.partnerSequence, placeholder: "Partner protein sequence…")
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
            Text(selection.wrappedValue.blurb)
                .font(.caption2).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: Engines

    private var engineSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Predictor.checkChoices.filter { $0 != .boltzPotentials }) { predictor in
                engineRow(predictor)
            }
            Divider().padding(.vertical, 2)
            Toggle("Boltz steering potentials", isOn: request.useBoltzPotentials)
                .toggleStyle(.checkbox).font(.callout)
            Toggle("Predict binding strength for small molecules", isOn: request.runAffinityHead)
                .toggleStyle(.checkbox).font(.callout)
            Text("The affinity head is Boltz-only and small-molecule-only.")
                .font(.caption2).foregroundStyle(.secondary)
        }
    }

    @ViewBuilder private func engineRow(_ predictor: Predictor) -> some View {
        let installed = app.installer.isUsable(predictor.component)
        Toggle(isOn: Binding(
            get: { request.wrappedValue.predictors.contains(predictor) },
            set: { on in
                var list = request.wrappedValue.predictors
                if on { list.append(predictor) } else { list.removeAll { $0 == predictor } }
                request.wrappedValue.predictors = list
            })) {
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 6) {
                    Text(predictor.label)
                    Text(predictor.speed(in: .batched).label)
                        .font(.caption).foregroundStyle(.secondary)
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
        .disabled(!installed)
    }

    // MARK: Throughput

    private var throughputSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Folds are grouped by size so a compiled shape is reused, and each engine runs at the process count and batch size measured fastest for it. Leave these alone unless you have a reason.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 8) {
                GridRow {
                    Text("Concurrent processes").font(.callout)
                    Stepper(value: request.maxParallel, in: 0...8) {
                        Text(request.wrappedValue.maxParallel == 0
                             ? "measured optimum" : "\(request.wrappedValue.maxParallel)")
                            .monospacedDigit()
                    }
                }
                GridRow {
                    Text("Folds per model load").font(.callout)
                    Stepper(value: request.batchSize, in: 0...32) {
                        Text(request.wrappedValue.batchSize == 0
                             ? "measured optimum" : "\(request.wrappedValue.batchSize)")
                            .monospacedDigit()
                    }
                }
            }
            if request.wrappedValue.maxParallel != 0 || request.wrappedValue.batchSize != 0 {
                Label("Overriding these discards the per-engine measurements — Boltz saturates the GPU with one process, IntelliFold wants four.",
                      systemImage: "exclamationmark.triangle")
                    .font(.caption).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !request.wrappedValue.jobs.isEmpty {
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
        return VStack(alignment: .leading, spacing: 8) {
            ForEach(issues, id: \.self) { issue in
                Label(issue, systemImage: "exclamationmark.triangle.fill")
                    .font(.callout).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack {
                if r.jobs.isEmpty {
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
                .disabled(!r.isRunnable || !issues.isEmpty)
            }
        }
        .padding(.top, 6)
    }

    private func parse() {
        isParsing = true
        parseError = nil
        warnings = []
        controller.buildJobs(request: request.wrappedValue,
                             workDir: outputDir.appendingPathComponent("input")) { jobs, notes, error in
            isParsing = false
            parseError = error
            warnings = notes
            request.wrappedValue.jobs = jobs
        }
    }
}

/// Live progress for a running batch.
struct PredictProgressView: View {
    @ObservedObject var controller: PredictionController

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
                Label(message, systemImage: "exclamationmark.triangle.fill")
                    .font(.callout).foregroundStyle(.orange)
                    .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
            }

            Text("Log").font(.headline)
            ScrollView {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(Array(controller.log.suffix(200).enumerated()), id: \.offset) { _, line in
                        Text(line).font(.system(.caption, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }.padding(8)
            }
            .background(RoundedRectangle(cornerRadius: 8).fill(.background))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))

            if let root = controller.outputRoot {
                Button { NSWorkspace.shared.activateFileViewerSelecting([root]) } label: {
                    Label("Show results", systemImage: "folder")
                }.controlSize(.small)
            }
            Spacer(minLength: 0)
        }
        .padding(28).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}
