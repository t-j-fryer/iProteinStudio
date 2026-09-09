import Foundation

/// Inverse-folding backend used for sequence redesign.
enum SequenceDesigner: String, CaseIterable, Codable, Identifiable {
    case antifold, abmpnn, proteinmpnn, solublempnn, ligandmpnn, lasermpnn

    var id: String { rawValue }

    var label: String {
        switch self {
        case .antifold:     return "AntiFold"
        case .abmpnn:       return "AbMPNN"
        case .proteinmpnn:  return "ProteinMPNN"
        case .solublempnn:  return "SolubleMPNN"
        case .ligandmpnn:   return "LigandMPNN"
        case .lasermpnn:    return "LASErMPNN"
        }
    }

    /// One-line, novice-friendly description.
    var blurb: String {
        switch self {
        case .antifold:     return "Antibody-aware. Best default for nanobody CDR design."
        case .abmpnn:       return "Antibody-fine-tuned ProteinMPNN. Great for CDR redesign."
        case .proteinmpnn:  return "General-purpose protein sequence design."
        case .solublempnn:  return "Tuned for soluble proteins. The usual choice for a de-novo binder."
        case .ligandmpnn:   return "Ligand-aware. Sees the small molecule while choosing residues."
        case .lasermpnn:    return "Ligand-aware, and also places side chains. Tends to over-pack the pocket less than LigandMPNN."
        }
    }

    /// Which installed component this designer needs.
    var component: InstallComponent {
        switch self {
        case .abmpnn:    return .abmpnn
        case .antifold:  return .antifold
        case .lasermpnn: return .lasermpnn
        default:         return .mpnn
        }
    }

    /// LASErMPNN has no MPS build, so it runs on CPU. Worth saying, because a
    /// user watching GPU load will otherwise think it has stalled.
    var runsOnCPU: Bool { self == .lasermpnn }
}

/// What kind of binder is being designed.
enum DesignType: String, CaseIterable, Codable, Identifiable, Hashable {
    case nanobody      // fixed VHH scaffold, redesign CDRs (AntiFold / MPNN)
    case minibinder    // de novo mini-protein binder vs a target (random binder + MPNN)
    case peptide       // short de novo peptide binder

    var id: String { rawValue }
    var label: String {
        switch self {
        case .nanobody:   return "Nanobody"
        case .minibinder: return "Mini-binder"
        case .peptide:    return "Peptide"
        }
    }
    var blurb: String {
        switch self {
        case .nanobody:   return "Redesign the CDR loops of a stable VHH scaffold against your target."
        case .minibinder: return "Design a de-novo mini-protein binder against your target."
        case .peptide:    return "Design a short de-novo peptide binder against your target."
        }
    }
    var usesScaffold: Bool { self == .nanobody }
    /// Default de-novo binder length range.
    var defaultLengthRange: ClosedRange<Int> {
        switch self {
        case .nanobody:   return 110...130
        case .minibinder: return 60...120
        case .peptide:    return 8...25
        }
    }
}

/// How the number of concurrent predictions is chosen.
enum ParallelMode: String, CaseIterable, Codable, Identifiable, Hashable {
    case auto, performance, manual
    var id: String { rawValue }
    var label: String {
        switch self {
        case .auto:        return "Automatic"
        case .performance: return "Performance"
        case .manual:      return "Manual"
        }
    }
    var blurb: String {
        switch self {
        case .auto:        return "Safe: uses only currently-free memory, leaving other apps responsive."
        case .performance: return "Uses more of your total RAM for design — other apps may slow down or swap."
        case .manual:      return "You set the number directly (no memory check)."
        }
    }
}

/// Whether the target is a protein (sequence) or a small molecule (SMILES).
enum TargetKind: String, CaseIterable, Codable, Identifiable, Hashable {
    case protein, ligand
    var id: String { rawValue }
    var label: String { self == .protein ? "Protein" : "Ligand (SMILES)" }
}

/// Experimental sequence priors for de-novo binders. These affect cycle-0
/// sampling and ProteinMPNN-family redesign logits; they do not guarantee the
/// secondary structure produced by a structure predictor.
enum SecondaryStructureBias: String, CaseIterable, Codable, Identifiable, Hashable {
    case none
    case antihelix
    case beta
    case mixed

    var id: String { rawValue }
    var label: String {
        switch self {
        case .none:      return "Natural diversity"
        case .antihelix: return "Reduce α-helix"
        case .beta:      return "Encourage β-rich"
        case .mixed:     return "β-rich + reduce α-helix"
        }
    }
    var blurb: String {
        switch self {
        case .none:
            return "No secondary-structure sequence prior."
        case .antihelix:
            return "Downweights helix-prone residue patterns without assuming that coil is β-sheet."
        case .beta:
            return "Uses short strand blocks, noisy alternating faces, solvent-friendly edges, and localized turns."
        case .mixed:
            return "Combines the β-oriented grammar with moderate α-helix suppression."
        }
    }
}

enum SecondaryStructureBiasScope: String, CaseIterable, Codable, Identifiable, Hashable {
    case seedOnly
    case seedAndCycles

