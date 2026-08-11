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

/// Everything the user specifies for a design campaign.
struct DesignRequest: Codable, Equatable, Hashable {
    var designType: DesignType = .nanobody

    // Nanobody (scaffold) fields
    var scaffoldID: String = "7xl0_vobarilizumab"
    var scaffoldSequence: String = ""
    var cdrs = CDRSelection()

    // De-novo (mini-binder / peptide) length range
    var binderMinLen: Int = 60
    var binderMaxLen: Int = 120
    /// Helix-kill strength for de-novo binders (0 = off, 1 = max). Biases the
    /// cycle-0 seed away from helix-prone residues. Ignored for nanobodies.
    var helixKill: Double = 0

    // Target
    var targetKind: TargetKind = .protein
    var targetName: String = "target"
    var targetSequence: String = ""            // when targetKind == .protein
    var targetSmiles: String = ""              // when targetKind == .ligand
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
    /// Atom the linker leaves from, for the core/linker split.
    var ligandAttachmentAtom: Int?
    /// SMILES and affinity setting the current atom names were generated for.
    /// A mismatch means they must be regenerated before use.
    var ligandAtomsGeneratedFor: String = ""

    var designer: SequenceDesigner = .antifold
    var numDesigns: Int = 12
    var numCycles: Int = 5
    var hitThreshold: Double = 0.70
    var parallelMode: ParallelMode = .auto
    var manualParallel: Int = 2

    /// Structure predictor that drives the design loop. Boltz-2 is 3.4x cheaper
    /// per proposal than the slowest alternative and needs only one process.
    var designPredictor: Predictor = .boltz
    /// Orthogonal predictors that re-fold hits after the design loop. This is the
    /// number that should drive selection: the design predictor's own iPTM is
    /// self-scored, because the loop optimises against it.
    var postPredictors: [Predictor] = [.intellifold]
    /// Only hits at or above `hitThreshold` are post-predicted, which is what
    /// keeps an orthogonal check affordable.
    var postOnlyHits: Bool = true
    var speedMode: SpeedMode = .standard

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
        var set: [InstallComponent] = [designPredictor.component]
        for p in postPredictors where !set.contains(p.component) { set.append(p.component) }
        if !set.contains(designer.component) { set.append(designer.component) }
        return set
    }

    /// Rough wall-clock estimate in seconds. The per-prediction figures are
    /// already the best measured schedule, so they are not divided by a process
    /// count again — doing that was double-counting the concurrency and made the
    /// estimate several times too optimistic. Still ignores MSA generation and
    /// inverse folding, so the UI presents it as "at least".
    var estimatedSecondsLowerBound: Double {
        let designPredictions = Double(max(1, numDesigns) * max(1, numCycles))
        var total = designPredictions * designPredictor.measuredSeconds(in: speedMode)
        // Post-prediction touches only the final cycle, and only hits when gated.
        let postCandidates = Double(max(1, numDesigns)) * (postOnlyHits ? 0.35 : 1.0)
        for p in postPredictors {
            total += postCandidates * p.measuredSeconds(in: speedMode)
        }
        return total
    }

    var isRunnable: Bool {
        let targetOK = targetKind == .protein ? !targetSequence.isEmpty : !targetSmiles.isEmpty
        guard targetOK else { return false }
        switch designType {
        case .nanobody:
            return !scaffoldSequence.isEmpty && !cdrs.isEmpty
        case .minibinder, .peptide:
            return binderMinLen >= 1 && binderMaxLen >= binderMinLen
        }
    }

    /// Clamp the designer to a valid choice for the current type/target.
    mutating func reconcileDesigner() {
        if !allowedDesigners.contains(designer) { designer = preferredDesigner }
    }

    /// Apply sensible defaults when switching design type.
    mutating func applyTypeDefaults() {
        let r = designType.defaultLengthRange
        binderMinLen = r.lowerBound
        binderMaxLen = r.upperBound
        reconcileDesigner()
    }

    init() {}

    private enum CodingKeys: String, CodingKey {
        case designType, scaffoldID, scaffoldSequence, cdrs, binderMinLen, binderMaxLen, helixKill
        case targetKind, targetName, targetSequence, targetSmiles, epitopeResidues
        case designer, numDesigns, numCycles, hitThreshold, parallelMode, manualParallel
        case designPredictor, postPredictors, postOnlyHits, speedMode, resumeIfPossible
        case mpnnTempCycle1, mpnnTempLater, lasermpnnSeqTemp, lasermpnnFirstShellTemp
        case ligandContactAtoms, ligandContactDistance, ligandContactForce
        case ligandAffinityHead, ligandAttachmentAtom, ligandAtomsGeneratedFor
    }

    /// Resilient decoding: every field defaults if absent, so adding new fields
    /// in future versions never breaks loading older saved projects.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let d = DesignRequest()
        designType      = try c.decodeIfPresent(DesignType.self, forKey: .designType) ?? d.designType
        scaffoldID      = try c.decodeIfPresent(String.self, forKey: .scaffoldID) ?? d.scaffoldID
        scaffoldSequence = try c.decodeIfPresent(String.self, forKey: .scaffoldSequence) ?? d.scaffoldSequence
        cdrs            = try c.decodeIfPresent(CDRSelection.self, forKey: .cdrs) ?? d.cdrs
        binderMinLen    = try c.decodeIfPresent(Int.self, forKey: .binderMinLen) ?? d.binderMinLen
        binderMaxLen    = try c.decodeIfPresent(Int.self, forKey: .binderMaxLen) ?? d.binderMaxLen
        helixKill       = try c.decodeIfPresent(Double.self, forKey: .helixKill) ?? d.helixKill
        targetKind      = try c.decodeIfPresent(TargetKind.self, forKey: .targetKind) ?? d.targetKind
        targetName      = try c.decodeIfPresent(String.self, forKey: .targetName) ?? d.targetName
        targetSequence  = try c.decodeIfPresent(String.self, forKey: .targetSequence) ?? d.targetSequence
        targetSmiles    = try c.decodeIfPresent(String.self, forKey: .targetSmiles) ?? d.targetSmiles
        epitopeResidues = try c.decodeIfPresent(String.self, forKey: .epitopeResidues) ?? d.epitopeResidues
        designer        = try c.decodeIfPresent(SequenceDesigner.self, forKey: .designer) ?? d.designer
        numDesigns      = try c.decodeIfPresent(Int.self, forKey: .numDesigns) ?? d.numDesigns
        numCycles       = try c.decodeIfPresent(Int.self, forKey: .numCycles) ?? d.numCycles
        hitThreshold    = try c.decodeIfPresent(Double.self, forKey: .hitThreshold) ?? d.hitThreshold
        parallelMode    = try c.decodeIfPresent(ParallelMode.self, forKey: .parallelMode) ?? d.parallelMode
        manualParallel  = try c.decodeIfPresent(Int.self, forKey: .manualParallel) ?? d.manualParallel
        designPredictor = try c.decodeIfPresent(Predictor.self, forKey: .designPredictor) ?? d.designPredictor
        postPredictors  = try c.decodeIfPresent([Predictor].self, forKey: .postPredictors) ?? d.postPredictors
        postOnlyHits    = try c.decodeIfPresent(Bool.self, forKey: .postOnlyHits) ?? d.postOnlyHits
        speedMode       = try c.decodeIfPresent(SpeedMode.self, forKey: .speedMode) ?? d.speedMode
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
        ligandAtomsGeneratedFor = try c.decodeIfPresent(String.self, forKey: .ligandAtomsGeneratedFor) ?? d.ligandAtomsGeneratedFor
    }
}
