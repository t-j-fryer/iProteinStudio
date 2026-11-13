import SwiftUI
import AppKit

struct ResultSpatialSummary: View {
    let row: ResultSpatialRow
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Label(row.passed ? "Spatial criteria passed" : "Spatial criteria failed", systemImage: row.passed ? "checkmark.circle" : "xmark.circle")
                Spacer()
                if let receipt = row.receipt {
                    Button("Reveal measurement") { NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: receipt)]) }.controlSize(.small)
                }
            }
            if let low = row.minimum_distance, let high = row.maximum_distance {
                Text(String(format: "Selected-site nearest-atom distances: %.2f–%.2f Å", low, high)).font(.caption)
            }
            if let sasa = row.sasa {
                Text(String(format: "Ligand burial %.1f%% · isolated %.1f Å² · bound %.1f Å²", sasa.buried_percent, sasa.isolated_sasa_a2, sasa.complex_sasa_a2)).font(.caption)
            }
            if let geometry = row.recorded_geometry {
                Text(geometry.passed ? "Recorded geometry: pass" : "Recorded geometry: fail").font(.caption)
            }
            if let warning = row.geometry_warning { Text(warning).font(.caption).foregroundStyle(.orange) }
            if let distances = row.distances, !distances.isEmpty {
                DisclosureGroup("Per-site distances (\(distances.count))") {
                    ScrollView {
                        LazyVStack(alignment: .leading) {
                            ForEach(distances.keys.sorted(), id: \.self) { site in
                                Text(String(format: "%@: %.2f Å", site, distances[site]!)).font(.caption.monospaced())
                            }
                        }
                    }.frame(maxHeight: 100)
                }.font(.caption)
            }
            Text("Pose: " + URL(fileURLWithPath: row.source).lastPathComponent).font(.caption2).foregroundStyle(.secondary)
        }.padding(10).frame(maxWidth: .infinity, alignment: .leading).background(.quaternary.opacity(0.12))
    }
}

struct ResultSpatialControls: View {
    @Binding var policy: ResultSpatialPolicy?
    let candidates: [ResultCandidate]
    @ObservedObject var controller: ResultSpatialController
    @State private var expanded = false

    private var value: Binding<ResultSpatialPolicy> {
        Binding(get: { policy ?? ResultSpatialPolicy() }, set: { policy = $0 })
    }
    var body: some View {
        DisclosureGroup("Epitope, ligand contacts & burial", isExpanded: $expanded) {
            VStack(alignment: .leading, spacing: 8) {
                Toggle("Require spatial criteria to pass", isOn: Binding(get: { policy != nil }, set: { policy = $0 ? ResultSpatialPolicy() : nil }))
                if policy != nil {
                    HStack {
                        Picker("Target", selection: value.mode) {
                            Text("Protein residues").tag(ResultSpatialPolicy.Mode.protein)
                            Text("Small-molecule atoms").tag(ResultSpatialPolicy.Mode.ligand)
                        }.frame(width: 220)
                        TextField("Binder/protein chains", text: value.binderChains).frame(width: 150)
                        TextField("Target/ligand chain", text: value.targetChain).frame(width: 150)
                    }
                    HStack {
                        if value.wrappedValue.mode == .protein {
                            TextField("Target residue IDs, e.g.40,99,107A", text: value.residues)
                        } else {
                            TextField("Ligand residue ID (blank if unique)", text: value.ligandResidue).frame(width: 235)
                            TextField("Exact atom names; blank = all heavy atoms", text: value.atoms)
                        }
                        Picker("Contact", selection: value.coverage) {
                            Text("Every selected site").tag(ResultSpatialPolicy.Coverage.all)
                            Text("Any selected site").tag(ResultSpatialPolicy.Coverage.any)
                        }.frame(width: 200)
                        Text("within")
                        TextField("Å", text: value.cutoff).frame(width: 55)
                        Text("Å")
                    }
                    if value.wrappedValue.mode == .ligand {
                        HStack {
                            Toggle("Require recorded geometry pass", isOn: value.requireGeometry)
                            Text("Full-complex ligand burial (%)")
                            TextField("Min (optional)", text: value.minimumBurial).frame(width: 105)
                            TextField("Max (optional)", text: value.maximumBurial).frame(width: 105)
                        }
                        Text("Burial =100 × (1 − bound/isolated ligand SASA), using all nonwater atoms in the full complex, the existing heavy-atom FreeSASA protocol and the same conformation. Recorded geometry is a separate, verified verdict for this exact pose; missing receipts fail when required.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Text("Use author IDs/names from the exact predicted structure. No SMILES atom indices or numbering from a different PDB are substituted. Missing sites fail. Every candidate must satisfy these criteria before sorting and family limits.")
                        .font(.caption).foregroundStyle(.secondary)
                    HStack {
                        Button("Inspect exact pose IDs") {
                            if let source = candidates.first?.analysisSource { controller.inspect(source.structureURL) }
                        }.disabled(controller.busy || candidates.isEmpty)
                        Button("Analyze \(candidates.count) candidates") { controller.run(candidates: candidates, policy: value.wrappedValue) }
                            .disabled(controller.busy || candidates.isEmpty || value.wrappedValue.validationMessage != nil)
                        if controller.busy { ProgressView().controlSize(.small); Button("Cancel analysis") { controller.cancel() } }
                        Spacer()
                    }
                    Text("CPU only · explicit analysis · completed units resume from cache. Current settings must be analyzed before candidates can match.").font(.caption).foregroundStyle(.secondary)
                    if let message = value.wrappedValue.validationMessage { Text(message).font(.caption).foregroundStyle(.orange) }
                    if let message = controller.message { Text(message).font(.caption).textSelection(.enabled) }
                    ForEach(controller.failures, id: \.self) { Text($0).font(.caption).foregroundStyle(.orange).textSelection(.enabled) }
                    if !controller.samples.isEmpty {
                        DisclosureGroup("Last analysis preview (first \(controller.samples.count) assessed candidates)") {
                            ScrollView {
                                LazyVStack(alignment: .leading, spacing: 5) {
                                    ForEach(controller.samples, id: \.id) { row in
                                        VStack(alignment: .leading) {
                                            Text((row.passed ? "Spatial pass · " : "Spatial fail · ") + URL(fileURLWithPath: row.source).lastPathComponent).lineLimit(1)
                                            if let error = row.error { Text(error).foregroundStyle(.orange) }
                                            else if let low = row.minimum_distance, let high = row.maximum_distance {
                                                Text(String(format: "Nearest site distances %.2f–%.2f Å", low, high))
                                            }
                                            if let sasa = row.sasa { Text(String(format: "Ligand burial %.1f%%", sasa.buried_percent)) }
                                        }.font(.caption).textSelection(.enabled)
                                    }
                                }
                            }.frame(maxHeight: 140)
                        }.font(.caption)
                    }
                    if let inventory = controller.inventory {
                        ScrollView { Text(inventory).font(.caption.monospaced()).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }.frame(maxHeight: 140)
                    }
                }
            }.textFieldStyle(.roundedBorder).padding(.top, 8)
        }.font(.callout)
        .onChange(of: policy != nil, initial: true) { _, enabled in if enabled { expanded = true } }
        .onChange(of: value.wrappedValue.mode) { _, mode in
            if policy != nil && mode == .protein {
                value.wrappedValue.requireGeometry = false
                value.wrappedValue.minimumBurial = ""; value.wrappedValue.maximumBurial = ""
            }
        }
    }
}
