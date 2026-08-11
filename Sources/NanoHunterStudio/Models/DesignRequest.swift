import Foundation

/// Inverse-folding backend used for sequence redesign.
enum SequenceDesigner: String, CaseIterable, Codable, Identifiable {
    case antifold, abmpnn, proteinmpnn, solublempnn, ligandmpnn

    var id: String { rawValue }

    var label: String {
        switch self {
        case .antifold:    return "AntiFold"
        case .abmpnn:       return "AbMPNN"
        case .proteinmpnn:  return "ProteinMPNN"
        case .solublempnn:  return "SolubleMPNN"
        case .ligandmpnn:   return "LigandMPNN"
        }
    }

    /// One-line, novice-friendly description.
    var blurb: String {
        switch self {
        case .antifold:    return "Antibody-aware. Best default for nanobody CDR design."
        case .abmpnn:       return "Antibody-fine-tuned ProteinMPNN. Great for CDR redesign."
        case .proteinmpnn:  return "General-purpose protein sequence design."
        case .solublempnn:  return "Tuned for soluble proteins."
        case .ligandmpnn:   return "Ligand/small-molecule-aware design."
        }
    }
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

    var designer: SequenceDesigner = .antifold
    var numDesigns: Int = 12
    var numCycles: Int = 5
    var hitThreshold: Double = 0.70
    var parallelMode: ParallelMode = .auto
    var manualParallel: Int = 2

    /// Designers valid for the current design + target combination.
    var allowedDesigners: [SequenceDesigner] {
        switch designType {
        case .nanobody:
            return [.antifold, .abmpnn]
        case .minibinder, .peptide:
            return targetKind == .ligand ? [.ligandmpnn] : [.proteinmpnn, .solublempnn, .ligandmpnn]
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

    var hasProteinTarget: Bool { targetKind == .protein }

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
    }
}
