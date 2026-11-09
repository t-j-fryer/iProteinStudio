import SwiftUI

struct LigandGeometryFilterForm: View {
    @Binding var policy: LigandGeometryFilter?
    let smiles: String
    var coreAtom: Int?
    var linkerAtom: Int?
    @StateObject private var preview = LigandPreview()
    private var identity: String { "\(smiles)|\(coreAtom ?? -1)|\(linkerAtom ?? -1)|\(policy != nil)" }
    private var value: LigandGeometryFilter { policy ?? LigandGeometryFilter() }

    var body: some View {
        DisclosureGroup("Ligand geometry hit filter") {
            VStack(alignment: .leading, spacing: 10) {
                Toggle("Require ligand geometry to pass", isOn: Binding(get: { policy != nil }, set: { policy = $0 ? LigandGeometryFilter() : nil }))
                Text("Every enabled geometry requirement must pass in the saved holo structure. Generation atom conditions and model confidence are separate settings. Missing or mismatched atoms cannot pass.")
                    .font(.caption).foregroundStyle(.secondary)
                if policy != nil {
                    Text("Boltz affinity can standardize the molecule’s chemical state. Geometry selections follow verified atom identities through Boltz’s own standardizer. Changed connectivity, lost stereochemistry or ambiguous selected atoms are blocked.")
                        .font(.caption).foregroundStyle(.secondary)
                    if let preset = preview.figure4Preset {
                        Button("Use Figure 4 biotin geometry") { policy = preset }
                        Text("Requires all nine binding-core atoms within 6 Å of the binder and an open or restricted biotin amide exit. Blocked and unresolved exits fail. The exit check replaces terminal acid-oxygen SASA.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Picker("Linker accessibility method", selection: Binding(get: { value.mode }, set: { policy?.mode = $0 })) {
                        Text("Selected atom accessibility (SASA)").tag("sasa")
                        if preview.figure4Preset != nil || value.mode == "biotin-carboxamide-v1" { Text("Figure 4 · free-biotin amide exit").tag("biotin-carboxamide-v1") }
                    }
                    if !preview.splitCore.isEmpty {
                        Button("Use selected binding core and linker") {
                            policy?.contact_atoms = preview.splitCore
                            policy?.exposed_atoms = preview.splitLinker
                        }
                    }
                    HStack {
                        Text("Maximum contact distance (Å)")
                        NumericTextField("Å", value: Binding(get: { value.contact_distance }, set: { policy?.contact_distance = $0 })).frame(width: 70)
                        Text("Minimum accessibility retained")
                        NumericTextField("Fraction", value: Binding(get: { value.exposure_min_fraction }, set: { policy?.exposure_min_fraction = $0 })).frame(width: 70)
                    }.font(.caption)
                    Text("Accessibility is each atom’s bound SASA divided by its isolated-ligand SASA in the same conformation. 0.5 requires at least half to remain accessible.").font(.caption).foregroundStyle(.secondary)
                    if preview.busy { ProgressView("Loading atom choices…") }
                    if let error = preview.error { Text(error).font(.caption).foregroundStyle(.orange) }
                    if !preview.atomElements.isEmpty {
                        DisclosureGroup("Contact and exposed atoms · input SMILES indices") {
                            LazyVGrid(columns: [GridItem(.adaptive(minimum: 190))], alignment: .leading) {
                                ForEach(preview.atomElements.indices, id: \.self) { i in
                                    HStack {
                                        Text("\(i) · \(preview.atomElements[i])").monospaced()
                                        Picker("Requirement for atom \(i)", selection: Binding(get: { value.contact_atoms.contains(i) ? "contact" : value.exposed_atoms.contains(i) ? "expose" : "none" }, set: { selected in
                                            policy?.contact_atoms.removeAll { $0 == i }; policy?.exposed_atoms.removeAll { $0 == i }
                                            if selected == "contact" { policy?.contact_atoms.append(i) }
                                            if selected == "expose" { policy?.exposed_atoms.append(i) }
                                        })) { Text("None").tag("none"); Text("Contact").tag("contact"); Text("Expose").tag("expose") }.labelsHidden()
                                    }
                                }
                            }
                        }
                    }
                    if let payload = preview.payload {
                        DisclosureGroup("Preview geometry requirements in 3D") {
                            LigandSpatialViewer(payload: payload, labels: preview.atomElements.indices.map(String.init),
                                conditions: Dictionary(uniqueKeysWithValues: preview.atomElements.indices.compactMap { i in
                                    let role = value.contact_atoms.contains(i) ? "hotspot" : value.exposed_atoms.contains(i) ? "exposed" : nil
                                    return role.map { (String(i), [$0]) }
                                })).frame(height: 270)
                        }
                    }
                    Button("Clear all geometry atom requirements") { policy?.contact_atoms = []; policy?.exposed_atoms = [] }
                    ForEach(value.validationIssues, id: \.self) { Text($0).font(.caption).foregroundStyle(.orange) }
                }
            }.padding(.top, 6)
        }.task(id: identity) { if policy != nil { preview.load(smiles: smiles, core: coreAtom, linker: linkerAtom) } }
         .onChange(of: smiles) { old, new in if old != new { policy = nil } }
    }
}
