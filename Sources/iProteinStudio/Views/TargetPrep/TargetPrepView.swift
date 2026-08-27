import SwiftUI

/// Predict the target structure (IntelliFold or Boltz) and explore it.
/// Protein targets: hover residues, hydrophobicity surface, click epitope
/// hotspots. Ligand targets: 3D ball-and-stick view of the predicted conformer.
struct TargetPrepView: View {
    let targetKind: TargetKind
    let targetSequence: String
    let targetSmiles: String
    var onUse: ([String]) -> Void
    /// Called with the predicted structure once it exists. The RFdiffusion3 tab
    /// uses this to adopt the prediction as its design target, so a user with
    /// only a sequence never has to find the file themselves.
    var onStructure: ((String) -> Void)?
    var onClose: () -> Void

    @EnvironmentObject var predictions: PredictionStore
    @StateObject private var predictor = TargetPredictor()
    @State private var selected: [String] = []
    @State private var showSurface = false
    @State private var engine: TargetEngine
    @State private var model: IntelliFoldModel = .v2flash
    @State private var name: String = ""

    init(targetKind: TargetKind, targetSequence: String, targetSmiles: String,
         onUse: @escaping ([String]) -> Void,
         onStructure: ((String) -> Void)? = nil,
         onClose: @escaping () -> Void) {
        self.targetKind = targetKind
        self.targetSequence = targetSequence
        self.targetSmiles = targetSmiles
        self.onUse = onUse
        self.onStructure = onStructure
        self.onClose = onClose
        // Ligand-only prediction is verified with Boltz; protein defaults to IntelliFold.
        _engine = State(initialValue: targetKind == .ligand ? .boltz : .intellifold)
    }

    private var isLigand: Bool { targetKind == .ligand }

