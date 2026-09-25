import SwiftUI
import AppKit

struct NISEView: View {
    @EnvironmentObject var app: AppState
    @Environment(\.openWindow) private var openWindow
    @ObservedObject private var jobs = JobCenter.shared
    @StateObject private var ligandAtoms = BoltzLigandAtoms()
    @State private var atomMapVerified = false
    @State private var cohortURL: URL?
    @State private var cohortSummary: String?
    @State private var cohortError: String?
    @State private var cohortLineages: Int?
    let project: Project
    @ObservedObject var controller: NISEController
    @ObservedObject var installer: PipelineInstaller

    private var request: Binding<NISERequest> {
        Binding(get: { app.projects.first(where: { $0.id == project.id })?.nise ?? project.nise },
                set: { value in app.updateProject(id: project.id) { $0.nise = value } })
    }
    private var ready: Bool { installer.isUsable(.boltz) && installer.isUsable(.boltzAffinity) && installer.isUsable(.lasermpnn) && (request.wrappedValue.backbone_method != "rfdiffusion3" || installer.isUsable(.rfd3)) && (!request.wrappedValue.usesNesso || installer.isUsable(request.wrappedValue.screening_engine == "psichic" ? .psichic : .nesso)) }
    private var atomChoicesReady: Bool {
        cohortURL != nil || !request.wrappedValue.hasAtomSelections || (atomMapVerified
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
                Text("Boltz generates structures and checks geometry; LASErMPNN expands surviving trajectories. Choose which model score drives selection below.")
                GroupBox("Starting point") {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Button("Import Phase 0 cohort…", action: chooseCohort)
                            if cohortURL != nil {
                                Button("Use a new backbone search") { cohortURL = nil; cohortSummary = nil; cohortError = nil; cohortLineages = nil }
                            }
                        }
                        if let cohortSummary {
                            Text(cohortSummary).font(.headline)
                            Text("Resume after first-refinement geometry checks. Screen every imported sequence with the selected engine; reuse saved Boltz folds, repeat geometry checks, then select using the chosen objective. Continue remaining refinement, the unrestrained gate and seed selection. Earlier affinity scores and decisions are not imported.").font(.caption)
                            Text("Ligand: \(request.wrappedValue.smiles)").textSelection(.enabled).font(.caption)
                            Text("Saved hotspot and exposure requirements are preserved. Choose NESSO or PSICHIC below; optimisation screening remains independently configurable.").font(.caption)
                        } else {
                            Text("Generate new backbones, or choose an unzipped iProteinStudio cohort folder containing cohort.json.").font(.caption).foregroundStyle(.secondary)
                        }
                        if let cohortError { Text(cohortError).foregroundStyle(.red) }
                    }.padding(8)
                }
                if cohortURL == nil {
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
                }
                GroupBox("1 · Initial backbone generation") {
                    VStack(alignment: .leading, spacing: 10) {
                        if cohortURL == nil {
                        Text("Create independent starting structures around the ligand, refine their pockets, then remove the pocket restraint and test structural consistency.")
                        Picker("Backbone generator", selection: request.backbone_method) {
                            Text("Protein Hunter · X-token hallucination").tag("protein-hunter")
                            Text("RFdiffusion3 · ligand-conditioned diffusion (experimental)").tag("rfdiffusion3")
                        }.accessibilityIdentifier("nise-backbone-method")
                        budgetControl("Starting backbone attempts", value: request.num_starts, range: 1...10000)
                        Text("1,000 is the default for new runs. You can type a different number. Each attempt starts a separate lineage; some lineages may fail selection.")
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
                        }
                        Picker("Experimental screening engine", selection: request.screening_engine) {
                            Text("NESSO-1 (experimental)").tag("nesso")
                            Text("PSICHIC-XL (experimental)").tag("psichic")
                        }
                        Picker("How to use this score", selection: request.scoring_mode) {
                            Text("Prefilter only · Boltz selects").tag("boltz")
                            Text("Optimisation objective · \(request.wrappedValue.screeningLabel) selects").tag("screening")
                        }
                        .accessibilityIdentifier("nise-scoring-mode")
                        if request.wrappedValue.usesScreeningObjective {
                            Text("\(request.wrappedValue.screeningLabel) drives refinement, seed selection, beams, best-so-far and patience using \(request.wrappedValue.objectiveFormula). Boltz generates structures and checks geometry; its affinity head is disabled. Both stages use the selected engine, with separate folding shortlist budgets. The cycle01 baseline is 0.4 for NESSO and 0.2 for PSICHIC; adjust it under Advanced · initial sampling and selection. Experimental objective; not calibrated evidence of binding.").font(.callout)
                        } else {
                            Text("Optional sequence shortlists reduce Boltz work. Boltz ligand pLDDT/100 + P(bind) determines advancement and patience.").font(.caption)
                        }
                        if request.wrappedValue.screening_engine == "psichic" {
                            Text("PSICHIC ranks 1 − nonbinder; affinity and class probabilities are saved. Experimental, with unvalidated binding accuracy. Boltz supplies structural checks. The score-use selector determines final selection. Maximum sequence length: 700 residues.").font(.caption)
                        }
                        Toggle("Use \(request.wrappedValue.screeningLabel) to shortlist initial sequences (experimental)", isOn: request.phase0_nesso_screen)
                            .disabled(cohortURL != nil || request.wrappedValue.usesScreeningObjective)
                            .accessibilityIdentifier("nise-initial-nesso-screen")
                        if request.wrappedValue.phase0_nesso_screen {
                            if cohortURL != nil {
                                Text("The imported round reuses saved sequences and folds. Sampling below applies to subsequent rounds.").font(.caption).foregroundStyle(.secondary)
                            }
                            Text("Each refinement round: LASErMPNN samples \(request.wrappedValue.phase0_seqs1) sequences per lineage → \(request.wrappedValue.screeningLabel) selects up to \(request.wrappedValue.phase0_nesso_refine_top_k) → Boltz folds with the pocket restraint → atom checks → the best passing candidate by the chosen objective advances.")
                                .font(.callout)
                            Text("After the unrestrained gate, \(request.wrappedValue.screeningLabel) scores every expansion sequence and shortlists up to \(request.wrappedValue.phase0_nesso_expand_top_k) in total, at most one per original lineage. Boltz then folds them, checks geometry and the chosen objective selects the stage 2 seeds.")
                                .font(.callout)
                            if request.wrappedValue.screening_engine == "nesso" {
                            Text("NESSO ranks by P(bind) + (1 − pocket-cropped protein–ligand entropy). Missing, out-of-range or near-zero entropy (≤ 0.000001) is rejected. Boltz supplies structural/atom checks; its affinity score is used only in prefilter mode. Failed shortlist candidates are not automatically replaced.")
                                .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        Text("\(request.wrappedValue.phase0_refine_cycles) refinement rounds; \(request.wrappedValue.phase0_gate_seqs) gate sequences per lineage; \(request.wrappedValue.phase0_seqs2) expansion sequences per gate survivor. The gate folds every sampled sequence without the pocket restraint and requires Cα RMSD < \(request.wrappedValue.phase0_sc_ca, specifier: "%.2f") Å. Up to one seed per original lineage enters stage 2.")
                            .font(.caption).foregroundStyle(.secondary)
                        DisclosureGroup("Advanced · initial sampling and selection") {
                            VStack(alignment: .leading, spacing: 10) {
                                budgetControl("Pocket refinement rounds", value: request.phase0_refine_cycles, range: (cohortURL == nil ? 0 : 1)...20)
                                HStack {
                                    Text("First refinement minimum \(request.wrappedValue.objectiveLabel) score (0 disables)")
                                    Spacer()
                                    TextField("0 disables", value: request.objectiveEarlyGate, format: .number)
                                        .textFieldStyle(.roundedBorder).frame(width: 90)
                                }
                                Text(request.wrappedValue.usesScreeningObjective ? "Applies only to cycle01, after geometry checks, using \(request.wrappedValue.objectiveFormula). Defaults: NESSO 0.4; PSICHIC 0.2. These are configurable baseline cutoffs, not calibrated binding probabilities. NESSO uses 0–2; PSICHIC uses 0–1. Each engine retains its own cutoff. Geometry and shortlist limits remain active." : "After geometry checks, retain lineage winners with ligand pLDDT/100 + P(bind) at or above this value. Applies only to the first refinement. The 0.80 pilot threshold is not validated across ligands.")
                                    .font(.caption).foregroundStyle(.secondary)
                                budgetControl("Sequences sampled per lineage per refinement", value: request.phase0_seqs1, range: 1...1024)
                                if request.wrappedValue.phase0_nesso_screen {
                                    budgetControl("\(request.wrappedValue.screeningLabel) shortlist per lineage per refinement", value: request.phase0_nesso_refine_top_k,
                                                  range: 1...max(1, request.wrappedValue.phase0_seqs1))
                                }
                                budgetControl("Gate sequences per lineage (all go to Boltz)", value: request.phase0_gate_seqs, range: 1...1024)
                                rmsdControl("Gate maximum Cα RMSD (Å)", value: request.phase0_sc_ca)
                                budgetControl("Expansion sequences per gate survivor", value: request.phase0_seqs2, range: 1...1024)
                                if request.wrappedValue.phase0_nesso_screen {
                                    budgetControl("Expansion shortlist for Boltz · total", value: request.phase0_nesso_expand_top_k,
                                                  range: max(1, min(10000, request.wrappedValue.trajectories))...10000)
                                }
                                Text("The gate tests consistency against the parent structure; expansion ranks passing structures without another RMSD cutoff. Binding/exposure requirements above apply to every sequence-bearing Boltz result. Atom checks require a fold and cannot be applied by \(request.wrappedValue.screeningLabel).")
                                    .font(.caption).foregroundStyle(.secondary)
                            }.padding(.top, 8)
                        }
                        if cohortURL == nil {
                            Text("Up to \(request.wrappedValue.initialPredictionBudget.formatted()) initial Boltz predictions.").font(.callout.bold())
                        } else {
                            Text("Initial backbone generation and first-refinement folding are reused. Later prediction counts depend on shortlist and geometry survival.").font(.caption)
                        }
                    }.padding(8)
                }
                GroupBox("2 · NISE optimisation") {
                    VStack(alignment: .leading, spacing: 10) {
                        budgetControl("Independent trajectories to optimise", value: request.trajectories,
                                      range: 1...max(1, min(1000, cohortLineages ?? request.wrappedValue.num_starts)))
                        budgetControl("First cycle · proposals from the starting seed", value: request.first_cycle_seqs,
                                      range: max(1, request.wrappedValue.beam)...4096)
                        budgetControl("Later cycles · proposals per parent", value: request.nise_seqs, range: 1...4096)
                        budgetControl("Total sequences to advance per trajectory per cycle", value: request.beam,
                                      range: 1...max(1, min(64, request.wrappedValue.nise_seqs)))
                        Text("Each trajectory starts with one parent. After folding, up to this many passing sequences become its next parents. Later cycles sample the per-parent count above; trajectories never share their survivors.")
                            .font(.caption).foregroundStyle(.secondary)
                        Toggle("Screen sequences with \(request.wrappedValue.screeningLabel) before folding (experimental)", isOn: request.nesso_screen)
                            .disabled(request.wrappedValue.usesScreeningObjective)
                            .accessibilityIdentifier("nise-nesso-screen")
                        if request.wrappedValue.nesso_screen {
                            budgetControl("\(request.wrappedValue.screeningLabel) shortlist per trajectory per proposal round", value: request.nesso_top_k,
                                          range: max(1, request.wrappedValue.beam)...max(request.wrappedValue.beam, request.wrappedValue.nise_seqs))
                            if request.wrappedValue.screening_engine == "nesso" {
                            Text("NESSO ranks the sampled sequences from all parents within each trajectory by P(bind) + (1 − pocket-cropped protein–ligand entropy). Invalid or near-zero entropy (≤ 0.000001) is rejected before selection. Only the shortlist goes to Boltz. Geometry checks and the chosen objective decide which sequences advance. In prefilter mode, this switch controls optimisation independently of initial-stage screening.")
                                .font(.caption).foregroundStyle(.secondary)
                            }
                            Text("Ranking accuracy for these designs is unvalidated; screening can discard useful candidates.")
                                .font(.caption).foregroundStyle(.secondary)
                            if !installer.isUsable(request.wrappedValue.screening_engine == "psichic" ? .psichic : .nesso) {
                                Label("Install \(request.wrappedValue.screeningLabel) from Engines; its required ESM model is included automatically.", systemImage: "shippingbox")
                            }
                        }
                        partialNoisingControls.disabled(request.wrappedValue.usesScreeningObjective)
                        if request.wrappedValue.usesScreeningObjective { Text("Partial noising is unavailable with a complete-sequence objective.").font(.caption) }
                        Toggle("Adaptive proposals · experimental", isOn: request.adaptive_proposals)
                            .disabled(request.wrappedValue.partial_noising)
                        if request.wrappedValue.adaptive_proposals {
                            budgetControl("Starting proposals per parent", value: request.initial_proposals,
                                          range: max(1, request.wrappedValue.beam)...max(request.wrappedValue.beam, request.wrappedValue.nise_seqs))
                            Text("Start small, then double up to the maximum only if the trajectory has not improved enough. With 16 and 64: sample 16, add 16, then add 32 per parent. Parents stay fixed during top-ups; all evaluated candidates compete for the next beam. \(request.wrappedValue.screeningLabel) shortlists each new batch separately. No rollback or rescue. Savings have not been measured.")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        HStack {
                            Text("Minimum \(request.wrappedValue.objectiveLabel) score improvement to reset patience / stop top-ups")
                            Spacer()
                            TextField("0.01", value: request.min_improvement, format: .number)
                                .textFieldStyle(.roundedBorder).frame(width: 90)
                        }
                        if !request.wrappedValue.usesScreeningObjective {
                        Toggle("Selective Boltz affinity evaluation (experimental)", isOn: request.selective_affinity)
                            .disabled(cohortURL != nil)
                        if request.wrappedValue.selective_affinity {
                            Text("Skip affinity for initial backbones and the geometry-only gate. Elsewhere, check geometry first, then evaluate affinity in ligand-confidence order until the remaining score bounds cannot enter the selected beam. \(request.wrappedValue.screeningLabel) screening still runs before folding. Software checks pass; run a small trial before a large campaign.")
                                .font(.caption).foregroundStyle(.secondary)
                            DisclosureGroup("Advanced · affinity batches") {
                                budgetControl("Affinity candidates per selection batch", value: request.affinity_batch_size, range: 1...128)
                                Text("Smaller batches allow earlier stopping. Workers retain their models within each scoring stage; this is not a GPU parallelism setting.").font(.caption)
                            }
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
                        Text("Within-cycle reuse loads each selected model once per scoring batch. Across-cycle reuse also retains \(request.wrappedValue.screeningLabel)/ESM when enabled, alongside the Boltz structure model (and affinity model only for Boltz selection), and uses more memory. Ligand throughput validation is still pending.").font(.caption)
                        TextField("Generation and folding seed", value: request.seed, format: .number)
                            .disabled(cohortURL != nil)
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
                    RunNameField(project: project, mode: .nise)
                    Button(busy ? "Add to Queue" : "Start NISE") {
                        let current = app.projects.first(where: { $0.id == project.id }) ?? project
                        controller.start(request: request.wrappedValue, project: current,
                                         name: current.runNames[WorkspaceMode.nise.rawValue] ?? "", cohort: cohortURL)
                    }
                        .buttonStyle(.borderedProminent).disabled(!ready || !controller.canStartAnother || !request.wrappedValue.validationIssues.isEmpty || !atomChoicesReady)
                        .accessibilityIdentifier("nise-start")
                    if busy { Text("This search will wait in the shared job queue.").font(.caption) }
                }
                if ownsRun {
                    Divider()
                    Text(controller.currentMessage).font(.headline)
                    if case .failed(let message) = controller.phase { Text(message).foregroundStyle(.orange) }
                    HStack {
                        if controller.isRunning { ProgressView().controlSize(.small); Button("Stop", role: .destructive) { controller.cancel() } }
                        else if controller.outputRoot != nil && controller.phase != .finished { Button("Resume saved run") { controller.retry() } }
                        if let root = controller.outputRoot {
                            Button("View results") { openWindow(value: RunResultsWindowRequest(root: root, workflow: .nise)) }
                            if FileManager.default.fileExists(atPath: root.appendingPathComponent("psichic_screening.csv").path) {
                                Button("Open PSICHIC screening table") { NSWorkspace.shared.open(root.appendingPathComponent("psichic_screening.csv")) }
                            }
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
        .onChange(of: request.wrappedValue.scoring_mode) { _, mode in
            if mode == "screening" { request.wrappedValue.enableScreeningObjective() }
        }
        .onChange(of: project.id) { _, _ in
            cohortURL = nil; cohortSummary = nil; cohortError = nil; cohortLineages = nil
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
            request.wrappedValue.initial_proposals = max(request.wrappedValue.beam, min(request.wrappedValue.initial_proposals, max(1, count)))
            request.wrappedValue.nesso_top_k = max(request.wrappedValue.beam, min(request.wrappedValue.nesso_top_k, count))
        }
        .onChange(of: request.wrappedValue.beam) { _, count in
            request.wrappedValue.nesso_top_k = max(count, request.wrappedValue.nesso_top_k)
            request.wrappedValue.initial_proposals = max(count, request.wrappedValue.initial_proposals)
            request.wrappedValue.first_cycle_seqs = max(count, request.wrappedValue.first_cycle_seqs)
            request.wrappedValue.noise_advance = min(request.wrappedValue.noise_advance, max(1, count - 1))
            if count < 2 { request.wrappedValue.partial_noising = false }
        }
        .onChange(of: request.wrappedValue.binder_min_len) { _, minimum in
            request.wrappedValue.binder_max_len = max(request.wrappedValue.binder_max_len, minimum)
        }
        .onChange(of: request.wrappedValue.binder_max_len) { _, maximum in
            request.wrappedValue.binder_min_len = min(request.wrappedValue.binder_min_len, maximum)
        }
    }

    private func chooseCohort() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true; panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.message = "Choose the unzipped NISE cohort folder containing cohort.json."
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            struct Manifest: Decodable {
                let format: String; let schema: Int; let boundary: String
                let candidate_count: Int; let lineage_count: Int; let request: NISERequest
            }
            let file = url.appendingPathComponent("cohort.json")
            let metadata = try file.resourceValues(forKeys: [.fileSizeKey, .isSymbolicLinkKey])
            guard metadata.isSymbolicLink != true, (metadata.fileSize ?? 0) < 100_000_000 else {
                throw CocoaError(.fileReadCorruptFile)
            }
            let manifest = try JSONDecoder().decode(Manifest.self, from: Data(contentsOf: file))
            guard manifest.format == "iproteinstudio-nise-cohort", manifest.schema == 1,
                  manifest.boundary == "phase0.cycle01.after_geometry.before_affinity",
                  (1...30000).contains(manifest.candidate_count),
                  (1...10000).contains(manifest.lineage_count) else { throw CocoaError(.fileReadCorruptFile) }
            var settings = manifest.request
            settings.phase0_nesso_screen = true; settings.nesso_screen = true
            settings.selective_affinity = true; settings.phase0_refine_cycles = max(1, settings.phase0_refine_cycles)
            settings.trajectories = min(settings.trajectories, manifest.lineage_count)
            guard settings.validationIssues.isEmpty else {
                cohortError = settings.validationIssues.joined(separator: " "); return
            }
            request.wrappedValue = settings
            cohortURL = url; cohortLineages = manifest.lineage_count
            cohortSummary = "\(manifest.candidate_count.formatted()) candidates · \(manifest.lineage_count.formatted()) original lineages"
            cohortError = nil
        } catch {
            cohortError = "Could not read this NISE cohort. Choose the unzipped package folder containing cohort.json. \(error.localizedDescription)"
        }
    }

    private var partialNoisingControls: some View {
        VStack(alignment: .leading, spacing: 8) {
            Toggle("Ligand-local X-token noising · experimental", isOn: request.partial_noising)
                .disabled(request.wrappedValue.beam < 2 || request.wrappedValue.adaptive_proposals)
                .accessibilityIdentifier("nise-partial-noising")
            if request.wrappedValue.partial_noising {
                Text("From cycle 2, partial noising replaces ordinary sampling places: use the best \(request.wrappedValue.normalParentCount) current parents for normal MPNN, plus one noising branch from the best current parent. Mask residues near the ligand, fold with Boltz, redesign the best passing backbone with LASErMPNN, then fold and score the complete sequences. Advance \(request.wrappedValue.normalParentCount) normal winners and up to \(request.wrappedValue.noise_advance) repaired winners, within \(request.wrappedValue.beam) total places. Empty branch places stay empty if its candidates fail.")
                    .font(.caption).foregroundStyle(.secondary)
                DisclosureGroup("Partial noising settings") {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text("Ligand neighbourhood radius (Å)"); Spacer()
                            TextField("6", value: request.noise_radius, format: .number)
                                .textFieldStyle(.roundedBorder).frame(width: 80)
                        }
                        HStack {
                            Text("Neighbourhood residues to mask (%)"); Spacer()
                            TextField("25", value: request.noise_percent, format: .number)
                                .textFieldStyle(.roundedBorder).frame(width: 80)
                        }
                        budgetControl("Masked Boltz predictions per trajectory", value: request.noise_predictions, range: 1...1024)
                        budgetControl("MPNN sequences from the chosen masked backbone", value: request.noise_mpnn_seqs,
                                      range: max(1, request.wrappedValue.noise_advance)...4096)
                        budgetControl("Beam places reserved for repaired sequences", value: request.noise_advance,
                                      range: 1...max(1, min(request.wrappedValue.beam - 1, request.wrappedValue.noise_mpnn_seqs)))
                        Text("Distance uses the nearest protein/ligand heavy atoms. Mask a random subset of that neighbourhood, with at least one residue and a separate recorded folding seed per prediction. The 6 Å / 25% starting settings are unvalidated. No eligible residues means no branch for that cycle.")
                            .font(.caption).foregroundStyle(.secondary)
                    }.padding(.top, 8)
                }
                Text("This masks sequence identities; it does not freeze coordinates outside the pocket. Masked structures are intermediates, never final designs. \(request.wrappedValue.screeningLabel) screens only complete MPNN sequences. Existing RMSD, Bind and Expose checks still apply. The branch uses up to \(request.wrappedValue.noisingPredictionBudget.formatted()) Boltz predictions across all trajectories per later cycle; totals below also account for the reduced ordinary parent count.")
                    .font(.caption).foregroundStyle(.secondary)
            } else if request.wrappedValue.beam < 2 || request.wrappedValue.adaptive_proposals {
                Text("Partial noising needs at least two beam places and fixed sampling.")
                    .font(.caption).foregroundStyle(.secondary)
            }
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