    var id: String { rawValue }
    var label: String {
        switch self {
        case .seedOnly:      return "Starting sequence only"
        case .seedAndCycles: return "Starting sequence + MPNN cycles"
        }
    }
    var cliValue: String {
        switch self {
        case .seedOnly:      return "seed-only"
        case .seedAndCycles: return "seed-and-cycles"
        }
    }
}

/// Structural conditioning applied to the target during design cycles only.
/// Independent post-prediction is intentionally always blind to this setting.
enum TargetTemplateMode: String, CaseIterable, Codable, Identifiable, Hashable {
    case guide
    case strong

    var id: String { rawValue }
}

/// Which iterative checkpoints receive an independent re-fold.
enum PostCheckScope: String, CaseIterable, Codable, Identifiable, Hashable {
    case finalCycle
    case allCycles

    var id: String { rawValue }
}

/// Which CDR loops to redesign. Applies to every designer.
struct CDRSelection: Codable, Equatable, Hashable {
    var cdr1 = false
    var cdr2 = false
    var cdr3 = true

    var isEmpty: Bool { !(cdr1 || cdr2 || cdr3) }

    /// Space-separated flag value, e.g. "CDR1 CDR3".
    var flagValue: String {
        var parts: [String] = []
        if cdr1 { parts.append("CDR1") }
        if cdr2 { parts.append("CDR2") }
        if cdr3 { parts.append("CDR3") }
        return parts.joined(separator: " ")
    }
}

/// A frozen framework selection; catalog updates cannot alter saved sequences.
struct NanobodyScaffoldAllocation: Codable, Hashable, Identifiable {
    var id: String
    var name: String
    var sequence: String
    var trajectories: Int
}

/// Everything the user specifies for a design campaign.
struct DesignRequest: Codable, Equatable, Hashable {
    var designType: DesignType = .nanobody

    // Nanobody (scaffold) fields
    var scaffoldID: String = "7xl0_vobarilizumab"
    var scaffoldSequence: String = ""
    /// nil retains the historical single-scaffold request; [] is deliberately invalid.
    var scaffoldSelections: [NanobodyScaffoldAllocation]? = nil
    var equalScaffoldBudgets = true

    var allocatedScaffolds: [NanobodyScaffoldAllocation] {
        var selected = scaffoldSelections ?? [.init(id: scaffoldID, name: scaffoldID,
                                                   sequence: scaffoldSequence, trajectories: numDesigns)]
        if equalScaffoldBudgets && !selected.isEmpty {
            for i in selected.indices {
                selected[i].trajectories = numDesigns / selected.count + (i < numDesigns % selected.count ? 1 : 0)
            }
        }
        return selected
    }

    mutating func setEqualScaffoldBudgets(_ equal: Bool) {
        scaffoldSelections = allocatedScaffolds
        equalScaffoldBudgets = equal
    }

    mutating func setScaffold(id: String, name: String, sequence: String, selected: Bool) {
        var values = allocatedScaffolds
        if selected && !values.contains(where: { $0.id == id }) {
            values.append(.init(id: id, name: name, sequence: sequence,
                                trajectories: max(1, numDesigns / (values.count + 1))))
        } else if !selected { values.removeAll { $0.id == id } }
        scaffoldSelections = values
        if equalScaffoldBudgets { numDesigns = max(numDesigns, values.count) }
        else { numDesigns = values.reduce(0) { $0 + $1.trajectories } }
    }

    mutating func setScaffoldBudget(id: String, trajectories: Int) {
        var values = allocatedScaffolds
        guard let index = values.firstIndex(where: { $0.id == id }) else { return }
        values[index].trajectories = trajectories
        scaffoldSelections = values
        equalScaffoldBudgets = false
        numDesigns = values.reduce(0) { $0 + $1.trajectories }
    }

    func forScaffold(_ scaffold: NanobodyScaffoldAllocation) -> DesignRequest {
        var child = self
        child.scaffoldSelections = nil
        child.equalScaffoldBudgets = true
        child.scaffoldID = scaffold.id
        child.scaffoldSequence = scaffold.sequence
        child.numDesigns = scaffold.trajectories
        return child
    }

    /// Engine-major order keeps each engine's scaffold campaigns adjacent.
    var campaignRequests: [(label: String, request: DesignRequest)] {
        selectedDesignEngines.flatMap { engine in
            let child = forDesignEngine(engine)
            if designType == .nanobody {
                return allocatedScaffolds.map { (label: "\(engine.label) · \($0.name)", request: child.forScaffold($0)) }
            }
            return [(label: engine.label, request: child)]
        }
    }
    var cdrs = CDRSelection()

    // De-novo (mini-binder / peptide) length range
    var binderMinLen: Int = 60
    var binderMaxLen: Int = 120
    /// Legacy fields are retained to identify saved experimental configurations.
    /// The only active control is initialization-only `helixKill`, which
    /// retains its saved-project key as the anti-helix strength.
    var secondaryStructureBias: SecondaryStructureBias = .none
    var secondaryStructureBiasScope: SecondaryStructureBiasScope = .seedOnly
    var helixKill: Double = 0
    var betaBiasStrength: Double = 0.5
    var betaPatternStrength: Double = 0.5
    var turnLocalizationStrength: Double = 0.5

