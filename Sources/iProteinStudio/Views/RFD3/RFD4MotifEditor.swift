import SwiftUI

struct RFD4MotifEditor: View {
    let source: String
    let apply: (RFD4Motif) -> Void
    @Environment(\.dismiss) private var dismiss
    @StateObject private var inspector = RFD4MotifInspector()
    @StateObject private var numericValidation = NumericInputValidation()
    @State private var motif: RFD4Motif
    @State private var filter = ""
    @State private var sourceChanged = false
    private var missingSelections: Bool {
        guard let inventory = inspector.inventory else { return false }
        return motif.residues.contains { selected in
            !inventory.residues.contains { $0.id == selected.id && Set(selected.atoms).isSubset(of: Set($0.atoms)) }
        }
    }

    init(source: String, initial: RFD4Motif?, apply: @escaping (RFD4Motif) -> Void) {
        self.source = source; self.apply = apply; _motif = State(initialValue: initial ?? RFD4Motif())
    }
    private var selected: Binding<[String]> {
        Binding(get: { motif.residues.map(\.id) }, set: { ids in
            guard let inventory = inspector.inventory else { return }
            motif.residues = inventory.residues.filter { ids.contains($0.id) }.map { residue in
                motif.residues.first { $0.id == residue.id } ?? RFD4MotifResidue(chain: residue.chain, residue: residue.residue, atoms: residue.atoms.filter { ["N", "CA", "C", "O"].contains($0) })
            }
        })
    }
    var body: some View {
        ScrollView {
        VStack(alignment: .leading, spacing: 12) {
            Text("Choose the motif to scaffold").font(.title2)
            Text("Select residues on the structure or in the list, then choose the atoms to condition. Amber spheres mark the chosen atoms. RFD4 conditions generation on this geometry; inspect the generated motif because coordinates are not guaranteed to match exactly.").font(.callout)
            if inspector.running { ProgressView("Reading native residue and atom identities…") }
            if let error = inspector.error { Text(error).foregroundStyle(.red).textSelection(.enabled) }
            if sourceChanged { Text("The source file changed. Choose the motif again on the current structure.").foregroundStyle(.orange) }
            if missingSelections { Text("Some saved residues or atoms are absent. Clear them and select from this structure.").foregroundStyle(.orange) }
            if let inventory = inspector.inventory {
                HStack(alignment: .top) {
                    TargetStructureView(structurePath: inventory.preview, selected: selected, showSurface: false, selectedAtoms: Dictionary(motif.residues.map { ($0.id, $0.atoms) }, uniquingKeysWith: { _, last in last })).frame(minWidth: 460, minHeight: 350)
                    VStack(alignment: .leading) {
                        TextField("Find chain, residue number or name", text: $filter)
                        ScrollView {
                            LazyVStack(alignment: .leading, spacing: 8) {
                                ForEach(inventory.residues.filter { filter.isEmpty || ($0.id + " " + $0.name).localizedCaseInsensitiveContains(filter) }) { residue in
                                    Toggle(residue.id + " · " + residue.name, isOn: Binding(get: { selected.wrappedValue.contains(residue.id) }, set: { on in
                                        selected.wrappedValue = on ? selected.wrappedValue + [residue.id] : selected.wrappedValue.filter { $0 != residue.id }
                                    }))
                                    if let index = motif.residues.firstIndex(where: { $0.id == residue.id }) {
                                        DisclosureGroup("Coordinate atoms: " + motif.residues[index].atoms.joined(separator: ", ")) {
                                            HStack {
                                                Button("Backbone") { motif.residues[index].atoms = residue.atoms.filter { ["N", "CA", "C", "O"].contains($0) } }
                                                Button("All atoms") { motif.residues[index].atoms = residue.atoms }
                                            }
                                            LazyVGrid(columns: [GridItem(.adaptive(minimum: 70))], alignment: .leading) {
                                                ForEach(residue.atoms, id: \.self) { atom in
                                                    Toggle(atom, isOn: Binding(get: { motif.residues[index].atoms.contains(atom) }, set: { on in
                                                        motif.residues[index].atoms.removeAll { $0 == atom }
                                                        if on { motif.residues[index].atoms.append(atom) }
                                                    })).toggleStyle(.checkbox)
                                                }
                                            }
                                        }.padding(.leading, 16)
                                    }
                                }
                            }
                        }.frame(height: 315)
                    }.frame(width: 345)
                }
                HStack {
                    Text("\(motif.residues.count) residues · \(motif.residues.reduce(0) { $0 + $1.atoms.count }) coordinate atoms")
                    Button("Clear all") { motif.residues = [] }
                }
                DisclosureGroup("Retain binding partners from this complex") {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Choose the partner side of a protein interface, bound small molecules, or both. They stay in the source motif’s coordinate frame during generation. The motif-bearing chain becomes the new scaffold; unselected source chains are omitted.").font(.caption)
                        ForEach(inventory.chains) { chain in
                            Toggle("Protein chain \(chain.chain) · \(chain.sequence.count) residues", isOn: Binding(get: { (motif.partner_chains ?? []).contains(chain.chain) }, set: { on in
                                var chains = motif.partner_chains ?? []; chains.removeAll { $0 == chain.chain }; if on { chains.append(chain.chain) }; motif.partner_chains = chains
                            })).disabled(motif.residues.contains { $0.chain == chain.chain })
                        }
                        ForEach(inventory.ligands) { ligand in
                            Toggle("Ligand \(ligand.id)", isOn: Binding(get: { (motif.ligand_ids ?? []).contains(ligand.id) }, set: { on in
                                var ids = motif.ligand_ids ?? []; ids.removeAll { $0 == ligand.id }; if on { ids.append(ligand.id) }; motif.ligand_ids = ids
                            }))
                        }
                        Button("Clear retained partners") { motif.partner_chains = nil; motif.ligand_ids = nil }
                        Text("A separate sequence has no binding pose. Use Predict from sequence with both chains to prepare a proposed complex first, then select the motif and partner here. Covalently attached ligands and nucleic acids require a separate workflow.").font(.caption).foregroundStyle(.secondary)
                    }
                }
                Divider()
                HStack(alignment: .top, spacing: 28) {
                    VStack(alignment: .leading, spacing: 8) {
                        Picker("Motif geometry", selection: $motif.coordinate_mode) {
                            Text("Absolute-coordinate conditioning").tag("absolute")
                            Text("Relative-coordinate conditioning (one group)").tag("relative")
                        }
                        Toggle("Keep motif residue identities", isOn: $motif.fix_sequence)
                        Text("Backbone-only coordinates can allow sequence redesign. Selected sidechain atoms require the residue identity to stay fixed.").font(.caption).foregroundStyle(.secondary)
                        Toggle("Let RFD4 place motif residues along the scaffold", isOn: $motif.unindexed)
                        if motif.unindexed { Toggle("Keep relative spacing within each contiguous motif segment", isOn: $motif.group_segments) }
                        Text(motif.unindexed ? "Unindexed residues can move in sequence. Geometry remains conditioned; groups retain offsets within each selected segment." : "Indexed residues follow the order and generated segment lengths below.").font(.caption).foregroundStyle(.secondary)
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        Text("New scaffold residues · minimum / maximum").font(.headline)
                        bounds("Before motif", values: $motif.prefix)
                        bounds("Between separated motif segments", values: $motif.linker)
                        bounds("After motif", values: $motif.suffix)
                        Text(motif.unindexed ? "Free placement: motif residues occupy generated positions. Final length is the sum of these segments; their labels do not fix motif locations. Use 0 / 0 to omit a segment." : "Indexed placement: final length adds the selected motif residues to these segments. Equal bounds fix the length; 0 / 0 omits a segment.").font(.caption).foregroundStyle(.secondary)
                    }.frame(width: 360)
                }
            }
            ForEach(motif.issues, id: \.self) { Text($0).font(.caption).foregroundStyle(.orange) }
            HStack {
                Button("Cancel") { dismiss() }
                Spacer()
                Button("Use this motif") { motif.source_sha256 = inspector.inventory?.source_sha256; apply(motif); dismiss() }.buttonStyle(.borderedProminent)
                    .disabled(inspector.inventory == nil || inspector.running || missingSelections || !motif.issues.isEmpty || !numericValidation.invalidEditors.isEmpty)
            }
        }.padding(20)
        }.frame(width: 900, height: 780)
            .environment(\.numericInputValidation, numericValidation)
            .task(id: source) { inspector.inspect(source: source) }
            .onChange(of: inspector.inventory?.source_sha256) { _, fingerprint in
                if let fingerprint, let saved = motif.source_sha256, fingerprint != saved {
                    motif.residues = []; motif.partner_chains = nil; motif.ligand_ids = nil; sourceChanged = true
                }
            }
            .onDisappear { inspector.cancel() }
    }
    private func bounds(_ label: String, values: Binding<[Int]>) -> some View {
        HStack {
            Text(label).frame(maxWidth: .infinity, alignment: .leading)
            if values.wrappedValue.count == 2 {
                EditableIntStepper(value: values[0], in: 0...2000, accessibilityLabel: label + " minimum", showsStepper: false).frame(width: 65)
                Text("/")
                EditableIntStepper(value: values[1], in: 0...2000, accessibilityLabel: label + " maximum", showsStepper: false).frame(width: 65)
            } else { Text("Invalid saved bounds").foregroundStyle(.red) }
        }
    }
}
