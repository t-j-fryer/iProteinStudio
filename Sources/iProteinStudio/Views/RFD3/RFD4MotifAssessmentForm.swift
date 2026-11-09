import SwiftUI

struct RFD4MotifAssessmentForm: View {
    @Binding var request: RFD4Request
    @ObservedObject var installer: PipelineInstaller
    private var enabled: Binding<Bool> {
        Binding(get: { request.motif_assessment != nil }, set: { on in
            request.motif_assessment = on ? RFD4MotifAssessment() : nil
            if on { request.search = .native; request.assess_native = false; request.native_search = false; if request.target_msa.isEmpty { request.target_msa = (request.motif?.partner_chains ?? []).isEmpty ? "empty" : "auto" } }
        })
    }
    private func mode(_ key: WritableKeyPath<RFD4MotifAssessment, Bool>) -> Binding<Bool> {
        Binding(get: { request.motif_assessment?[keyPath: key] ?? false }, set: { on in
            request.motif_assessment?[keyPath: key] = on
            if key == \.holo && !on { request.motif_assessment?.placement_rmsd_max = nil }
        })
    }
    private func cutoff(_ key: WritableKeyPath<RFD4MotifAssessment, Double?>) -> Binding<Double> {
        Binding(get: { request.motif_assessment?[keyPath: key] ?? 2 }, set: { request.motif_assessment?[keyPath: key] = $0 })
    }
    var body: some View {
        Card(title: "Final structure prediction and motif hits", systemImage: "checkmark.seal") {
            VStack(alignment: .leading, spacing: 10) {
                Toggle("Predict generated scaffold sequences", isOn: enabled).disabled(request.motif == nil)
                if request.motif == nil { Text("Choose motif residues and atoms first so the prediction can be compared with the exact input selection.").font(.caption) }
                if let assessment = request.motif_assessment {
                    Toggle("Apo · scaffold alone", isOn: mode(\.apo))
                    Toggle("Holo · scaffold with retained partners", isOn: mode(\.holo))
                    Picker("Structure predictor", selection: $request.predictor) {
                        ForEach(RFD4Predictor.allCases.filter { !assessment.holo || (request.motif?.ligand_ids ?? []).isEmpty || $0 == .boltz || $0.family == "ESMFold2" }) { option in
                            Text(option.label + (installer.isUsable(option.component) ? "" : " · install in Engines")).tag(option.rawValue)
                        }
                    }
                    if assessment.holo && !(request.motif?.partner_chains ?? []).isEmpty && !["esmfold2-fast-mlx", "esmfold2-600-mlx"].contains(request.predictor) {
                        Picker("Partner sequence alignment", selection: $request.target_msa) {
                            Text("Automatic per partner chain").tag("auto")
                            Text("Single sequence").tag("empty")
                            if !["auto", "empty", ""].contains(request.target_msa) { Text("Saved A3M file").tag(request.target_msa) }
                        }
                    }
                    Toggle("Call hits using motif shape RMSD", isOn: Binding(get: { assessment.rmsd_max != nil }, set: { request.motif_assessment?.rmsd_max = $0 ? 2 : nil }))
                    if assessment.rmsd_max != nil {
                        StudioFormField("Maximum motif RMSD (Å)") { NumericTextField("RMSD cutoff", value: cutoff(\.rmsd_max)) }
                    }
                    if assessment.holo {
                        Toggle("Also require motif placement relative to partners", isOn: Binding(get: { assessment.placement_rmsd_max != nil }, set: { request.motif_assessment?.placement_rmsd_max = $0 ? 2 : nil }))
                        if assessment.placement_rmsd_max != nil {
                            StudioFormField("Maximum partner-aligned motif RMSD (Å)") { NumericTextField("Placement cutoff", value: cutoff(\.placement_rmsd_max)) }
                        }
                    }
                    Text("Shape RMSD fits the selected motif atoms to the input motif. Placement RMSD fits the retained partner Cα atoms and ligand heavy atoms, then measures the motif without fitting it again. At least three noncollinear fit atoms are needed. Atom names are matched exactly.").font(.caption)
                    Text("Each selected mode runs a separate prediction without scaffold templates. A hit must pass every requested cutoff in all selected modes; missing atoms or incomplete predictions cannot pass. The editable 2 Å starting value is not a validated success threshold. RMSD and confidence do not establish binding or function.").font(.caption).foregroundStyle(.secondary)
                }
            }.padding(8)
        }
    }
}
