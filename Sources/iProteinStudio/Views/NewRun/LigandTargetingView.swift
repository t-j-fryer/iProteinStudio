import SwiftUI

/// Choose which atoms of a small molecule the binder should wrap around, and
/// understand the molecule before committing GPU hours to it.
///
/// Two things are worth knowing about what this produces.
///
/// Boltz only has *positive* contacts — there is no "keep this atom exposed"
/// field. Leaving a linker out of the contact list is a nudge, not a guarantee,
/// so linker exposure has to be checked in the results rather than assumed.
///
/// And the atom names are not stable. Enabling the affinity head standardises
/// the SMILES before naming, which renumbers every atom. Names are regenerated
/// whenever either changes, and a run is blocked if they are stale.
struct LigandTargetingView: View {
    @Binding var request: DesignRequest
    @ObservedObject var atoms: BoltzLigandAtoms
    @ObservedObject var intelligence: LigandIntelligence
    let outputDir: URL

    @State private var atomSymbols: [String] = []

    private var smiles: String { request.targetSmiles.trimmingCharacters(in: .whitespaces) }
    private var namesReady: Bool { atoms.generatedFor == request.ligandAtomKey && atoms.hasAtoms }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Toggle("Predict binding strength, P(bind)", isOn: $request.ligandAffinityHead)
                .toggleStyle(.checkbox)
                .disabled(!request.usesBoltzAnywhere)
            Text("Turns on Boltz's affinity head. It also renumbers every ligand atom, so the choices below are rebuilt when you change it.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if !request.usesBoltzAnywhere {
                Label("Add Boltz as the design engine or a checking engine to predict binding strength.",
                      systemImage: "info.circle")
                    .font(.caption2).foregroundStyle(.secondary)
            }