    /// A previously computed structure for the currently selected engine+model.
    private var cachedCIF: String? {
        predictor.cachedCIF(targetKind: targetKind, sequence: targetSequence,
                            smiles: targetSmiles, engine: engine, model: model)
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            content
            Divider()
            footer
        }
        .frame(width: 900, height: 700)
        .onChange(of: predictor.phase) { _, phase in
            if case .done(let cif) = phase {
                recordPrediction()
                onStructure?(cif)
            }
        }
    }

    private func recordPrediction() {
        let id = predictor.cacheKey(targetKind: targetKind, sequence: targetSequence,
                                    smiles: targetSmiles, engine: engine, model: model)
        let payload = targetKind == .protein
            ? (ProteinSequenceInput.canonical(targetSequence, startingAt: 1) ?? targetSequence)
                                             : targetSmiles.trimmingCharacters(in: .whitespaces)
        predictions.upsert(id: id, name: name, targetKind: targetKind, payload: payload,
                           engine: engine, model: model)
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(isLigand ? "Ligand Structure" : "Target Prep").font(.headline)
                Text(isLigand
                     ? "See what the structure predictors make of your molecule."
                     : "Find the best epitope: hover for residue numbers, show hydrophobic patches, click to mark hotspots.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Button("Close", action: onClose)
        }
        .padding()
    }

    @ViewBuilder private var content: some View {
        switch predictor.phase {
        case .idle:            setupPanel(error: nil)
        case .failed(let msg): setupPanel(error: msg)
        case .running:         runningPanel
        case .done(let cif):   resultPanel(cif: cif)
        }
    }

    private func setupPanel(error: String?) -> some View {
        VStack(spacing: 18) {
            Spacer()
            Image(systemName: isLigand ? "cube.transparent" : "scope").font(.system(size: 44)).foregroundStyle(.tint)
            Text(isLigand ? "Predict the ligand structure" : "Predict the target structure").font(.title3.bold())
            VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("Prediction engine").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    Picker("", selection: $engine) {
                        ForEach(TargetEngine.allCases) { Text($0.label).tag($0) }
                    }.pickerStyle(.segmented).labelsHidden().frame(maxWidth: .infinity)
                        .accessibilityLabel("Target prediction engine")
                }
                if engine == .intellifold {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("IntelliFold model").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                        Picker("", selection: $model) {
                            ForEach(IntelliFoldModel.allCases) { Text($0.label).tag($0) }
                        }.labelsHidden().frame(maxWidth: .infinity)
                            .accessibilityLabel("IntelliFold model")
                    }
                }
                if cachedCIF == nil {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("Prediction name (optional)").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                        TextField("Name this prediction (optional)", text: $name)
                            .textFieldStyle(.roundedBorder).frame(maxWidth: .infinity)
                    }
                }
            }
            .frame(width: 360)

            if cachedCIF != nil {
                // Already computed for this target + engine + model — offer retrieval.
                VStack(spacing: 8) {
                    Label("Already predicted with \(engine.label)\(engine == .intellifold ? " (\(model.rawValue))" : "")",
                          systemImage: "checkmark.seal.fill")
                        .font(.callout).foregroundStyle(.green)
                    Button { predict(force: false) } label: {
                        Label("Show existing structure", systemImage: "arrow.down.doc").frame(width: 240)
                    }
                    .buttonStyle(.borderedProminent).controlSize(.large)
                    Button { predict(force: true) } label: {
                        Label("Predict again", systemImage: "arrow.clockwise")
                    }
                    .controlSize(.small)
                }
            } else {
                Button { predict(force: false) } label: {
                    Label("Predict structure", systemImage: "play.fill").frame(width: 220)
                }
                .buttonStyle(.borderedProminent).controlSize(.large)
            }

            if let error {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.callout).foregroundStyle(.orange).multilineTextAlignment(.center).frame(maxWidth: 480)
            } else if cachedCIF == nil {
                Text(isLigand ? "Boltz is verified for ligand-only prediction; IntelliFold may also work."
                              : "Studio checks the shared MSA cache first and generates a real alignment only when it is missing. v2-flash is the fastest option.")
                    .font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
            }
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity).padding()
    }

    private var runningPanel: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Predicting with \(engine.label)\(engine == .intellifold ? " (\(model.rawValue))" : "")…").font(.callout)
            LogView(lines: predictor.log)
            Button("Cancel", role: .cancel) { predictor.cancel() }.controlSize(.small)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity).padding()
    }

    @ViewBuilder private func resultPanel(cif: String) -> some View {
        if isLigand {
            TargetStructureView(structurePath: cif, selected: $selected, showSurface: false, ligand: true)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            HStack(spacing: 0) {
                TargetStructureView(structurePath: cif, selected: $selected, showSurface: showSurface)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                sidebar
            }
        }
    }

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 14) {
            Toggle(isOn: $showSurface) {
                VStack(alignment: .leading, spacing: 1) {
                    Text("Hydrophobicity surface")
                    Text("Switches to the 3D surface view; orange = hydrophobic")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }.toggleStyle(.switch)
            Divider()
            HStack {
                Text("Hotspots").font(.headline)
                Spacer()
                if !selected.isEmpty { Button("Clear") { selected = [] }.controlSize(.small) }
            }
            Text("Click residues in the structure to add or remove them, or tap a chip below to remove it.")
                .font(.caption).foregroundStyle(.secondary)
            ScrollView {
                RemovableChips(residues: selected) { residue in
                    selected.removeAll { $0 == residue }
                }
            }
                .frame(maxHeight: .infinity)
            Divider()
            Button { predictor.cancel(); selected = []; showSurface = false } label: {
                Label("Re-predict…", systemImage: "arrow.clockwise")
            }.controlSize(.small)
        }
        .padding().frame(width: 250).background(.quaternary.opacity(0.25))
    }

    @ViewBuilder private var footer: some View {
        if isLigand {
            HStack {
                if case .done = predictor.phase {
                    Button { predictor.cancel() } label: { Label("Re-predict…", systemImage: "arrow.clockwise") }
                        .controlSize(.small)
                }
                Spacer()
                Button("Done", action: onClose).buttonStyle(.borderedProminent)
            }
            .padding()
        } else {
            HStack {
                Text(selected.isEmpty ? "No hotspots selected"
                     : "\(selected.count) hotspot\(selected.count == 1 ? "" : "s") selected")
                    .foregroundStyle(.secondary).font(.callout)
                Spacer()
                Button("Use hotspots") { onUse(selected); onClose() }
                    .buttonStyle(.borderedProminent).disabled(selected.isEmpty)
            }
            .padding()
        }
    }

    private func predict(force: Bool) {
        predictor.predict(targetKind: targetKind, sequence: targetSequence,
                          smiles: targetSmiles, engine: engine, model: model, force: force)
    }
}

/// Wrapping row of hotspot chips; tap a chip to remove that residue.
struct RemovableChips: View {
    let residues: [String]
    var onRemove: (String) -> Void
    var body: some View {
        let cols = [GridItem(.adaptive(minimum: 58), spacing: 6)]
        LazyVGrid(columns: cols, alignment: .leading, spacing: 6) {
            ForEach(residues, id: \.self) { residue in
                Button { onRemove(residue) } label: {
                    HStack(spacing: 3) {
                        Text(residue).font(.caption.monospacedDigit())
                        Image(systemName: "xmark.circle.fill").font(.system(size: 9))
                    }
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(Capsule().fill(.orange.opacity(0.2)))
                    .foregroundStyle(.orange)
                }
                .buttonStyle(.plain).help("Remove \(residue)")
            }
        }
    }
}
