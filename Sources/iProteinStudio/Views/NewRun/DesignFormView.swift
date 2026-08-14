import SwiftUI

/// Guided design form. Adapts to the chosen design type (nanobody vs de-novo
/// mini-binder / peptide). Sensible defaults; advanced options tucked away.
struct DesignFormView: View {
    @EnvironmentObject var app: AppState
    let project: Project
    @ObservedObject var installer: PipelineInstaller
    @State private var showAdvanced = false
    @State private var setupExperience: SetupExperience = .quick
    @State private var showTargetPrep = false
    @StateObject private var ligandAtoms = BoltzLigandAtoms()
    @StateObject private var ligandIntelligence = LigandIntelligence()

    private var request: Binding<DesignRequest> {
        Binding(
            get: { app.selectedProject?.request ?? project.request },
            set: { nv in app.updateSelected { $0.request = nv } }
        )
    }

    private var type: DesignType { request.wrappedValue.designType }

    var body: some View {
        VStack(spacing: 0) {
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
                    .accessibilityLabel("Target type")

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

                if type.usesScaffold {
                    Card(title: "2 · Nanobody scaffold", systemImage: "cube") {
                        Text("Choose a validated VHH framework. CDR loops are redesigned; the framework stays fixed.")
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
                        HelixKillControl(value: request.helixKill)
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

                if setupExperience == .advanced {
                    Card(title: "4 · Prediction & checking", systemImage: "checkmark.seal") {
                        PredictorPicker(request: request, installer: installer)
                    }
                } else {
                    Card(title: "4 · Recommended models", systemImage: "checkmark.seal") {
                        Label(quickModelSummary, systemImage: "cpu")
                            .font(.callout)
                        Text("Switch to Advanced to change the designer, checking models, temperatures, or scheduling.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
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
                    request.wrappedValue.epitopeResidues = residues.map { "B\($0)" }.joined(separator: " ")
                },
                onClose: { showTargetPrep = false }
            )
        }
    }

    private var quickModelSummary: String {
        let r = request.wrappedValue
        let checks = r.postPredictors.isEmpty ? "no extra checker" : r.postPredictors.map(\.label).joined(separator: ", ")
        return "\(r.designer.label) designs; \(r.designPredictor.label) guides each cycle; \(checks)."
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(project.name).font(.largeTitle.bold())
            Text("Set up your design run, then press Start.").foregroundStyle(.secondary)
        }
    }

    private var startBar: some View {
        let anotherWorkflowIsRunning = app.rfd3.isRunning || app.prediction.isRunning
        return HStack(spacing: 12) {
            let r = request.wrappedValue
            if anotherWorkflowIsRunning {
                Label("Finish or stop the active \(app.rfd3.isRunning ? "RFdiffusion3" : "prediction") run before starting iterative design.",
                      systemImage: "hourglass")
                    .font(.callout).foregroundStyle(.secondary)
            } else if !r.isRunnable || r.ligandAtomsStale {
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
            .buttonStyle(.borderedProminent).controlSize(.large)
            .accessibilityLabel("Start iterative design run")
            .accessibilityIdentifier("start-iterative-run")
            .disabled(!r.isRunnable || r.ligandAtomsStale || anotherWorkflowIsRunning)
        }
        .padding(.top, 6)
    }

    private func missingReason(_ r: DesignRequest) -> String {
        if r.targetKind == .protein && r.targetSequence.isEmpty { return "Add a target sequence to continue." }
        if r.targetKind == .ligand && r.targetSmiles.trimmingCharacters(in: .whitespaces).isEmpty { return "Add a ligand SMILES to continue." }
        if r.designType == .nanobody && r.scaffoldSequence.isEmpty { return "Pick a nanobody scaffold." }
        if r.designType == .nanobody && r.cdrs.isEmpty { return "Select at least one CDR to design." }
        if r.ligandAtomsStale {
            return "Reload the ligand atoms — the saved names were generated for different settings."
        }
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
        .accessibilityLabel(placeholder)
        .accessibilityHint("Enter an amino-acid sequence using one-letter codes")
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
        .accessibilityLabel("Nanobody scaffold")
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
                    Text(String(format: "%.2f", request.mpnnTempCycle1))
                        .font(.callout.monospacedDigit()).frame(width: 44, alignment: .trailing)
                }
                GridRow {
                    Text("Later cycles").font(.callout)
                    Slider(value: $request.mpnnTempLater, in: 0.05...1.0, step: 0.05).frame(width: 200)
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
                        Text(String(format: "%.2f", request.lasermpnnSeqTemp))
                            .font(.callout.monospacedDigit()).frame(width: 44, alignment: .trailing)
                    }
                    GridRow {
                        Text("Binding site").font(.callout)
                        Slider(value: $request.lasermpnnFirstShellTemp, in: 0.1...2.0, step: 0.1).frame(width: 200)
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
        // The iterative pipeline cannot drive the JAX backend, so it is not
        // offered here even though it is a valid checker elsewhere.
        Predictor.iterativeChoices.filter { $0.runnerValue != request.designPredictor.runnerValue }
    }

    private var usesIntelliFold: Bool {
        ([request.designPredictor] + request.postPredictors).contains {
            $0 == .intellifold || $0 == .intellifoldJAX
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // --- Design predictor ---
            VStack(alignment: .leading, spacing: 8) {
                Text("Design engine").font(.headline)
                Text("Folds each design as it is optimised. Every extra second here is paid on every design of every cycle.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Picker("Design engine", selection: $request.designPredictor) {
                    ForEach(Predictor.designChoices) { p in
                        Text(p.label).tag(p)
                    }
                }
                .pickerStyle(.menu).labelsHidden()
                .onChange(of: request.designPredictor) { _, new in
                    // A predictor cannot meaningfully check its own designs.
                    request.postPredictors.removeAll { $0.runnerValue == new.runnerValue }
                }
                predictorNote(request.designPredictor, isDesign: true)
            }

            Divider()

            // --- Orthogonal checking ---
            VStack(alignment: .leading, spacing: 8) {
                Text("Check hits with").font(.headline)
                Text("Independently re-folds your best designs with a different model. This is the score to trust — the design engine's own confidence is self-scored, because the loop optimises against it.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                ForEach(checkChoices) { p in
                    Toggle(isOn: Binding(
                        get: { request.postPredictors.contains(p) },
                        set: { on in
                            if on { request.postPredictors.append(p) }
                            else { request.postPredictors.removeAll { $0 == p } }
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
                    .disabled(!installer.isUsable(p.component))
                    .help(p.caveat.isEmpty ? p.blurb : p.caveat)
                }

                if request.postPredictors.isEmpty {
                    Label("Without an independent check you only have the design engine's own opinion of its designs.",
                          systemImage: "exclamationmark.triangle.fill")
                        .font(.caption).foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    Toggle("Only check designs that pass the hit threshold", isOn: $request.postOnlyHits)
                        .toggleStyle(.checkbox).font(.callout)
                }

                if usesIntelliFold {
                    Picker("IntelliFold model", selection: Binding(
                        get: { request.intellifoldModel ?? .v2flash },
                        set: { request.intellifoldModel = $0 }
                    )) {
                        ForEach(IntelliFoldModel.allCases) { model in
                            Text(model.label).tag(model)
                        }
                    }
                    .pickerStyle(.menu)
                    Text("Applied to every selected IntelliFold engine. v2-flash is the smaller validated default; v2 is the full model.")
                        .font(.caption2).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Divider()
            estimate
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
            && (p == .intellifold || p == .intellifoldJAX) {
            Text("not benchmarked").font(.caption).foregroundStyle(.secondary)
        } else {
            let band = p.speed(in: request.speedMode)
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

    /// Deliberately labelled "at least": the estimate counts predictions only,
    /// not MSA generation or inverse folding.
    private var estimate: some View {
        let fullV2Selected = request.intellifoldModel == .v2 && usesIntelliFold
        if fullV2Selected {
            return AnyView(Label {
                Text("No time estimate: full IntelliFold v2 has not been benchmarked on this Mac yet.")
            } icon: {
                Image(systemName: "clock")
            }
            .font(.callout)
            .foregroundStyle(.secondary))
        }
        let seconds = request.estimatedSecondsLowerBound
        return AnyView(Label {
            Text("Rough estimate: at least \(formatted(seconds)) of compute on this Mac.")
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
            // --- Scheduling ---
            VStack(alignment: .leading, spacing: 6) {
                Text("Scheduling").font(.headline)
                Picker("", selection: $request.speedMode) {
                    ForEach(SpeedMode.allCases) { Text($0.label).tag($0) }
                }.pickerStyle(.segmented).labelsHidden().frame(width: 300)
                    .accessibilityLabel("Scheduling mode")
                Text(request.speedMode.blurb).font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                if request.speedMode.isExperimental {
                    Label("Not yet validated for ligand targets or steering potentials. If a run misbehaves, switch back to Standard.",
                          systemImage: "flask")
                        .font(.caption).foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Toggle("Reuse finished work if this run is restarted", isOn: $request.resumeIfPossible)
                    .toggleStyle(.checkbox).font(.callout)
                Text("Long campaigns get interrupted. With this on, completed cycles, sequences and checks are read back from disk instead of recomputed.")
                    .font(.caption2).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Divider()

            // --- Parallelisation ---
            VStack(alignment: .leading, spacing: 6) {
                Text("Parallelisation").font(.headline)
                Picker("", selection: $request.parallelMode) {
                    ForEach(ParallelMode.allCases) { Text($0.label).tag($0) }
                }.pickerStyle(.segmented).labelsHidden().frame(width: 300)
                    .accessibilityLabel("Memory and parallelism mode")
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

            Divider()
            DisclosureGroup("What settings will actually be used") {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(([request.designPredictor] + request.postPredictors)
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
                Text("Design engine: \(request.designPredictor.label) · Checked with: "
                     + (request.postPredictors.isEmpty
                        ? "nothing"
                        : request.postPredictors.map(\.label).joined(separator: ", ")))
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