            Divider()
            understandingSection
            Divider()
            atomSection
                .disabled(!request.usesBoltzDesignEngine)
            if !request.usesBoltzDesignEngine {
                Label("Specific-atom pocket steering is a Boltz design feature. Select Boltz as the design engine to use it.",
                      systemImage: "info.circle")
                    .font(.caption2).foregroundStyle(.secondary)
            }
        }
        .onChange(of: request.ligandAffinityHead) { _, _ in invalidate() }
        .onChange(of: request.targetSmiles) { _, _ in invalidate() }
    }

    private func invalidate() {
        // Never carry names across a renumbering.
        request.ligandContactAtoms = []
        request.ligandAtomsGeneratedFor = ""
        request.ligandAttachmentAtom = nil
        request.ligandAttachmentLinkerAtom = nil
        atoms.reset()
        intelligence.reset()
    }

    // MARK: Understanding the molecule

    private var understandingSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Understand the molecule").font(.headline)
            Text("Chemistry checks, and which part of the molecule binding is actually about. Unlike the RFdiffusion3 tab there is no conformer choice here — Boltz builds the ligand's shape itself from the SMILES, so there is nothing to pick between.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            Toggle("This molecule is attached to something (a protein, a surface, a bead)",
                   isOn: Binding(get: { request.ligandIsConjugated },
                                 set: { on in
                                     request.ligandIsConjugated = on
                                     intelligence.reset()
                                     if !on {
                                         request.ligandAttachmentAtom = nil
                                         request.ligandAttachmentLinkerAtom = nil
                                     }
                                 }))
                .toggleStyle(.checkbox).font(.callout)

            if request.ligandIsConjugated {
                Text(request.ligandAttachmentAtom == nil
                     ? "First select the atom on the binding-core side of the linker bond."
                     : request.ligandAttachmentLinkerAtom == nil
                     ? "Now select its directly bonded neighbour on the linker side."
                     : "The directed core-to-linker bond is selected; click either endpoint to clear it.")
                    .font(.caption)
                    .foregroundStyle(request.ligandAttachmentLinkerAtom == nil ? .orange : .secondary)
            }

            HStack {
                Button {
                    intelligence.analyse(smiles: smiles,
                                         attachmentAtom: request.ligandAttachmentAtom,
                                         attachmentLinkerAtom: request.ligandAttachmentLinkerAtom,
                                         attachmentSymbol: selectedSymbol(request.ligandAttachmentAtom),
                                         attachmentLinkerSymbol: selectedSymbol(request.ligandAttachmentLinkerAtom),
                                         searchPDB: true, outputDir: outputDir)
                } label: {
                    Label(intelligence.hasResult ? "Check again" : "Check this molecule",
                          systemImage: "sparkles.rectangle.stack")
                }
                .disabled(intelligence.isRunning || smiles.isEmpty ||
                          (request.ligandIsConjugated && (request.ligandAttachmentAtom == nil ||
                                            request.ligandAttachmentLinkerAtom == nil)))
                if intelligence.isRunning { ProgressView().controlSize(.small) }
            }

            if let error = intelligence.error {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let analysis = intelligence.analysis {
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
                if !analysis.core.presentationAtoms.isEmpty {
                    Label("\(analysis.core.coreAtoms.count) atoms are binding core, \(analysis.core.presentationAtoms.count) are linker. Aim at the core; leave the linker out.",
                          systemImage: "scissors")
                        .font(.caption).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    // MARK: Atom targeting

    private var atomSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Aim at specific atoms").font(.headline)
            Text("Optional. Naming atoms makes the binder build a pocket around them instead of anywhere on the molecule.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            HStack {
                Button {
                    atoms.resolve(smiles: smiles, affinityHead: request.ligandAffinityHead)
                } label: {
                    Label(namesReady ? "Reload atoms" : "Load this molecule's atoms",
                          systemImage: "atom")
                }
                .disabled(atoms.isResolving || smiles.isEmpty)
                if atoms.isResolving { ProgressView().controlSize(.small) }
                if atoms.standardized {
                    Label("names shifted by the affinity head", systemImage: "info.circle")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }
            if let error = atoms.error {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption).foregroundStyle(.orange)
            }

            if namesReady {
                if atoms.canPickOnStructure {
                    LigandAtomPicker(
                        smiles: smiles,
                        attachmentAtom: Binding(
                            get: { request.ligandAttachmentAtom },
                            set: { request.ligandAttachmentAtom = $0 }),
                        attachmentLinkerAtom: Binding(
                            get: { request.ligandAttachmentLinkerAtom },
                            set: { request.ligandAttachmentLinkerAtom = $0 }),
                        coreAtoms: intelligence.analysis?.core.coreAtoms ?? [],
                        presentationAtoms: intelligence.analysis?.core.presentationAtoms ?? [],
                        atomLabels: atoms.namesByInputIndex,
                        allowsAttachmentPicking: request.ligandIsConjugated,
                        onAtomsResolved: { atomSymbols = $0 }
                    )
                    .frame(height: 240)
                    .background(RoundedRectangle(cornerRadius: 8).fill(.white))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
                    .onChange(of: request.ligandAttachmentAtom) { _, _ in intelligence.reset() }
                    .onChange(of: request.ligandAttachmentLinkerAtom) { _, _ in intelligence.reset() }
                }

                Text("Contact atoms").font(.callout.weight(.medium))
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 74), spacing: 6)], spacing: 6) {
                    ForEach(atoms.atoms) { atom in
                        let picked = request.ligandContactAtoms.contains(atom.name)
                        Button {
                            toggle(atom.name)
                        } label: {
                            Text(atom.name)
                                .font(.system(.caption, design: .monospaced))
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 4)
                        }
                        .buttonStyle(.bordered)
                        .tint(picked ? .accentColor : .secondary)
                    }
                }

                HStack {
                    Text("Contact distance").font(.callout)
                    Slider(value: $request.ligandContactDistance, in: 3...10, step: 0.5).frame(width: 180)
                    Text(String(format: "%.1f Å", request.ligandContactDistance))
                        .font(.callout.monospacedDigit())
                }
                Toggle("Actively steer towards these contacts", isOn: $request.ligandContactForce)
                    .toggleStyle(.checkbox).font(.callout)
                Text("Steering turns the restraint from a hint into something the model is pushed to satisfy. It switches on Boltz's potentials, which roughly doubles the time.")
                    .font(.caption2).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                if !request.ligandContactAtoms.isEmpty {
                    Label("Boltz has no way to keep an atom exposed — leaving the linker out only removes the pull towards it. Check the linker really is solvent-facing in the results.",
                          systemImage: "info.circle")
                        .font(.caption2).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            } else if request.ligandAtomsStale {
                Label("The saved atom names were generated for different settings and would now point at the wrong atoms. Reload them.",
                      systemImage: "exclamationmark.triangle.fill")
                    .font(.caption).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func toggle(_ name: String) {
        if let index = request.ligandContactAtoms.firstIndex(of: name) {
            request.ligandContactAtoms.remove(at: index)
        } else {
            request.ligandContactAtoms.append(name)
        }
        request.ligandAtomsGeneratedFor = request.ligandContactAtoms.isEmpty ? "" : request.ligandAtomKey
    }

    private func selectedSymbol(_ index: Int?) -> String? {
        guard let index, atomSymbols.indices.contains(index) else { return nil }
        return atomSymbols[index]
    }
}
