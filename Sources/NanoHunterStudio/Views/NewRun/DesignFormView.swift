import SwiftUI

/// Guided design form. Adapts to the chosen design type (nanobody vs de-novo
/// mini-binder / peptide). Sensible defaults; advanced options tucked away.
struct DesignFormView: View {
    @EnvironmentObject var app: AppState
    let project: Project
    @State private var showAdvanced = false
    @State private var showTargetPrep = false

    private var request: Binding<DesignRequest> {
        Binding(
            get: { app.selectedProject?.request ?? project.request },
            set: { nv in app.updateSelected { $0.request = nv } }
        )
    }

    private var type: DesignType { request.wrappedValue.designType }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header

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
                    Text(type.blurb).font(.caption).foregroundStyle(.secondary)
                }

                Card(title: "1 · Your target", systemImage: "target") {
                    Picker("", selection: Binding(
                        get: { request.wrappedValue.targetKind },
                        set: { nv in
                            var r = request.wrappedValue
                            r.targetKind = nv
                            r.reconcileDesigner()
                            request.wrappedValue = r
                        }
                    )) {
                        ForEach(TargetKind.allCases) { Text($0.label).tag($0) }
                    }
                    .pickerStyle(.segmented).labelsHidden().frame(width: 320)

                    if request.wrappedValue.targetKind == .protein {
                        Text("Paste the amino-acid sequence of the protein you want to bind.")
                            .font(.callout).foregroundStyle(.secondary)
                        SequenceEditor(text: request.targetSequence, placeholder: "Target sequence (chain B)…")
                        HStack {
                            Text("Length: \(TemplateWriter.clean(request.wrappedValue.targetSequence).count) aa")
                                .font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            TextField("Epitope hotspots (optional, e.g. 32 55)", text: request.epitopeResidues)
                                .textFieldStyle(.roundedBorder).frame(width: 240)
                                .help("Target residue numbers to steer binding toward. The target chain (B) is added automatically.")
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
                    }
                }

                if type.usesScaffold {
                    Card(title: "2 · Nanobody scaffold", systemImage: "cube") {
                        Text("Choose a validated VHH framework. CDR loops are redesigned; the framework stays fixed.")
                            .font(.callout).foregroundStyle(.secondary)
                        ScaffoldPicker(request: request)
                    }
                    Card(title: "3 · What to design", systemImage: "slider.horizontal.3") {
                        CDRPicker(cdrs: request.cdrs)
                        Divider().padding(.vertical, 4)
                        DesignerPicker(designer: request.designer, allowed: request.wrappedValue.allowedDesigners)
                    }
                } else {
                    Card(title: "2 · Binder size & fold", systemImage: "ruler") {
                        BinderSizePicker(request: request)
                        Divider().padding(.vertical, 4)
                        HelixKillControl(value: request.helixKill)
                    }
                    Card(title: "3 · Designer", systemImage: "slider.horizontal.3") {
                        DesignerPicker(designer: request.designer, allowed: request.wrappedValue.allowedDesigners)
                    }
                }

                Card(title: "4 · Run settings", systemImage: "gauge.with.dots.needle.67percent") {
                    RunSettings(request: request)
                    DisclosureGroup("Advanced", isExpanded: $showAdvanced) {
                        AdvancedSettings(request: request, projectDir: AppPaths.projectDir(project))
                    }.font(.callout)
                }

                startBar
            }
            .padding(28).frame(maxWidth: 820, alignment: .leading).frame(maxWidth: .infinity)
        }
        .sheet(isPresented: $showTargetPrep) {
            TargetPrepView(
                targetKind: request.wrappedValue.targetKind,
                targetSequence: request.wrappedValue.targetSequence,
                targetSmiles: request.wrappedValue.targetSmiles,
                onUse: { residues in
                    request.wrappedValue.epitopeResidues = residues.map { "B\($0)" }.joined(separator: " ")
                },
                onClose: { showTargetPrep = false }
            )
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(project.name).font(.largeTitle.bold())
            Text("Set up your design run, then press Start.").foregroundStyle(.secondary)
        }
    }

    private var startBar: some View {
        HStack(spacing: 12) {
            let r = request.wrappedValue
            if !r.isRunnable {
                Label(missingReason(r), systemImage: "info.circle").font(.callout).foregroundStyle(.secondary)
            }
            Spacer()
            Button {
                app.metrics.stop()
                app.run.start(project: app.selectedProject ?? project)
                if let root = app.run.campaignRoot { app.metrics.start(root: root) }
            } label: {
                Label("Start Design Run", systemImage: "play.fill").frame(minWidth: 200)
            }
            .buttonStyle(.borderedProminent).controlSize(.large).disabled(!r.isRunnable)
        }
        .padding(.top, 6)
    }

    private func missingReason(_ r: DesignRequest) -> String {
        if r.targetKind == .protein && r.targetSequence.isEmpty { return "Add a target sequence to continue." }
        if r.targetKind == .ligand && r.targetSmiles.trimmingCharacters(in: .whitespaces).isEmpty { return "Add a ligand SMILES to continue." }
        if r.designType == .nanobody && r.scaffoldSequence.isEmpty { return "Pick a nanobody scaffold." }
        if r.designType == .nanobody && r.cdrs.isEmpty { return "Select at least one CDR to design." }
        return ""
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
    }
}

