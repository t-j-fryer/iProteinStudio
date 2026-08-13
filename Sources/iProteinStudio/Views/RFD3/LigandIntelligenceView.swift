import SwiftUI

/// Shows what the molecule actually looks like, and how the design budget should
/// be split across its shapes.
///
/// The failure this prevents is invisible without it. Design a pocket around one
/// arbitrary conformer of a floppy ligand and the campaign completes, the iPTMs
/// look fine, and the binder was built for a geometry the molecule may seldom
/// adopt. Nothing downstream catches that, so it has to be caught here.
struct LigandIntelligenceView: View {
    @ObservedObject var intelligence: LigandIntelligence
    @Binding var request: RFD3Request
    let outputDir: URL

    @State private var isConjugated = false
    @State private var atomSymbols: [String] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            controls
            if intelligence.isRunning {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Looking at the molecule and searching the PDB…")
                        .font(.callout).foregroundStyle(.secondary)
                }
            }
            if let error = intelligence.error {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.callout).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let analysis = intelligence.analysis {
                results(analysis)
            }
        }
        .onChange(of: intelligence.selected) { _, _ in syncPlan() }
        .onAppear { isConjugated = request.attachmentAtom != nil }
    }

    // MARK: Controls

    private var controls: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Before designing, Studio can work out which shapes this molecule actually adopts and split the design budget across them.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            Toggle("Look for experimental structures of this molecule in the PDB", isOn: $request.searchPDB)
                .toggleStyle(.checkbox).font(.callout)
            Text("A shape seen in a dozen unrelated crystal structures is far better evidence than any force field. Needs an internet connection.")
                .font(.caption2).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            Divider().padding(.vertical, 2)
            attachmentPicker
            HStack {
                Button {
                    intelligence.analyse(smiles: request.smiles,
                                         attachmentAtom: request.attachmentAtom,
                                         attachmentSymbol: pickedSymbol,
                                         searchPDB: request.searchPDB,
                                         outputDir: outputDir)
                } label: {
                    Label(intelligence.hasResult ? "Analyse again" : "Analyse this molecule",
                          systemImage: "sparkles.rectangle.stack")
                }
                .disabled(intelligence.isRunning ||
                          request.smiles.trimmingCharacters(in: .whitespaces).isEmpty)
                if intelligence.isRunning {
                    Button("Cancel") { intelligence.cancel() }.controlSize(.small)
                }
            }
        }
    }

    // MARK: Attachment point

    /// Clicking the atom is the whole point: a typed index gives the user no way
    /// to notice they picked the wrong one, and picking the wrong one quietly
    /// ruins the analysis by counting a linker as recognition core.
    private var attachmentPicker: some View {
        VStack(alignment: .leading, spacing: 8) {
            Toggle("This molecule is attached to something (a protein, a surface, a bead)",
                   isOn: Binding(
                    get: { isConjugated },
                    set: { on in
                        isConjugated = on
                        if !on { request.attachmentAtom = nil }
                    }))
                .toggleStyle(.checkbox).font(.callout)

            if isConjugated {
                Text(request.attachmentAtom == nil
                     ? "Click the atom where the linker leaves the molecule."
                     : "Linker leaves from atom \(request.attachmentAtom!)\(symbolSuffix). Click it again to clear.")
                    .font(.caption)
                    .foregroundStyle(request.attachmentAtom == nil ? .orange : .secondary)
                    .fixedSize(horizontal: false, vertical: true)

                LigandAtomPicker(
                    smiles: request.smiles,
                    attachmentAtom: $request.attachmentAtom,
                    coreAtoms: intelligence.analysis?.core.coreAtoms ?? [],
                    presentationAtoms: intelligence.analysis?.core.presentationAtoms ?? [],
                    onAtomsResolved: { symbols in atomSymbols = symbols }
                )
                .frame(height: 260)
                .background(RoundedRectangle(cornerRadius: 8).fill(.white))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))

                if intelligence.analysis?.core.presentationAtoms.isEmpty == false {
                    HStack(spacing: 14) {
                        legendDot(.green.opacity(0.5), "binding core")
                        legendDot(.orange.opacity(0.6), "linker — ignored when judging shape")
                    }
                    .font(.caption2).foregroundStyle(.secondary)
                }
            }
        }
    }

    private func legendDot(_ colour: Color, _ label: String) -> some View {
        HStack(spacing: 5) {
            Circle().fill(colour).frame(width: 9, height: 9)
            Text(label)
        }
    }

    /// Shown next to the chosen index so an atom-numbering mismatch between the
    /// depiction and the analysis would be visible rather than silent.
    /// Element of the clicked atom, as the depiction understands it.
    private var pickedSymbol: String? {
        guard let index = request.attachmentAtom,
              atomSymbols.indices.contains(index) else { return nil }
        return atomSymbols[index]
    }

    private var symbolSuffix: String {
        guard let index = request.attachmentAtom,
              atomSymbols.indices.contains(index) else { return "" }
        return " (\(atomSymbols[index]))"
    }

    // MARK: Results

    @ViewBuilder private func results(_ analysis: LigandAnalysis) -> some View {
        Divider()
        HStack(spacing: 10) {
            Circle().fill(flexibilityColour(analysis.flexibility.level)).frame(width: 12, height: 12)
            Text(analysis.headline).font(.headline)
            Spacer()
            Text(analysis.forceField).font(.caption2).foregroundStyle(.tertiary)
        }
        Text(analysis.flexibility.rationale)
            .font(.callout).foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)

        evidence(analysis)

        if !analysis.qa.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                ForEach(analysis.qa) { note in
                    Label {
                        VStack(alignment: .leading, spacing: 1) {
                            Text(note.title).font(.caption.weight(.medium))
                            Text(note.detail).font(.caption2).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    } icon: {
                        Image(systemName: note.isWarning ? "exclamationmark.triangle.fill" : "info.circle")
                            .foregroundStyle(note.isWarning ? .orange : .secondary)
                    }
                }
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 8).fill(.quaternary.opacity(0.3)))
        }

        statesTable(analysis)
        allocationSummary()
    }

    private func evidence(_ analysis: LigandAnalysis) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            let core = analysis.core
            if !core.presentationAtoms.isEmpty {
                Label("\(core.coreAtoms.count) atoms treated as the binding core; \(core.presentationAtoms.count) as linker. "
                      + "\(core.coreRotatableBonds) of \(core.totalRotatableBonds) rotatable bonds actually matter.",
                      systemImage: "scissors")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if analysis.pdb.searched {
                if analysis.pdb.nInstancesMatched > 0 {
                    Label("\(analysis.pdb.nInstancesMatched) experimental structures of this molecule were found and matched to the shapes below.",
                          systemImage: "checkmark.seal.fill")
                        .font(.caption).foregroundStyle(.green)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    Label(analysis.pdb.note.isEmpty
                          ? "No experimental structures matched. The recommendation is computational only."
                          : analysis.pdb.note,
                          systemImage: "questionmark.circle")
                        .font(.caption).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Text("\(analysis.ensemble.keptAfterStrainFilter) of \(analysis.ensemble.requested) generated conformers survived the strain filter, grouping into \(analysis.ensemble.clusters) shapes at \(String(format: "%.2f", analysis.ensemble.clusterRMSDUsed)) Å.")
                .font(.caption2).foregroundStyle(.tertiary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func statesTable(_ analysis: LigandAnalysis) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Shapes found").font(.headline)
            ForEach(analysis.states) { state in
                Toggle(isOn: Binding(
                    get: { intelligence.selected.contains(state.id) },
                    set: { on in
                        if on { intelligence.selected.insert(state.id) }
                        else { intelligence.selected.remove(state.id) }
                    }
                )) {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 8) {
                            Text("Shape \(state.id)").font(.callout.weight(.medium))
                            if state.hasExperimentalSupport {
                                Label("\(state.pdbEntries.count) in the PDB", systemImage: "checkmark.seal.fill")
                                    .font(.caption2).foregroundStyle(.green)
                            }
                            Text("\(Int(state.ensembleFraction * 100))% of the ensemble")
                                .font(.caption2).foregroundStyle(.secondary)
                            if state.relativeEnergy > 0.05 {
                                Text(String(format: "+%.1f kcal/mol", state.relativeEnergy))
                                    .font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                        Text(state.justification)
                            .font(.caption2).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                        if state.hasExperimentalSupport {
                            Text(state.pdbEntries.prefix(8).joined(separator: ", ")
                                 + (state.pdbEntries.count > 8 ? " …" : ""))
                                .font(.system(.caption2, design: .monospaced))
                                .foregroundStyle(.tertiary)
                        }
                    }
                }
                .toggleStyle(.checkbox)
                .disabled(state.sdf == nil)
                .help(state.sdf == nil ? "Not written out — tick a recommended shape instead." : "")
            }
            Text("Energies come from a force field. They are good enough to rank shapes and discard strained ones, and not good enough to be read as populations.")
                .font(.caption2).foregroundStyle(.tertiary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder private func allocationSummary() -> some View {
        let plan = intelligence.plan()
        if plan.isEmpty {
            Label("Nothing selected — the campaign will use a single generated conformer.",
                  systemImage: "exclamationmark.triangle")
                .font(.caption).foregroundStyle(.orange)
        } else {
            VStack(alignment: .leading, spacing: 4) {
                Divider()
                Text("Design budget").font(.headline)
                ForEach(plan, id: \.state.id) { entry in
                    HStack {
                        Text("Shape \(entry.state.id)").font(.callout)
                        Spacer()
                        Text("\(entry.share)%").font(.callout.monospacedDigit())
                        Text("≈ \(request.numDesigns * entry.share / 100) backbones")
                            .font(.caption).foregroundStyle(.secondary)
                            .frame(width: 130, alignment: .trailing)
                    }
                }
                Text("Each shape gets its own fixtures at every binder length, so batching stays intact.")
                    .font(.caption2).foregroundStyle(.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func flexibilityColour(_ level: String) -> Color {
        switch level {
        case "low":      return .green
        case "moderate": return .yellow
        default:         return .red
        }
    }

    /// Push the user's selection into the campaign request, so pressing Start
    /// designs against exactly what is shown here.
    private func syncPlan() {
        request.conformerPlan = intelligence.plan().compactMap { entry in
            guard let sdf = entry.state.sdf else { return nil }
            return ConformerChoice(label: entry.state.id, path: sdf,
                                   weight: Double(entry.share) / 100.0)
        }
    }
}
