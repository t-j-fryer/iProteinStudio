import SwiftUI
import AppKit

struct NISEView: View {
    @EnvironmentObject var app: AppState
    @Environment(\.openWindow) private var openWindow
    @ObservedObject private var jobs = JobCenter.shared
    @StateObject private var ligandAtoms = BoltzLigandAtoms()
    @State private var atomMapVerified = false
    let project: Project
    @ObservedObject var controller: NISEController
    @ObservedObject var installer: PipelineInstaller

    private var request: Binding<NISERequest> {
        Binding(get: { app.projects.first(where: { $0.id == project.id })?.nise ?? project.nise },
                set: { value in app.updateProject(id: project.id) { $0.nise = value } })
    }
    private var ready: Bool { installer.isUsable(.boltz) && installer.isUsable(.boltzAffinity) && installer.isUsable(.lasermpnn) && (request.wrappedValue.backbone_method != "rfdiffusion3" || installer.isUsable(.rfd3)) && (!request.wrappedValue.usesNesso || installer.isUsable(.nesso)) }
    private var atomChoicesReady: Bool {
        !request.wrappedValue.hasAtomSelections || (atomMapVerified
            && ligandAtoms.signature == request.wrappedValue.ligand_atom_signature
            && request.wrappedValue.exposed_atoms.count < ligandAtoms.atoms.count)
    }
    private var busy: Bool { controller.isRunning || app.run.isRunning || app.rfd3.isRunning || app.prediction.isRunning || !jobs.active.isEmpty }
    private var ownsRun: Bool { controller.projectSlug == project.slug }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("NISE").font(.largeTitle.bold())
                Text("Design small-molecule binding pockets through selection and expansion.")
                    .font(.title3).foregroundStyle(.secondary)
                Text("Boltz scores ligand-bound structures; LASErMPNN expands each surviving trajectory. Computed scores prioritize candidates for experiments.")
                GroupBox("Small molecule") {
                    VStack(alignment: .leading, spacing: 10) {
                        TextField("SMILES", text: request.smiles, axis: .vertical)
                            .textFieldStyle(.roundedBorder).lineLimit(2...5)
                            .accessibilityIdentifier("nise-smiles")
                        Button("Use fluorescein hydroxyethylamide") { request.wrappedValue.smiles = ExampleTarget.fluorescein.smiles }
                        NISEAtomTargetingView(request: request, atoms: ligandAtoms, verified: $atomMapVerified)
                    }.padding(8)
                }
                HStack {
                    Button("Small trial") { request.wrappedValue.useSmallTrial() }
                    Button("Default settings") {
                        let smiles = request.wrappedValue.smiles
                        request.wrappedValue = NISERequest(); request.wrappedValue.smiles = smiles
                    }
                }
                GroupBox("1 · Initial backbone generation") {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Create independent starting structures around the ligand, refine their pockets, then remove the pocket restraint and test structural consistency.")
                        Picker("Backbone generator", selection: request.backbone_method) {
                            Text("Protein Hunter · X-token hallucination").tag("protein-hunter")
                            Text("RFdiffusion3 · ligand-conditioned diffusion (experimental)").tag("rfdiffusion3")
                        }.accessibilityIdentifier("nise-backbone-method")
                        budgetControl("Starting backbone attempts", value: request.num_starts, range: 1...10000)
                        Text("100 is the default, matching the original fluorescein campaign. You can type a different number. Each attempt starts a separate lineage; some lineages may fail selection.")
                            .font(.caption).foregroundStyle(.secondary)
                        budgetControl("Minimum binder length", value: request.binder_min_len, range: 60...250)
                        budgetControl("Maximum binder length", value: request.binder_max_len, range: 60...250)
                        if request.wrappedValue.backbone_method == "rfdiffusion3" {
                            budgetControl("Binder length groups", value: request.rfd3_num_bins, range: 1...20)
                            Text("Lengths: \(request.wrappedValue.rfd3Lengths.map(String.init).joined(separator: ", ")) residues. The total backbone count is shared evenly across these lengths; it is not multiplied by the number of groups. One group uses the midpoint.")
                                .font(.caption).foregroundStyle(.secondary)
                            Text("RFdiffusion3 generates backbones around one fixed ligand conformer, using 200 diffusion steps, 2 recycles and BF16. Its workers reuse weights across batches and exit before Boltz starts. The subsequent NISE search uses the same controls below; this combined path is experimental.")
                                .font(.caption).foregroundStyle(.secondary)
                            if !installer.isUsable(.rfd3) {
                                Label("Install RFdiffusion3 from Engines to use this generator.", systemImage: "shippingbox")
                            }
                            Text("\(request.wrappedValue.num_starts.formatted()) RFdiffusion3 backbones, followed by the initial Boltz funnel below.")
                                .font(.callout.bold())
                        }
                        Toggle("Use NESSO to shortlist initial sequences (experimental)", isOn: request.phase0_nesso_screen)
                            .accessibilityIdentifier("nise-initial-nesso-screen")
                        if request.wrappedValue.phase0_nesso_screen {
                            Text("Each refinement round: LASErMPNN samples \(request.wrappedValue.phase0_seqs1) sequences per lineage → NESSO selects up to \(request.wrappedValue.phase0_nesso_refine_top_k) → Boltz folds with the pocket restraint → atom checks → one best structure advances.")
                                .font(.callout)
                            Text("After the unrestrained gate, NESSO scores every expansion sequence and shortlists up to \(request.wrappedValue.phase0_nesso_expand_top_k) in total, at most one per original lineage. Boltz then folds and scores them to select the stage 2 seeds.")
                                .font(.callout)
                            Text("NESSO ranks by P(bind) + (1 − pocket-cropped protein–ligand entropy). Missing, out-of-range or near-zero entropy (≤ 0.000001) is rejected. Boltz still supplies ligand pLDDT + P(bind) and all structural/atom checks. Failed shortlist candidates are not automatically replaced.")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Text("\(request.wrappedValue.phase0_refine_cycles) refinement rounds; \(request.wrappedValue.phase0_gate_seqs) gate sequences per lineage; \(request.wrappedValue.phase0_seqs2) expansion sequences per gate survivor. The gate folds every sampled sequence without the pocket restraint and requires Cα RMSD < \(request.wrappedValue.phase0_sc_ca, specifier: "%.2f") Å. Up to one seed per original lineage enters stage 2.")
                            .font(.caption).foregroundStyle(.secondary)
                        DisclosureGroup("Advanced · initial sampling and selection") {
                            VStack(alignment: .leading, spacing: 10) {
                                budgetControl("Pocket refinement rounds", value: request.phase0_refine_cycles, range: 0...20)
                                budgetControl("Sequences sampled per lineage per refinement", value: request.phase0_seqs1, range: 1...1024)
                                if request.wrappedValue.phase0_nesso_screen {
                                    budgetControl("NESSO shortlist per lineage per refinement", value: request.phase0_nesso_refine_top_k,
                                                  range: 1...max(1, request.wrappedValue.phase0_seqs1))
                                }
                                budgetControl("Gate sequences per lineage (all go to Boltz)", value: request.phase0_gate_seqs, range: 1...1024)
                                rmsdControl("Gate maximum Cα RMSD (Å)", value: request.phase0_sc_ca)
                                budgetControl("Expansion sequences per gate survivor", value: request.phase0_seqs2, range: 1...1024)
                                if request.wrappedValue.phase0_nesso_screen {
                                    budgetControl("Expansion shortlist for Boltz · total", value: request.phase0_nesso_expand_top_k,
                                                  range: max(1, min(10000, request.wrappedValue.trajectories))...10000)
                                }
                                Text("The gate tests consistency against the parent structure; expansion ranks passing structures without another RMSD cutoff. Binding/exposure requirements above apply to every sequence-bearing Boltz result. Atom checks require a fold and cannot be applied by NESSO.")
                                    .font(.caption).foregroundStyle(.secondary)
                            }.padding(.top, 8)
                        }
                        Text("Up to \(request.wrappedValue.initialPredictionBudget.formatted()) initial Boltz predictions.").font(.callout.bold())
                    }.padding(8)
                }
                GroupBox("2 · NISE optimisation") {
                    VStack(alignment: .leading, spacing: 10) {
                        budgetControl("Independent trajectories to optimise", value: request.trajectories,
                                      range: 1...max(1, min(1000, request.wrappedValue.num_starts)))
                        budgetControl("Sequences sampled per parent per cycle", value: request.nise_seqs, range: 1...4096)
                        budgetControl("Sequences to advance per trajectory per cycle", value: request.beam,
                                      range: 1...max(1, min(64, request.wrappedValue.nise_seqs)))
                        Text("Each trajectory starts with one parent. After folding, up to this many passing sequences become its next parents. Every parent samples the number above; trajectories never share their survivors.")
                            .font(.caption).foregroundStyle(.secondary)
                        Toggle("Screen sequences with NESSO before folding (experimental)", isOn: request.nesso_screen)
                            .accessibilityIdentifier("nise-nesso-screen")
                        if request.wrappedValue.nesso_screen {
                            budgetControl("NESSO shortlist to fold per trajectory per cycle", value: request.nesso_top_k,
                                          range: max(1, request.wrappedValue.beam)...max(request.wrappedValue.beam, request.wrappedValue.nise_seqs))
                            Text("NESSO ranks the sampled sequences from all parents within each trajectory by P(bind) + (1 − pocket-cropped protein–ligand entropy). Invalid or near-zero entropy (≤ 0.000001) is rejected before selection. Only the shortlist goes to Boltz. Boltz scores and structural checks then decide which sequences advance. This switch controls optimisation independently of initial-stage NESSO screening.")
                                .font(.caption).foregroundStyle(.secondary)
                            Text("Native-MPS execution was validated upstream. Ranking accuracy for these designs is unvalidated; screening can discard useful candidates.")
                                .font(.caption).foregroundStyle(.secondary)
                            if !installer.isUsable(.nesso) {
                                Label("Install NESSO-1 from Engines; its required ESM-2 650M model is included automatically.", systemImage: "shippingbox")
                            }
                        }
                        DisclosureGroup("Advanced · optimisation structural filters") {
                            VStack(alignment: .leading, spacing: 10) {
                                rmsdControl("Maximum Cα RMSD (Å)", value: request.nise_sc_ca)
                                rmsdControl("Maximum ligand RMSD (Å)", value: request.nise_sc_lig)
                                budgetControl("First cycle requiring ligand consistency", value: request.nise_ligand_sc_from_cycle, range: 1...1001)
                                Text("RMSD compares each folded candidate with its parent. Ligand checks start at the chosen cycle; choosing a cycle beyond the run length leaves only Cα and atom checks active. The pocket restraint stays off during optimisation.")
                                    .font(.caption).foregroundStyle(.secondary)
                            }.padding(.top, 8)
                        }
                        budgetControl("Maximum optimisation cycles", value: request.max_cycles, range: 1...1000)
                        budgetControl("Stop after cycles without improvement", value: request.patience, range: 1...1000)
                        Text("Up to \(request.wrappedValue.firstCyclePredictionBudget.formatted()) Boltz predictions in the first cycle; \(request.wrappedValue.cyclePredictionBudget.formatted()) per later cycle. Up to \(request.wrappedValue.optimizationPredictionBudget.formatted()) across optimisation.")
                            .font(.callout.bold())
                        Text("These are upper bounds, not runtime estimates. Fewer surviving lineages, failed structural checks and early stopping reduce work. Increasing the number advanced increases sampling in later cycles.")
                            .font(.caption).foregroundStyle(.secondary)
                    }.padding(8)
                }
                GroupBox("Final pocket analysis") {
                    VStack(alignment: .leading) {
                        Toggle("Compare the best candidates with the ligand removed", isOn: request.preorganisation)
                        if request.wrappedValue.preorganisation {
                            Stepper("Shortlist: up to \(request.wrappedValue.top_x) candidates", value: request.top_x, in: 1...64)
                            Text("Measures pocket side-chain geometry and whole-binder stability. This final ranking does not change which sequences the search advances.").font(.caption)
                        }
                    }.padding(8)
                }
                DisclosureGroup("Execution and reproducibility") {
                    VStack(alignment: .leading, spacing: 8) {
                        Picker("Model reuse", selection: request.scheduler) {
                            Text("Within each cycle").tag("cycle-wave")
                            Text("Across cycles (experimental)").tag("resident")
                        }
                        Text("Within-cycle reuse loads each selected model once per scoring batch. Across-cycle reuse also retains NESSO/ESM when enabled, alongside Boltz structure and affinity models, and uses more memory. Ligand throughput validation is still pending.").font(.caption)
                        TextField("Generation and folding seed", value: request.seed, format: .number)
                        Text("LASErMPNN has no upstream seed control. Studio saves the exact sampled sequences and audited predictions for resume.").font(.caption)
                    }
                }
                if !ready { Label("Install the selected NISE engines from Engines to start.", systemImage: "shippingbox") }
                if request.wrappedValue.hasAtomSelections && !atomMapVerified {
                    Text("Load the molecule to verify its saved atom choices before starting.").font(.caption).foregroundStyle(.orange)
                }
                if atomMapVerified && request.wrappedValue.exposed_atoms.count == ligandAtoms.atoms.count {
                    Text("Leave at least one ligand atom available for binding.").font(.caption).foregroundStyle(.orange)
                }
                ForEach(request.wrappedValue.validationIssues, id: \.self) { Text($0).foregroundStyle(.orange) }
                HStack {
                    Button("Start NISE") { controller.start(request: request.wrappedValue, project: project) }
                        .buttonStyle(.borderedProminent).disabled(!ready || busy || !request.wrappedValue.validationIssues.isEmpty || !atomChoicesReady)
                        .accessibilityIdentifier("nise-start")
                    if busy { Text("Active work must finish or stop before another search starts.").font(.caption) }
                }
                if ownsRun {
                    Divider()
                    Text(controller.currentMessage).font(.headline)
                    if case .failed(let message) = controller.phase { Text(message).foregroundStyle(.orange) }
                    HStack {
                        if controller.isRunning { ProgressView().controlSize(.small); Button("Stop", role: .destructive) { controller.cancel() } }
                        else if controller.outputRoot != nil && controller.phase != .finished { Button("Resume saved run") { controller.retry() }.disabled(busy) }
                        if let root = controller.outputRoot {
                            Button("View results") { openWindow(value: RunResultsWindowRequest(root: root, workflow: .nise)) }
                            if FileManager.default.fileExists(atPath: root.appendingPathComponent("nesso_screening.csv").path) {
                                Button("Open NESSO screening table") { NSWorkspace.shared.open(root.appendingPathComponent("nesso_screening.csv")) }
                            }
                            if FileManager.default.fileExists(atPath: root.appendingPathComponent("atom_checks.csv").path) {
                                Button("Open atom checks") { NSWorkspace.shared.open(root.appendingPathComponent("atom_checks.csv")) }
                            }
                            Button("Reveal files") { NSWorkspace.shared.activateFileViewerSelecting([root]) }
                        }
                    }
                    if !controller.log.isEmpty {
                        DisclosureGroup("Run log") { Text(controller.log.suffix(40).joined(separator: "\n")).font(.caption.monospaced()).textSelection(.enabled) }
                    }
                }
            }.padding(24).frame(maxWidth: 860, alignment: .leading).frame(maxWidth: .infinity)
        }
        .onChange(of: request.wrappedValue.phase0_seqs1) { _, count in
            request.wrappedValue.phase0_nesso_refine_top_k = min(request.wrappedValue.phase0_nesso_refine_top_k, max(1, count))
        }
        .onChange(of: request.wrappedValue.trajectories) { _, count in
            request.wrappedValue.phase0_nesso_expand_top_k = max(request.wrappedValue.phase0_nesso_expand_top_k, count)
        }
        .onChange(of: request.wrappedValue.num_starts) { _, starts in
            request.wrappedValue.trajectories = min(request.wrappedValue.trajectories, max(1, starts))
        }
        .onChange(of: request.wrappedValue.nise_seqs) { _, count in
            request.wrappedValue.beam = min(request.wrappedValue.beam, count)
            request.wrappedValue.nesso_top_k = max(request.wrappedValue.beam, min(request.wrappedValue.nesso_top_k, count))
        }
        .onChange(of: request.wrappedValue.beam) { _, count in
            request.wrappedValue.nesso_top_k = max(count, request.wrappedValue.nesso_top_k)
        }
        .onChange(of: request.wrappedValue.binder_min_len) { _, minimum in
            request.wrappedValue.binder_max_len = max(request.wrappedValue.binder_max_len, minimum)
        }
        .onChange(of: request.wrappedValue.binder_max_len) { _, maximum in
            request.wrappedValue.binder_min_len = min(request.wrappedValue.binder_min_len, maximum)
        }
    }

    private func rmsdControl(_ label: String, value: Binding<Double>) -> some View {
        HStack {
            Text(label)
            Spacer()
            TextField(label, value: value, format: .number.precision(.fractionLength(1...2)))
                .frame(width: 80).textFieldStyle(.roundedBorder)
                .accessibilityLabel(label)
            Stepper(label, value: value, in: 0.1...10, step: 0.1).labelsHidden()
        }
    }

    private func budgetControl(_ label: String, value: Binding<Int>, range: ClosedRange<Int>) -> some View {
        HStack {
            Text(label)
            Spacer()
            EditableIntStepper(value: value, in: range, accessibilityLabel: label)
        }
    }
}