    // Target
    var targetKind: TargetKind = .protein
    var targetName: String = "target"
    var targetSequence: String = ""            // when targetKind == .protein
    var targetSmiles: String = ""              // when targetKind == .ligand
    /// Project-owned PDB/mmCIF used to condition target chains during design.
    /// The launch controller copies it into the immutable campaign before use.
    var targetTemplatePath: String = ""
    /// Ordinary template conditioning is the released path. The retained
    /// strong enum value only decodes older saved forms and is rejected after
    /// reproducible Apple-GPU geometry failures.
    var targetTemplateMode: TargetTemplateMode = .guide
    var targetTemplateThreshold: Double = 2.0
    /// Optional epitope residues on a protein target, e.g. "B55 B57" (or "55 57").
    var epitopeResidues: String = ""

    // --- Small-molecule targeting ---
    /// Ligand atoms the binder should form a pocket around, in Boltz's own
    /// naming. These go into a Boltz `pocket` constraint.
    ///
    /// The names are not SMILES indices and are not stable: Boltz derives them
    /// from the canonical ranking, and enabling the affinity head standardises
    /// the SMILES first, which renumbers everything. The same linker atoms are
    /// O17/C24/N44 without affinity and O19/C26/N46 with it. They are therefore
    /// regenerated whenever the SMILES or the affinity setting changes, never
    /// carried across.
    var ligandContactAtoms: [String] = []
    /// Angstroms for the pocket constraint.
    var ligandContactDistance: Double = 6.0
    /// Expose the restraint to Boltz's steering potential. Requires
    /// `--boltz-use-potentials` to actually steer, which is passed with it.
    var ligandContactForce: Bool = true
    /// Turn on Boltz's affinity head to get P(bind) for the ligand.
    var ligandAffinityHead: Bool = true
    /// Core-side atom of the explicitly directed core-to-linker bond.
    var ligandAttachmentAtom: Int?
    /// Linker-side atom directly bonded to `ligandAttachmentAtom`.
    var ligandAttachmentLinkerAtom: Int?
    /// Persisted intent, so a run cannot start while the two-click bond choice
    /// is only half complete.
    var ligandIsConjugated: Bool = false
    /// SMILES and affinity setting the current atom names were generated for.
    /// A mismatch means they must be regenerated before use.
    var ligandAtomsGeneratedFor: String = ""

    var designer: SequenceDesigner = .antifold
    var numDesigns: Int = 12
    var numCycles: Int = 5
    /// Defines a campaign hit and, when enabled, the gate for final-cycle
    /// orthogonal checking. Both CLI thresholds must receive the same value.
    var hitThreshold: Double = 0.70
    var parallelMode: ParallelMode = .auto
    var manualParallel: Int = 2

    /// Structure predictor that drives the design loop. Boltz-2 is 3.4x cheaper
    /// per proposal than the slowest alternative and needs only one process.
    var designPredictor: Predictor = .boltz
    /// nil preserves historical single-engine requests; an empty checklist is invalid.
    var designPredictors: [Predictor]? = nil

    /// Explicit checkpoint choices. nil reads the previous backend/model fields.
    var designEngines: [DesignEngine]? = nil

    var selectedDesignEngines: [DesignEngine] {
        let stored = designEngines ?? (designPredictors ?? [designPredictor]).map {
            DesignEngine(predictor: $0, model: intellifoldModel)
        }
        return stored.reduce(into: []) { result, engine in
            if !result.contains(engine) { result.append(engine) }
        }
    }
    /// Backend union for independent-check eligibility and shared settings.
    var selectedDesignPredictors: [Predictor] {
        selectedDesignEngines.map(\.predictor).reduce(into: []) {
            if !$0.contains($1) { $0.append($1) }
        }
    }
    var designEngineSummary: String { selectedDesignEngines.map(\.label).joined(separator: ", ") }
    var totalTrajectories: Int {
        if designType == .nanobody && allocatedScaffolds.isEmpty { return 0 }
        return max(0, numDesigns) * selectedDesignEngines.count
    }

    /// Every engine receives the same user settings and its own explicit checkpoint.
    func forDesignEngine(_ engine: DesignEngine) -> DesignRequest {
        var child = self
        child.designEngines = nil
        child.designPredictors = nil
        child.designPredictor = engine.predictor
        if let model = engine.model { child.intellifoldModel = model }
        return child
    }

    /// Compatibility for callers that still specify a backend plus shared model.
    func forDesignEngine(_ predictor: Predictor) -> DesignRequest {
        forDesignEngine(DesignEngine(predictor: predictor, model: intellifoldModel))
    }

    mutating func setDesignEngine(_ engine: DesignEngine, selected: Bool) {
        var engines = selectedDesignEngines.filter { $0 != engine }
        if selected { engines.append(engine) }
        designEngines = DesignEngine.choices.filter { engines.contains($0) }
            + engines.filter { !DesignEngine.choices.contains($0) }
        if let first = designEngines?.first { designPredictor = first.predictor }
        reconcilePredictors()
    }

