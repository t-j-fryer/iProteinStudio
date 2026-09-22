import SwiftUI

struct LigandNessoOptionsView: View {
    @Binding var options: LigandNessoOptions
    let explanation: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Toggle("Experimental sequence screening before structural verification", isOn: $options.enabled)
                .toggleStyle(.checkbox)
            if options.enabled {
                Picker("Scoring engine", selection: $options.engine) {
                    Text("NESSO-1 (experimental)").tag("nesso")
                    Text("PSICHIC-XL (experimental)").tag("psichic")
                }
                Text(explanation).font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                LabeledContent("Maximum sequences to advance") {
                    EditableIntStepper(value: $options.topK, in: 1...100000,
                                       accessibilityLabel: "Screening shortlist size")
                }
                Picker("Fold shortlist with", selection: $options.predictor) {
                    ForEach(LigandNessoOptions.predictors) { predictor in
                        Text(predictor.label).tag(predictor)
                    }
                }
                if options.predictor == .intellifold {
                    Picker("IntelliFold checkpoint", selection: $options.intellifoldModel) {
                        ForEach(IntelliFoldModel.allCases) { Text($0.label).tag($0) }
                    }
                }
                if options.engine == "psichic" {
                    Text("Ranks 1 − nonbinder. Binding-like probability, affinity and class probabilities are saved. No structural-confidence proxy is available. Experimental: binding accuracy for designed proteins is unvalidated. Supports complete sequences up to 700 residues.").font(.caption).foregroundStyle(.secondary)
                } else {
                Text("Ranks P(bind) + (1 − pocket-cropped interface entropy). Invalid or near-zero placement entropy is excluded. Fewer valid candidates means a smaller shortlist. This experimental score is not ligand pLDDT or evidence of binding; structure confidence is reported separately. Verification folds use the ligand SMILES with no pocket restraint or template.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                }
                if let error = options.validationError {
                    Label(error, systemImage: "exclamationmark.circle").foregroundStyle(.orange)
                }
            }
        }
    }
}
