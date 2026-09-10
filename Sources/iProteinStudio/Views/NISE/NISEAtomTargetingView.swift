import SwiftUI

/// Labels belong to Boltz affinity's explicit chemical state, also passed to
/// NESSO and RFdiffusion3. Never reinterpret original-SMILES indices as names.
struct NISEAtomTargetingView: View {
    @Binding var request: NISERequest
    @ObservedObject var atoms: BoltzLigandAtoms
    @Binding var verified: Bool
    @State private var depictionError: String?

    private var key: String { request.smiles.trimmingCharacters(in: .whitespacesAndNewlines) + "|1|nise" }
    private var ready: Bool { atoms.generatedFor == key && atoms.hasAtoms && !atoms.signature.isEmpty }
    private var hotspotIndices: [Int] {
        atoms.namesByInputIndex.indices.filter { request.hotspot_atoms.contains(atoms.namesByInputIndex[$0]) }
    }
    private var exposedIndices: [Int] {
        atoms.namesByInputIndex.indices.filter { request.exposed_atoms.contains(atoms.namesByInputIndex[$0]) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Binding hotspots and linker exposure (optional)").font(.headline)
            Text("All stages use Boltz affinity’s chemical state of the molecule. Load it to review that state and choose atoms to contact or keep solvent-accessible. Every selected atom is checked before sequences advance.")
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                Button(ready ? "Reload molecule" : "Load molecule and atom labels") {
                    verified = false; depictionError = nil
                    atoms.resolve(smiles: request.smiles, affinityHead: true, nise: true)
                }
                .disabled(atoms.isResolving || request.smiles.isEmpty)
                if atoms.isResolving { ProgressView().controlSize(.small) }
                if request.hasAtomSelections {
                    Button("Clear atom choices") { request.clearAtomSelections() }
                }
            }
            if let error = atoms.error ?? depictionError {
                Label(error, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange).font(.caption)
            }
            if ready {
                Text("The diagram shows the chemical state used by Boltz affinity. The same SMILES goes to RFdiffusion3 and NESSO. Labels are Boltz atom names, not atom numbers to enter into NESSO.")
                    .font(.caption).foregroundStyle(.secondary)
                if atoms.chemicalStateChanged {
                    Label("Boltz changes the input molecule's chemical state (for example protonation). Review the molecule below before selecting atoms.", systemImage: "info.circle")
                        .font(.caption).foregroundStyle(.orange)
                }
                LigandAtomPicker(smiles: atoms.displaySmiles,
                                 attachmentAtom: .constant(nil), attachmentLinkerAtom: .constant(nil),
                                 coreAtoms: hotspotIndices, presentationAtoms: exposedIndices,
                                 atomLabels: atoms.namesByInputIndex, allowsAttachmentPicking: false,
                                 onAtomsResolved: { symbols in
                    let matches = symbols.map { $0.uppercased() } == atoms.atoms.map { $0.element.uppercased() }
                    depictionError = matches ? nil : "Diagram atom order could not be verified. Reload the molecule; atom selection is blocked."
                    verified = matches && ready
                })
                .id(atoms.signature)
                .frame(height: 260)
                .background(RoundedRectangle(cornerRadius: 8).fill(.white))
                Text("Choose below: Bind highlights a hotspot in green; Expose highlights a solvent-accessible atom in orange. None clears its requirement.")
                    .font(.caption)
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 185))], spacing: 8) {
                    ForEach(atoms.atoms) { atom in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(atom.name).font(.caption.monospaced().bold())
                            Picker("Requirement for \(atom.name)", selection: Binding(
                                get: { request.hotspot_atoms.contains(atom.name) ? "bind" : request.exposed_atoms.contains(atom.name) ? "expose" : "none" },
                                set: { choice in
                                    // SwiftUI can retain the binding's value for
                                    // this event. Separate writes overwrite one
                                    // another; commit the choice and map together.
                                    var updated = request
                                    updated.hotspot_atoms.removeAll { $0 == atom.name }
                                    updated.exposed_atoms.removeAll { $0 == atom.name }
                                    if choice == "bind" { updated.hotspot_atoms.append(atom.name) }
                                    if choice == "expose" { updated.exposed_atoms.append(atom.name) }
                                    updated.ligand_atom_signature = atoms.signature
                                    updated.ligand_atoms_generated_for = updated.smiles.trimmingCharacters(in: .whitespacesAndNewlines)
                                    request = updated
                                })) {
                                    Text("None").tag("none")
                                    Text("Bind").tag("bind")
                                    Text("Expose").tag("expose")
                                }.pickerStyle(.segmented).labelsHidden()
                                .accessibilityLabel("Requirement for ligand atom \(atom.name)")
                        }.padding(6)
                    }
                }.disabled(!verified || (request.hasAtomSelections && request.ligand_atom_signature != atoms.signature))
                if request.hasAtomSelections && request.ligand_atom_signature != atoms.signature {
                    Label("The saved labels belong to a different atom map. Clear the choices and select them again.", systemImage: "exclamationmark.triangle.fill")
                        .font(.caption).foregroundStyle(.orange)
                }
                DisclosureGroup("SMILES used by the engines") {
                    Text(atoms.displaySmiles).font(.caption.monospaced()).textSelection(.enabled)
                }
            }
            if !request.hotspot_atoms.isEmpty {
                HStack {
                    Text("Maximum hotspot contact distance")
                    Slider(value: $request.hotspot_distance, in: 3...10, step: 0.5)
                    Text(String(format: "%.1f Å", request.hotspot_distance)).monospacedDigit()
                }.font(.caption)
            }
            if !request.exposed_atoms.isEmpty {
                HStack {
                    Text("Minimum accessibility retained per exposed atom")
                    Slider(value: $request.exposure_min_fraction, in: 0.1...1, step: 0.05)
                    Text(request.exposure_min_fraction, format: .percent.precision(.fractionLength(0))).monospacedDigit()
                }.font(.caption)
                Text("50% means each selected atom keeps at least half of its solvent-accessible area compared with the same ligand conformation without protein. This is a predicted-geometry filter, not experimental confirmation of linker accessibility.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Text("RFdiffusion3 also receives hotspot and exposure conditioning. Protein Hunter uses hotspots during initial pocket formation; Boltz has no exposure restraint. All later selection remains unrestrained and checks the requested contacts/exposure. Without explicit hotspots, automatic contacts exclude exposed atoms.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .onChange(of: request.smiles) { _, _ in
            request.clearAtomSelections(); atoms.reset(); verified = false; depictionError = nil
        }
    }
}