    var usesFullIntelliFold: Bool {
        selectedDesignEngines.contains(.intellifoldFull)
            || (intellifoldModel == .v2 && effectivePostPredictors.contains(.intellifold))
    }
    /// Orthogonal predictors that re-fold final designs after the loop. This is the
    /// number that should drive selection: the design predictor's own iPTM is
    /// self-scored, because the loop optimises against it.
    var postPredictors: [Predictor] = [.intellifold]
    /// Architecture for independent IntelliFold checks. Individual campaign
    /// records also use this field for their runner's explicit --model flag.
    /// Older workspaces used it for design as well; nil retains v2-flash.
    var intellifoldModel: IntelliFoldModel? = .v2flash
    /// Only hits at or above `hitThreshold` are post-predicted, which is what
    /// keeps an orthogonal check affordable.
    var postOnlyHits: Bool = true
    /// Whether independent predictors see only the completed design or every
    /// optimized checkpoint (cycles 01...N). The unoptimized cycle 00 seed is
    /// never included by Studio. Threshold gating is intentionally orthogonal.
    var postCheckScope: PostCheckScope = .finalCycle
    /// Also fold each independently checked binder without its target. This is
    /// required for a direct preorganisation check rather than inferring
    /// monomer stability from a complex prediction.
    var postRunBinderAlone: Bool = true
    /// Saved, tunable verdict thresholds. The post-predictor remains the score
    /// source; the design engine's self-score is never substituted here.
    var postFilters = RFD3HitFilters()
    var nesso = LigandNessoOptions()
    /// GUI campaigns always use the measured engine-specific scheduler policy.
    /// The stored field remains solely so older project JSON continues to
    /// decode; decoding migrates historical Compatibility values to Optimized.
    /// Per-trajectory troubleshooting remains an explicit CLI-only option.
    var speedMode: SpeedMode = .batched

    /// Sampling temperature for the first redesign cycle, and for later ones.
    /// Cycle 1 starts hotter to explore, then cools to refine. These are the
    /// pipeline's own defaults; they apply to AntiFold and the MPNN designers
    /// alike, because the runner aliases both onto the same pair of flags.
    var mpnnTempCycle1: Double = 0.30
    var mpnnTempLater: Double = 0.10
    /// LASErMPNN decodes sequence and side-chain rotamers together, so it has a
    /// second temperature for the binding site specifically.
    var lasermpnnSeqTemp: Double = 0.10
    var lasermpnnFirstShellTemp: Double = 1.00
    /// Reuse completed cycles when a campaign is restarted. Idempotent, and safe
    /// on a fresh run name.
    var resumeIfPossible: Bool = true

    /// Designers valid for the current design + target combination.
    /// LigandMPNN and LASErMPNN are ligand-aware and have nothing to work with
    /// against a protein target, so they are not offered there. Conversely both
    /// are offered for a small molecule, since they make different trade-offs.
    var allowedDesigners: [SequenceDesigner] {
        switch designType {
        case .nanobody:
            return [.antifold, .abmpnn]
        case .minibinder, .peptide:
            return targetKind == .ligand ? [.ligandmpnn, .lasermpnn] : [.proteinmpnn, .solublempnn]
        }
    }

    var preferredDesigner: SequenceDesigner {
        switch designType {
        case .nanobody:
            return .antifold
        case .minibinder, .peptide:
            return targetKind == .ligand ? .ligandmpnn : .solublempnn
        }
    }

    /// `--workflow` value. Nanobody workflow keeps the fixed-scaffold CDR
    /// machinery; protein workflow is what de-novo binders and every
    /// ligand-aware designer require.
    var workflow: String { designType == .nanobody ? "nanobody" : "protein" }

    var hasProteinTarget: Bool { targetKind == .protein }

    var targetChainResult: Result<[ProteinChainInput], ProteinSequenceInputError> {
        ProteinSequenceInput.parse(targetSequence, startingAt: 1, minimumLength: 5)
    }

    var targetChains: [ProteinChainInput] {
        guard case .success(let chains) = targetChainResult else { return [] }
        return chains
    }

    var targetChainIDs: [String] { targetChains.map(\.id) }

    var targetSequenceError: String? {
        guard targetKind == .protein, case .failure(let error) = targetChainResult else { return nil }
        return error.message
    }

    var usesBoltzDesignEngine: Bool { designPredictor.runnerValue == Predictor.boltz.runnerValue }