struct ScaffoldPicker: View {
    @EnvironmentObject var app: AppState
    @Binding var request: DesignRequest
    var body: some View {
        Picker("Scaffold", selection: Binding(
            get: { request.scaffoldID },
            set: { id in
                request.scaffoldID = id
                if let s = app.scaffolds.first(where: { $0.id == id }) { request.scaffoldSequence = s.sequence }
            }
        )) {
            ForEach(app.scaffolds) { Text($0.displayName).tag($0.id) }
        }
        .pickerStyle(.menu)
        if let s = app.scaffolds.first(where: { $0.id == request.scaffoldID }) {
            Text(s.recommendedUse).font(.caption).foregroundStyle(.secondary)
        }
    }
}

struct BinderSizePicker: View {
    @Binding var request: DesignRequest
    var body: some View {
        Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 10) {
            GridRow {
                Text("Shortest")
                Stepper(value: $request.binderMinLen, in: 1...300) {
                    Text("\(request.binderMinLen) aa").monospacedDigit()
                }
            }
            GridRow {
                Text("Longest")
                Stepper(value: $request.binderMaxLen, in: request.binderMinLen...400) {
                    Text("\(request.binderMaxLen) aa").monospacedDigit()
                }
            }
        }
        Text("Each design gets a random length in this range.").font(.caption).foregroundStyle(.secondary)
    }
}

/// Helix-suppression ("helix-kill") slider for de-novo binders, with
/// effect-size guidance from DSSP of past runs (dTF155–160, chain A, final
/// cycle, mean helix fraction): Boltz ~53%→33% and IntelliFold ~16%→7% from
/// off to max helix-kill.
struct HelixKillControl: View {
    @Binding var value: Double
    private var boltzHelix: Int { Int((53.0 - 20.0 * value).rounded()) }   // 53% → 33%
    private var ifoldHelix: Int { Int((16.0 - 9.0 * value).rounded()) }    // 16% → 7%

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Helix suppression").font(.headline)
                Spacer()
                Text(value < 0.01 ? "Off" : String(format: "%.0f%%", value * 100))
                    .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
            }
            Slider(value: $value, in: 0...1, step: 0.05) {
                Text("Helix suppression")
            } minimumValueLabel: { Text("Off").font(.caption2) }
              maximumValueLabel: { Text("Max").font(.caption2) }
            Text(annotation).font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var annotation: String {
        if value < 0.01 {
            return "Off — de-novo binders can come out quite helical (mean ≈ 53% helix by Boltz, ≈ 16% by IntelliFold)."
        }
        return "Biases the starting design away from α-helices, so cycles favour sheet & loop. "
             + "Expected helix ≈ \(boltzHelix)% (Boltz) · \(ifoldHelix)% (IntelliFold); at Max ≈ 33% / 7%."
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
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Sequence designer").font(.headline)
            Picker("Designer", selection: $designer) {
                ForEach(allowed) { Text($0.label).tag($0) }
            }
            .pickerStyle(.segmented)
            .onAppear { if !allowed.contains(designer) { designer = allowed.first ?? .solublempnn } }
            Text(designer.blurb).font(.caption).foregroundStyle(.secondary)
        }
    }
}

struct RunSettings: View {
    @Binding var request: DesignRequest
    var body: some View {
        Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 12) {
            GridRow {
                Text("Number of designs")
                Stepper(value: $request.numDesigns, in: 1...96) { Text("\(request.numDesigns)").monospacedDigit() }
            }
            GridRow {
                Text("Optimization cycles")
                Stepper(value: $request.numCycles, in: 1...20) { Text("\(request.numCycles)").monospacedDigit() }
            }
            GridRow {
                Text("Hit threshold (iPTM)")
                HStack {
                    Slider(value: $request.hitThreshold, in: 0.3...0.95, step: 0.01).frame(width: 220)
                    Text(String(format: "%.2f", request.hitThreshold)).monospacedDigit()
                }
            }
        }
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
            // --- Parallelisation ---
            VStack(alignment: .leading, spacing: 6) {
                Text("Parallelisation").font(.headline)
                Picker("", selection: $request.parallelMode) {
                    ForEach(ParallelMode.allCases) { Text($0.label).tag($0) }
                }.pickerStyle(.segmented).labelsHidden().frame(width: 300)
                Text(request.parallelMode.blurb).font(.caption).foregroundStyle(.secondary)
                if request.parallelMode == .manual {
                    Stepper(value: $request.manualParallel, in: 1...max(1, cpuCount)) {
                        Text("Run \(request.manualParallel) prediction\(request.manualParallel == 1 ? "" : "s") at once").monospacedDigit()
                    }
                } else if request.parallelMode == .performance {
                    Label("Best when you're not actively using the Mac for other work.",
                          systemImage: "bolt.fill")
                        .font(.caption).foregroundStyle(.orange)
                }
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
                Text("Runs one heaviest-case prediction (longest binder + your target, on Boltz) to measure peak memory — the same step the automatic mode does before a run.")
                    .font(.caption).foregroundStyle(.secondary)
                calibrationResults
            }

            Text("Design engine: Boltz · Post-prediction: IntelliFold (fixed for now)")
                .font(.caption).foregroundStyle(.secondary)
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