    var hasTargetTemplate: Bool {
        targetKind == .protein
            && !targetTemplatePath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var targetTemplateCompatibilityError: String? {
        guard hasTargetTemplate else { return nil }
        let ext = URL(fileURLWithPath: targetTemplatePath).pathExtension.lowercased()
        guard ["pdb", "cif", "mmcif"].contains(ext) else {
            return "The target template must be a PDB, CIF, or mmCIF file."
        }
        guard FileManager.default.fileExists(atPath: targetTemplatePath) else {
            return "The saved target template is missing. Choose the file again."
        }
        if targetTemplateMode == .strong {
            return "Strong target-coordinate restraint is unavailable: acceptance testing on Apple GPU produced broken target geometry. Remove and reselect the template to use Guide mode."
        } else if !(usesBoltzDesignEngine || designPredictor == .protenixV2
                    || designPredictor == .intellifold) {
            return "Target-fold guidance is supported by Boltz-2, Protenix v2, and IntelliFold v2 Flash/full."
        }
        return nil
    }

    /// Both Boltz and the dedicated Protenix Constraint checkpoint can guide a
    /// design toward selected target residues, albeit with different trained
    /// restraint mechanisms.
    var supportsEpitopePocket: Bool { designPredictor.supportsEpitopePocket }

    /// Canonical post-check list: checks never use steering potentials, never
    /// repeat the design engine, and never run one backend twice.
    var effectivePostPredictors: [Predictor] {
        var seen = Set<String>()
        return postPredictors.compactMap { raw in
            let predictor = raw.checkingVariant
            guard predictor.isAvailable, predictor.canPostCheck,
                  selectedDesignPredictors.contains(where: { $0.independenceIdentity != predictor.independenceIdentity }),
                  seen.insert(predictor.independenceIdentity).inserted else { return nil }
            return predictor
        }
    }

    var usesIntelliFold: Bool {
        (selectedDesignPredictors + effectivePostPredictors).contains { $0 == .intellifold }
    }

    var usesBoltzAnywhere: Bool {
        selectedDesignPredictors.contains { $0.runnerValue == Predictor.boltz.runnerValue } || effectivePostPredictors.contains { $0.runnerValue == Predictor.boltz.runnerValue }
    }

    var epitopeTokenResult: (tokens: [String], invalid: [String]) {
        TemplateWriter.residueTokenResult(epitopeResidues,
                                          allowedTargetChains: targetChainIDs)
    }

    var hasEnteredEpitopeResidues: Bool {
        targetKind == .protein && !epitopeResidues.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    /// Hotspots are retained when the user tries another design engine, and
    /// become active only for a driver with an explicit epitope capability.
    var hasEpitopeSteering: Bool {
        hasEnteredEpitopeResidues && supportsEpitopePocket
    }

    var hasInvalidEpitopeResidues: Bool {
        hasEpitopeSteering && !epitopeTokenResult.invalid.isEmpty
    }

    /// Generic protein hotspot restraints and atom-specific ligand pockets are
    /// design-time Boltz features. Other engines may still see the target, but
    /// cannot honour these requested restraints.
    var hasIncompatibleTargeting: Bool {
        (targetKind == .ligand && designPredictor == .protenixConstraint)
            || (targetKind == .ligand && !ligandContactAtoms.isEmpty && !usesBoltzDesignEngine)
            || targetTemplateCompatibilityError != nil
    }

    /// Key the ligand atom names were generated under. Changing either half
    /// renumbers the atoms, so the names must be regenerated.
    var ligandAtomKey: String {
        "\(targetSmiles.trimmingCharacters(in: .whitespaces))|\(ligandAffinityHead ? 1 : 0)"
    }
    /// True when the stored atom names no longer correspond to the current
    /// SMILES and affinity setting — the UI must not let a run start like this.
    var ligandAtomsStale: Bool {
        targetKind == .ligand && !ligandContactAtoms.isEmpty
            && ligandAtomsGeneratedFor != ligandAtomKey
    }

    /// Every backend this run needs installed before it can start.
    var requiredComponents: [InstallComponent] {
        if designEngines != nil || designPredictors != nil {
            return selectedDesignEngines.flatMap { forDesignEngine($0).requiredComponents }
                .reduce(into: []) { if !$0.contains($1) { $0.append($1) } }
        }
        var set: [InstallComponent] = [designPredictor.component]
        for p in effectivePostPredictors where !set.contains(p.component) { set.append(p.component) }
        if usesIntelliFold && intellifoldModel == .v2 { set.append(.intellifoldFull) }
        if !set.contains(designer.component) { set.append(designer.component) }
        if targetKind == .ligand {
            for component in nesso.requiredComponents where !set.contains(component) { set.append(component) }
        }
        return set
    }

    /// Rough wall-clock estimate in seconds. The per-prediction figures are
    /// already the best measured schedule, so they are not divided by a process
    /// count again — doing that was double-counting the concurrency and made the
    /// estimate several times too optimistic. It includes every possible final
    /// post-check, but excludes MSA generation and inverse folding; the UI names
    /// both qualifications instead of presenting it as a strict bound.
    var estimatedPredictionSeconds: Double {
        if designEngines != nil || designPredictors != nil {
            return selectedDesignEngines.reduce(0) { $0 + forDesignEngine($1).estimatedPredictionSeconds }
        }
        // The runner predicts cycle_00 before the requested optimisation
        // cycles, so five optimisation cycles means six folds per design.
        let cyclesIncludingSeed = max(0, numCycles) + 1
        let designPredictions = Double(max(1, numDesigns) * cyclesIncludingSeed)
        var total = designPredictions * designPredictor.measuredSeconds(in: .batched)
        // Use every eligible checkpoint so threshold gating can only make the
        // real run shorter.
        let checkedCycles = postCheckScope == .allCycles ? max(1, numCycles) : 1
        let postCandidates = Double(max(1, numDesigns) * checkedCycles)
        for p in effectivePostPredictors {
            total += postCandidates * p.measuredSeconds(in: .batched)
            if postRunBinderAlone {
                total += postCandidates * p.measuredSeconds(in: .batched)
            }
        }
        return total
    }

    /// One independent trajectory yields one optimized structure per design
    /// cycle. Cycle 00 is a starting structure and is never counted as a design.
    var expectedOptimizedDesigns: Int {
        totalTrajectories * max(0, numCycles)
    }

    var expectedStartingStructures: Int { totalTrajectories }

    var secondaryStructureControlsValid: Bool {
        [helixKill]
            .allSatisfy { (0.0...1.0).contains($0) }
    }

    var secondaryStructureCompatibilityError: String? {
        if secondaryStructureBias == .beta || secondaryStructureBias == .mixed ||
            (secondaryStructureBias != .none && secondaryStructureBiasScope == .seedAndCycles) {
            return "This saved configuration uses retired secondary-structure controls. Choose initialization-only helix kill to continue."
        }
        return nil
    }

    var validationIssues: [DesignValidationIssue] {
        if designEngines != nil || designPredictors != nil {
            guard !selectedDesignPredictors.isEmpty else {
                return [.init(field: "models", message: "Select at least one design engine.")]
            }
            return selectedDesignEngines.flatMap { engine in
                forDesignEngine(engine).validationIssues.map {
                    DesignValidationIssue(field: $0.field, message: "\(engine.label): \($0.message)")
                }
            }
        }
        var issues: [DesignValidationIssue] = []
        func add(_ field: String, _ message: String) { issues.append(.init(field: field, message: message)) }
        if targetKind == .protein, let error = targetSequenceError { add("target", error) }
        if targetKind == .ligand && targetSmiles.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            add("target", "Add a ligand SMILES to continue.")
        }
        if targetKind == .ligand, let error = nesso.validationError { add("nesso", error) }
        if numDesigns < 1 || numCycles < 1 { add("run", "Choose at least one trajectory per engine and one optimization cycle.") }
        if !designPredictor.isAvailable { add("models", "\(designPredictor.label) is retired after failing Apple-GPU quality control. Choose a supported design engine.") }
        if hasInvalidEpitopeResidues { add("target", "Fix the hotspot residue list before starting.") }
        if hasIncompatibleTargeting {
            add("target", targetTemplateCompatibilityError ?? "The selected targeting restraint is incompatible with this engine. Review the target and model settings.")
        }
        if targetKind == .ligand && ligandIsConjugated && (ligandAttachmentAtom == nil || ligandAttachmentLinkerAtom == nil) {
            add("target", "Choose both ends of the core-to-linker bond, or mark the molecule as free.")
        }
        if ligandAtomsStale { add("target", "Reload the ligand atoms; the saved names were generated for different settings.") }
        if designType == .nanobody {
            let allocations = allocatedScaffolds
            if allocations.isEmpty { add("binder", "Select at least one nanobody scaffold.") }
            if Set(allocations.map(\.id)).count != allocations.count { add("binder", "Each scaffold may be selected only once.") }
            if allocations.contains(where: { $0.id.isEmpty || $0.sequence.isEmpty || !Set($0.sequence).isSubset(of: Set("ACDEFGHIKLMNPQRSTVWY")) }) {
                add("binder", "Every selected scaffold needs its saved amino-acid sequence.")
            }
            if allocations.contains(where: { $0.trajectories < 1 || $0.trajectories > 10_000 }) || allocations.reduce(0, { $0 + $1.trajectories }) != numDesigns {
                add("binder", "Allocate at least one trajectory to every selected scaffold; allocations must match the total.")
            }
            if cdrs.isEmpty { add("binder", "Select at least one CDR to design.") }
        } else {
            if binderMinLen < 1 || binderMaxLen < binderMinLen { add("binder", "Set a positive binder length with the maximum at least as large as the minimum.") }
            if !secondaryStructureControlsValid { add("binder", "Secondary-structure strengths must be between 0 and 100%.") }
            if let error = secondaryStructureCompatibilityError { add("binder", error) }
        }
        return issues
    }

    var isRunnable: Bool { validationIssues.isEmpty }

    /// Clamp the designer to a valid choice for the current type/target.
    mutating func reconcileDesigner() {
        if !allowedDesigners.contains(designer) { designer = preferredDesigner }
    }

    /// Remove duplicate/self-checking engines. Protein hotspot selections stay
    /// saved but dormant under non-Boltz drivers; atom-specific ligand pockets
    /// remain a hard Boltz requirement because they define the ligand campaign.
    mutating func reconcilePredictors() {
        if designEngines != nil || designPredictors != nil {
            // Keep selected checkers even when the checklist is temporarily empty.
            if !selectedDesignPredictors.isEmpty { postPredictors = effectivePostPredictors }
            return
        }
        if targetKind == .ligand && !ligandContactAtoms.isEmpty && !usesBoltzDesignEngine {
            let previousDesign = designPredictor.checkingVariant
            designPredictor = ligandContactForce ? .boltzPotentials : .boltz
            if previousDesign.runnerValue != Predictor.boltz.runnerValue {
                postPredictors.append(previousDesign)
            }
        }
        postPredictors = effectivePostPredictors
    }

    /// Change the design engine without accidentally losing independent
    /// validation. The former driver becomes a checker when it is a different
    /// backend; a Boltz/potentials variant change remains the same backend.
    mutating func selectDesignPredictor(_ newPredictor: Predictor) {
        designEngines = nil
        designPredictors = nil
        let previous = designPredictor.checkingVariant
        designPredictor = newPredictor
        if previous.canPostCheck && previous.independenceIdentity != newPredictor.independenceIdentity {
            postPredictors.append(previous)
        }
        reconcilePredictors()
    }

    /// Reconcile only active controls when target kind changes. Alternate input
    /// is retained so an accidental picker change does not erase user work;
    mutating func reconcileTargetKind() {
        if targetKind == .protein {
            ligandIsConjugated = false
            ligandAttachmentAtom = nil
            ligandAttachmentLinkerAtom = nil
        }
        reconcileDesigner()
        reconcilePredictors()
    }

    /// Apply sensible defaults when switching design type.
    mutating func applyTypeDefaults() {
        let r = designType.defaultLengthRange
        binderMinLen = r.lowerBound
        binderMaxLen = r.upperBound
        reconcileDesigner()
        reconcilePredictors()
    }

    init() {}

    private enum CodingKeys: String, CodingKey {
        case designType, scaffoldID, scaffoldSequence, scaffoldSelections, equalScaffoldBudgets, cdrs, binderMinLen, binderMaxLen, helixKill
        case secondaryStructureBias, secondaryStructureBiasScope
        case betaBiasStrength, betaPatternStrength, turnLocalizationStrength
        case targetKind, targetName, targetSequence, targetSmiles, epitopeResidues
        case targetTemplatePath, targetTemplateMode, targetTemplateThreshold
        case designer, numDesigns, numCycles, hitThreshold, parallelMode, manualParallel
        case designPredictor, designPredictors, designEngines, postPredictors, intellifoldModel, postOnlyHits, postCheckScope
        case postRunBinderAlone, postFilters, nesso
        case speedMode, resumeIfPossible
        case mpnnTempCycle1, mpnnTempLater, lasermpnnSeqTemp, lasermpnnFirstShellTemp
        case ligandContactAtoms, ligandContactDistance, ligandContactForce
        case ligandAffinityHead, ligandIsConjugated, ligandAttachmentAtom
        case ligandAttachmentLinkerAtom, ligandAtomsGeneratedFor
    }

    /// Resilient decoding: every field defaults if absent, so adding new fields
    /// in future versions never breaks loading older saved projects.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let d = DesignRequest()
        nesso = try c.decodeIfPresent(LigandNessoOptions.self, forKey: .nesso) ?? d.nesso
        designType      = try c.decodeIfPresent(DesignType.self, forKey: .designType) ?? d.designType
        scaffoldID      = try c.decodeIfPresent(String.self, forKey: .scaffoldID) ?? d.scaffoldID
        scaffoldSequence = try c.decodeIfPresent(String.self, forKey: .scaffoldSequence) ?? d.scaffoldSequence
        scaffoldSelections = try c.decodeIfPresent([NanobodyScaffoldAllocation].self, forKey: .scaffoldSelections)
        equalScaffoldBudgets = try c.decodeIfPresent(Bool.self, forKey: .equalScaffoldBudgets) ?? true
        cdrs            = try c.decodeIfPresent(CDRSelection.self, forKey: .cdrs) ?? d.cdrs
        binderMinLen    = try c.decodeIfPresent(Int.self, forKey: .binderMinLen) ?? d.binderMinLen
        binderMaxLen    = try c.decodeIfPresent(Int.self, forKey: .binderMaxLen) ?? d.binderMaxLen
        helixKill       = try c.decodeIfPresent(Double.self, forKey: .helixKill) ?? d.helixKill
        secondaryStructureBias = try c.decodeIfPresent(SecondaryStructureBias.self,
                                                        forKey: .secondaryStructureBias)
            ?? (helixKill > 0.01 ? .antihelix : d.secondaryStructureBias)
        secondaryStructureBiasScope = try c.decodeIfPresent(SecondaryStructureBiasScope.self,
                                                             forKey: .secondaryStructureBiasScope)
            ?? d.secondaryStructureBiasScope
        betaBiasStrength = try c.decodeIfPresent(Double.self, forKey: .betaBiasStrength) ?? d.betaBiasStrength
        betaPatternStrength = try c.decodeIfPresent(Double.self, forKey: .betaPatternStrength) ?? d.betaPatternStrength
        turnLocalizationStrength = try c.decodeIfPresent(Double.self, forKey: .turnLocalizationStrength) ?? d.turnLocalizationStrength
        targetKind      = try c.decodeIfPresent(TargetKind.self, forKey: .targetKind) ?? d.targetKind
        targetName      = try c.decodeIfPresent(String.self, forKey: .targetName) ?? d.targetName
        targetSequence  = try c.decodeIfPresent(String.self, forKey: .targetSequence) ?? d.targetSequence
        targetSmiles    = try c.decodeIfPresent(String.self, forKey: .targetSmiles) ?? d.targetSmiles
        epitopeResidues = try c.decodeIfPresent(String.self, forKey: .epitopeResidues) ?? d.epitopeResidues
        targetTemplatePath = try c.decodeIfPresent(String.self, forKey: .targetTemplatePath) ?? d.targetTemplatePath
        targetTemplateMode = try c.decodeIfPresent(TargetTemplateMode.self, forKey: .targetTemplateMode) ?? d.targetTemplateMode
        targetTemplateThreshold = try c.decodeIfPresent(Double.self, forKey: .targetTemplateThreshold) ?? d.targetTemplateThreshold
        designer        = try c.decodeIfPresent(SequenceDesigner.self, forKey: .designer) ?? d.designer
        numDesigns      = try c.decodeIfPresent(Int.self, forKey: .numDesigns) ?? d.numDesigns
        numCycles       = try c.decodeIfPresent(Int.self, forKey: .numCycles) ?? d.numCycles
        hitThreshold    = try c.decodeIfPresent(Double.self, forKey: .hitThreshold) ?? d.hitThreshold
        parallelMode    = try c.decodeIfPresent(ParallelMode.self, forKey: .parallelMode) ?? d.parallelMode
        manualParallel  = try c.decodeIfPresent(Int.self, forKey: .manualParallel) ?? d.manualParallel
        designPredictor = try c.decodeIfPresent(Predictor.self, forKey: .designPredictor) ?? d.designPredictor
        designPredictors = try c.decodeIfPresent([Predictor].self, forKey: .designPredictors)
        designEngines = try c.decodeIfPresent([DesignEngine].self, forKey: .designEngines)
        postPredictors  = try c.decodeIfPresent([Predictor].self, forKey: .postPredictors) ?? d.postPredictors
        intellifoldModel = try c.decodeIfPresent(IntelliFoldModel.self, forKey: .intellifoldModel) ?? d.intellifoldModel
        postOnlyHits    = try c.decodeIfPresent(Bool.self, forKey: .postOnlyHits) ?? d.postOnlyHits
        postCheckScope  = try c.decodeIfPresent(PostCheckScope.self, forKey: .postCheckScope) ?? d.postCheckScope
        postRunBinderAlone = try c.decodeIfPresent(Bool.self, forKey: .postRunBinderAlone) ?? d.postRunBinderAlone
        postFilters     = try c.decodeIfPresent(RFD3HitFilters.self, forKey: .postFilters) ?? d.postFilters
        // Compatibility scheduling was once exposed in Advanced. It made an
        // old saved form silently bypass the validated resident default. Read
        // the legacy value so malformed data still fails decoding, then migrate
        // every GUI project to the automatic optimized policy.
        _ = try c.decodeIfPresent(SpeedMode.self, forKey: .speedMode)
        speedMode       = .batched
        resumeIfPossible = try c.decodeIfPresent(Bool.self, forKey: .resumeIfPossible) ?? d.resumeIfPossible
        mpnnTempCycle1  = try c.decodeIfPresent(Double.self, forKey: .mpnnTempCycle1) ?? d.mpnnTempCycle1
        mpnnTempLater   = try c.decodeIfPresent(Double.self, forKey: .mpnnTempLater) ?? d.mpnnTempLater
        lasermpnnSeqTemp = try c.decodeIfPresent(Double.self, forKey: .lasermpnnSeqTemp) ?? d.lasermpnnSeqTemp
        lasermpnnFirstShellTemp = try c.decodeIfPresent(Double.self, forKey: .lasermpnnFirstShellTemp) ?? d.lasermpnnFirstShellTemp
        ligandContactAtoms   = try c.decodeIfPresent([String].self, forKey: .ligandContactAtoms) ?? d.ligandContactAtoms
        ligandContactDistance = try c.decodeIfPresent(Double.self, forKey: .ligandContactDistance) ?? d.ligandContactDistance
        ligandContactForce   = try c.decodeIfPresent(Bool.self, forKey: .ligandContactForce) ?? d.ligandContactForce
        ligandAffinityHead   = try c.decodeIfPresent(Bool.self, forKey: .ligandAffinityHead) ?? d.ligandAffinityHead
        ligandAttachmentAtom = try c.decodeIfPresent(Int.self, forKey: .ligandAttachmentAtom) ?? d.ligandAttachmentAtom
        ligandAttachmentLinkerAtom = try c.decodeIfPresent(Int.self, forKey: .ligandAttachmentLinkerAtom) ?? d.ligandAttachmentLinkerAtom
        ligandIsConjugated = try c.decodeIfPresent(Bool.self, forKey: .ligandIsConjugated)
            ?? (ligandAttachmentAtom != nil || ligandAttachmentLinkerAtom != nil)
        ligandAtomsGeneratedFor = try c.decodeIfPresent(String.self, forKey: .ligandAtomsGeneratedFor) ?? d.ligandAtomsGeneratedFor
        reconcileDesigner()
        reconcilePredictors()
    }
}

/// A validation reason and the form section that can resolve it.
struct DesignValidationIssue: Identifiable, Equatable {
    let field: String
    let message: String
    var id: String { field + "|" + message }
}
