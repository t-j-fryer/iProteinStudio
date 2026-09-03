import Foundation

/// The three scientifically distinct RFdiffusion3 workflows exposed by Studio.
/// Keeping this explicit prevents a partial-diffusion request from accidentally
/// passing through the de-novo length planner.
enum RFD3DesignMode: String, CaseIterable, Codable, Identifiable, Hashable {
    case deNovo
    case partialDiffusion
    case motifScaffolding

    var id: String { rawValue }
    var label: String {
        switch self {
        case .deNovo: return "De novo design"
        case .partialDiffusion: return "Partial diffusion"
        case .motifScaffolding: return "Motif scaffolding"
        }
    }
    var blurb: String {
        switch self {
        case .deNovo:
            return "Generate a new binder backbone from noise around a protein or small molecule."
        case .partialDiffusion:
            return "Explore nearby backbones from an existing binder–target complex while keeping the target fixed."
        case .motifScaffolding:
            return "Build a new binder around explicitly selected functional atoms from an existing binder–target complex."
        }
    }
}

/// One functional residue supplied to RFD3's unindexed motif mechanism.
/// Atom names are explicit because fixing every atom by default can overconstrain
/// a scaffold and an empty selection is rejected upstream.
struct RFD3MotifSite: Codable, Hashable, Identifiable {
    var residue: String
    var atoms: String
    var id: String { residue.uppercased() }
}

/// Tunable, provenance-preserving gates applied after both complex and
/// binder-alone prediction. Nil disables an individual gate.
struct RFD3HitFilters: Codable, Hashable {
    var minimumIPTM: Double? = 0.50
    var minimumIPSAEMin: Double? = 0.50
    var maximumComplexRMSD: Double? = 2.5
    var minimumBinderPLDDT: Double? = 0.80
    var maximumBinderRMSD: Double? = 2.0
    /// Recovery of the explicitly constrained motif atoms after an independent
    /// complex prediction. Only applied to motif-scaffolding campaigns.
    var maximumMotifRMSD: Double? = 1.0

    init() {}

    private enum CodingKeys: String, CodingKey {
        case minimumIPTM, minimumIPSAEMin, maximumComplexRMSD
        case minimumBinderPLDDT, maximumBinderRMSD, maximumMotifRMSD
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let d = RFD3HitFilters()
        minimumIPTM = try c.decodeIfPresent(Double.self, forKey: .minimumIPTM) ?? d.minimumIPTM
        minimumIPSAEMin = try c.decodeIfPresent(Double.self, forKey: .minimumIPSAEMin) ?? d.minimumIPSAEMin
        maximumComplexRMSD = try c.decodeIfPresent(Double.self, forKey: .maximumComplexRMSD) ?? d.maximumComplexRMSD
        minimumBinderPLDDT = try c.decodeIfPresent(Double.self, forKey: .minimumBinderPLDDT) ?? d.minimumBinderPLDDT
        maximumBinderRMSD = try c.decodeIfPresent(Double.self, forKey: .maximumBinderRMSD) ?? d.maximumBinderRMSD
        maximumMotifRMSD = try c.decodeIfPresent(Double.self, forKey: .maximumMotifRMSD) ?? d.maximumMotifRMSD
    }
}

/// What RFdiffusion3 is designing a binder against.
///
/// Deliberately limited to protein and small-molecule targets. The nucleic-acid
/// model (`rfd3na`) is a separate network with a separate checkpoint that is not
/// obtainable on this machine, and the validated MLX fast path is protein+ligand
/// only — see `lab_book/0001-repository-genesis-and-audit.md` Finding 4. Offering
/// a DNA/RNA option that cannot run would be worse than not offering it.
enum RFD3TargetKind: String, CaseIterable, Codable, Identifiable, Hashable {
    case protein
    case smallMolecule

    var id: String { rawValue }

    var label: String {
        switch self {
        case .protein:       return "Protein"
        case .smallMolecule: return "Small molecule"
        }
    }

    var blurb: String {
        switch self {
        case .protein:
            return "Design a binder against a protein structure. You choose which surface residues to aim at."
        case .smallMolecule:
            return "Design a pocket around a small molecule. You choose which atoms end up buried, exposed, or hydrogen bonded."
        }
    }

    /// Inverse folders that make sense for this target. AbMPNN and AntiFold stay
    /// nanobody-only and never appear here.
    var sequenceModels: [RFD3SequenceModel] {
        switch self {
        case .protein:       return [.solublempnn, .proteinmpnn]
        case .smallMolecule: return [.lasermpnn, .ligandmpnn]
        }
    }
}

/// Inverse-folding model used to put sequences on RFdiffusion3 backbones.
enum RFD3SequenceModel: String, CaseIterable, Codable, Identifiable, Hashable {
    case lasermpnn
    case ligandmpnn
    case solublempnn
    case proteinmpnn

    var id: String { rawValue }

    var label: String {
        switch self {
        case .lasermpnn:   return "LASErMPNN"
        case .ligandmpnn:  return "LigandMPNN"
        case .solublempnn: return "SolubleMPNN"
        case .proteinmpnn: return "ProteinMPNN"
        }
    }

    var blurb: String {
        switch self {
        case .lasermpnn:
            return "Ligand-aware, and places side chains at the same time. Tends to over-pack the pocket less. Runs on the CPU."
        case .ligandmpnn:
            return "Ligand-aware and fast. The established choice for small-molecule binders."
        case .solublempnn:
            return "Tuned for soluble proteins — the usual choice for a de-novo binder."
        case .proteinmpnn:
            return "The general-purpose original. Use it when you want the least opinionated model."
        }
    }

    /// Key written into the campaign config; the orchestrator dispatches on it.
    var configValue: String { rawValue }

    var component: InstallComponent { self == .lasermpnn ? .lasermpnn : .mpnn }

    var runsOnCPU: Bool { self == .lasermpnn }

    /// LASErMPNN's own defaults differ from the MPNN family's, so the UI has to
    /// reset the temperature when the model changes rather than carrying a value
    /// that means something different.
    var defaultTemperature: Double { self == .lasermpnn ? 0.10 : 0.10 }
    var defaultFirstShellTemperature: Double { 1.00 }
}

/// How the user supplied the small molecule.
///
/// RFdiffusion3 has **no native SMILES field** — there is no `smiles` key
/// anywhere in its `DesignInputSpecification`. A SMILES string must therefore be
/// turned into an explicit chemical component before RFD3 can see it. Supplying
/// a generic `LIG` residue instead resolves against a three-atom placeholder CCD
/// component, which fails silently rather than loudly.
enum LigandSource: String, CaseIterable, Codable, Identifiable, Hashable {
    /// SMILES → RDKit conformer → explicit CCD component + chain-L PDB.
    case smiles
    /// User-supplied PDB/CIF; the user names the ligand residue inside it.
    case structureFile

    var id: String { rawValue }

    var label: String {
        switch self {
        case .smiles:         return "Paste SMILES"
        case .structureFile:  return "Use my structure file"
        }
    }

    var blurb: String {
        switch self {
        case .smiles:
            return "Studio generates a 3D conformer and a proper chemical-component definition for it. Best when you have no preferred pose."
        case .structureFile:
            return "Keeps your exact pose, tautomer and protonation state. Best when the ligand came from a crystal structure or a docking run."
        }
    }
}

/// Per-atom conditioning class for a small-molecule target. These map to RFD3's
/// `select_buried` / `select_exposed` / `select_hbond_*` fields.
///
/// One pinned-build pitfall is handled for us by `patch_foundry_rasa.py`:
/// supplying both `select_buried` and `select_exposed` originally caused the
/// later selection to erase the earlier one.
///
/// RFD3 also defines `select_partially_buried`, but the validated spec writer
/// (`RFD3/scripts/prepare_ligand_target.py`) does not accept it, so Studio does
/// not offer it. Adding an option the pipeline would silently drop is worse than
/// not having it.
enum AtomCondition: String, CaseIterable, Codable, Identifiable, Hashable {
    case buried
    case exposed
    case hbondDonor
    case hbondAcceptor
    case hotspot

    var id: String { rawValue }

    var label: String {
        switch self {
        case .buried:        return "Bury"
        case .exposed:       return "Expose"
        case .hbondDonor:    return "Ligand donor"
        case .hbondAcceptor: return "Ligand acceptor"
        case .hotspot:       return "Hotspot"
        }
    }

    var help: String {
        switch self {
        case .buried:        return "RASA condition: ask RFdiffusion3 to pack protein around this atom and reduce its solvent accessibility."
        case .exposed:       return "RASA condition: keep this atom solvent-accessible — appropriate for explicit linkers and conjugation handles."
        case .hbondDonor:    return "This selected ligand atom donates a hydrogen bond; RFdiffusion3 should place a complementary protein acceptor."
        case .hbondAcceptor: return "This selected ligand atom accepts a hydrogen bond; RFdiffusion3 should place a complementary protein donor."
        case .hotspot:       return "Ask the designed protein to contact this atom, typically within 4.5 Å; unlike Bury, this does not require enclosing it."
        }
    }

    /// Key in the ligand spec consumed by `prepare_ligand_target.py`, which
    /// translates these to RFD3's `select_*` fields.
    var specKey: String {
        switch self {
        case .buried:        return "buried"
        case .exposed:       return "exposed"
        case .hbondDonor:    return "hbond_donor"
        case .hbondAcceptor: return "hbond_acceptor"
        case .hotspot:       return "hotspots"
        }
    }

    /// Conditions that make sense for a protein target's residues.
    static var proteinCases: [AtomCondition] { [.hotspot] }
}

/// One ligand geometry the campaign will design against.
struct ConformerChoice: Codable, Hashable, Identifiable {
    var label: String
    var path: String
    var weight: Double
    var id: String { label }
}

/// How the design is positioned relative to the target.
enum OriginStrategy: String, CaseIterable, Codable, Identifiable, Hashable {
    /// Automatically distribute starts over solvent-accessible target patches.
    case surfaceScan
    /// Position near a broad user-selected region without conditioning contacts.
    case surfacePatch
    /// Centre of mass of the target.
    case com
    /// Centred on the selected hotspots — the right choice when aiming at a patch.
    case hotspots
    /// Explicit XYZ.
    case explicit

    var id: String { rawValue }

    var label: String {
        switch self {
        case .surfaceScan:  return "Whole surface"
        case .surfacePatch: return "Broad region"
        case .com:      return "Target centre of mass"
        case .hotspots: return "Exact epitope"
        case .explicit: return "Manual XYZ"
        }
    }

    var blurb: String {
        switch self {
        case .surfaceScan:
            return "Studio finds exposed surface patches and spreads the design budget across them. No target residue is conditioned as a hotspot."
        case .surfacePatch:
            return "Pick a broad part of the surface. Studio uses it only to place the starting centre; it does not force contacts to those residues."
        case .com:
            return "Build around the target centre of mass. This is suitable for a small molecule, not a fixed globular protein."
        case .hotspots:
            return "The selected residues both position the binder and become contact hotspots. Use this only when the epitope is intentional."
        case .explicit:
            return "You supply the XYZ the design should be centred on."
        }
    }

    var specValue: String? {
        switch self {
        case .surfaceScan, .surfacePatch: return nil
        case .com:      return "com"
        case .hotspots: return "hotspots"
        case .explicit: return nil
        }
    }
}

/// One atom or residue that can carry conditioning, as read back out of the
/// prepared target. Names come from the target itself rather than being typed by
/// the user, so a typo cannot silently produce an unconditioned design.
struct TargetSite: Codable, Hashable, Identifiable {
    /// Zero-based atom index in the submitted SMILES; nil for protein residues.
    var atomIndex: Int?
    /// e.g. "O17" for a ligand atom, "B67" for a protein residue.
    var name: String
    /// e.g. "O" / "C" for ligand atoms, the three-letter code for residues.
    var element: String
    /// A ligand atom may be both buried and a donor/acceptor. A single optional
    /// suggestion silently discarded that chemistry.
    var suggestions: Set<AtomCondition>
    /// Why each suggestion was made, shown before the user applies it.
    var suggestionReasons: [AtomCondition: String]

    var id: String { name }
}

/// Which predictors verify the finished designs.
struct RFD3Verification: Codable, Hashable {
    /// Verification predictors. Small-molecule campaigns add these alongside
    /// mandatory Boltz affinity scoring; protein campaigns run exactly this
    /// selection because the affinity head is not trained for their interface.
    var extraPredictors: [Predictor] = []
    var intellifoldModel: IntelliFoldModel = .v2flash
    /// Steering potentials roughly double Boltz's time but give physically
    /// cleaner poses, which matters more for a pocket than for an interface.
    var useBoltzPotentials: Bool = true
    /// The affinity head produces P(bind). Small molecules only — it is not
    /// trained for protein–protein interfaces.
    var runAffinityHead: Bool = true
    /// Re-fold the top designs without the target, to check the binder folds on
    /// its own rather than only in complex.
    var runApoCheck: Bool = true
    var topN: Int = 100
    var filters = RFD3HitFilters()

    /// Everything that will actually run.
    ///
    /// For a small molecule Boltz is prepended unconditionally: the ranking
    /// metric needs P(bind) and only Boltz produces it. For a protein target
    /// that reason evaporates — the affinity head is trained on small molecules
    /// — so the list is exactly what the user chose.
    func effectiveExtraPredictors(for kind: RFD3TargetKind) -> [Predictor] {
        var seen = Set<String>()
        return extraPredictors.compactMap { raw in
            let predictor = raw.checkingVariant
            guard predictor.isAvailable else { return nil }
            if kind == .smallMolecule && predictor.runnerValue == Predictor.boltz.runnerValue {
                return nil
            }
            return seen.insert(predictor.independenceIdentity).inserted ? predictor : nil
        }
    }

    func allPredictors(for kind: RFD3TargetKind) -> [Predictor] {
        let extras = effectiveExtraPredictors(for: kind)
        guard kind == .smallMolecule else { return extras }
        let boltz: Predictor = useBoltzPotentials ? .boltzPotentials : .boltz
        return [boltz] + extras
    }

    func usesBoltz(for kind: RFD3TargetKind) -> Bool {
        allPredictors(for: kind).contains { $0.runnerValue == Predictor.boltz.runnerValue }
    }

    func usesIntelliFold(for kind: RFD3TargetKind) -> Bool {
        allPredictors(for: kind).contains { $0 == .intellifold }
    }

    private enum CodingKeys: String, CodingKey {
        case extraPredictors, intellifoldModel, useBoltzPotentials, runAffinityHead, runApoCheck, topN, filters
    }

    init() {}

    /// Resilient decoding, so a project saved before the predictor choice
    /// existed still opens.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let d = RFD3Verification()
        extraPredictors    = try c.decodeIfPresent([Predictor].self, forKey: .extraPredictors) ?? d.extraPredictors
        intellifoldModel   = try c.decodeIfPresent(IntelliFoldModel.self, forKey: .intellifoldModel) ?? d.intellifoldModel
        useBoltzPotentials = try c.decodeIfPresent(Bool.self, forKey: .useBoltzPotentials) ?? d.useBoltzPotentials
        runAffinityHead    = try c.decodeIfPresent(Bool.self, forKey: .runAffinityHead) ?? d.runAffinityHead
        runApoCheck        = try c.decodeIfPresent(Bool.self, forKey: .runApoCheck) ?? d.runApoCheck
        topN               = try c.decodeIfPresent(Int.self, forKey: .topN) ?? d.topN
        filters            = try c.decodeIfPresent(RFD3HitFilters.self, forKey: .filters) ?? d.filters
    }
}

/// Everything the user specifies for an RFdiffusion3 campaign.
struct RFD3Request: Codable, Hashable {
    var designMode: RFD3DesignMode = .deNovo
    var targetKind: RFD3TargetKind = .smallMolecule

    // --- Existing-complex workflows ---
    /// Source binder chain in the user structure. It is normalized to A.
    var sourceBinderChain: String = "A"
    /// Partial diffusion noise magnitude in Angstroms, not a timestep index.
    var partialT: Double = 2.0
    /// Keep the supplied binder sequence rather than running an inverse folder.
    var preservePartialSequence: Bool = true
    /// Functional residues and the minimum atoms whose geometry must be retained.
    var motifSites: [RFD3MotifSite] = []

    // --- Small-molecule target ---
    var ligandSource: LigandSource = .smiles
    var smiles: String = ""
    /// Three-letter component code. RFD3 needs an explicit component; a generic
    /// "LIG" resolves against a three-atom placeholder in the pinned build.
    var componentCode: String = "LG1"
    var ligandStructurePath: String = ""
    var ligandResidueName: String = ""

    // --- Protein target ---
    /// RFdiffusion3 needs a structure. A user with only a sequence can have one
    /// predicted in the tab, which then becomes the target structure.
    var targetSequence: String = ""
    /// Sequence extracted from the selected structure/chain by the target
    /// inspector. Kept separately so a pasted sequence mismatch blocks the run.
    var structureTargetSequence: String = ""
    var targetStructurePath: String = ""
    /// Comma-separated structure chain IDs in colon-sequence order. This stays
    /// a string so projects from the original single-chain control migrate.
    var targetChain: String = "B"
    /// Residue range kept from the target, e.g. "B1-71".
    var targetContig: String = ""

    /// Ligand geometries to design across, with their share of the budget.
    /// Empty means the single generated conformer is used, as before.
    var conformerPlan: [ConformerChoice] = []
    /// User-declared intent. This is separate from the endpoints so the Start
    /// button stays blocked between turning conjugation on and completing the
    /// two-click directed bond.
    var ligandIsConjugated: Bool = false
    /// Core-side atom of the explicit acyclic bond leading into a linker.
    var attachmentAtom: Int?
    /// Linker-side atom directly bonded to `attachmentAtom`. Both endpoints are
    /// required because one atom alone cannot identify which branch is linker.
    var attachmentLinkerAtom: Int?
    var searchPDB: Bool = true

    // --- Conditioning ---
    /// Site name -> conditions applied to it.
    var conditions: [String: Set<AtomCondition>] = [:]
    var originStrategy: OriginStrategy = .com
    /// Residues used only to locate a broad surface region. They are never
    /// serialized as RFdiffusion3 hotspot conditioning.
    var surfacePatchResidues: Set<String> = []
    var originXYZ: [Double] = [0, 0, 0]

    // --- Design shape ---
    var minLength: Int = 65
    var maxLength: Int = 150
    var numBins: Int = 10
    var numDesigns: Int = 100
    /// Explicit bin lengths, when the user has pinned them. Empty means derive
    /// them from min/max/numBins.
    var explicitLengths: [Int] = []
    /// Non-loopy conditioning, on by default: de-novo binders otherwise come out
    /// loop-heavy. The RFD3 field is spelled `is_non_loopy`.
    var preferStructured: Bool = true

    // --- Sampling ---
    var timesteps: Int = 200
    var recycles: Int = 2
    /// Native MLX trajectory batch. 8 was the measured optimum on small
    /// fixtures (81-131 tokens); the validated production campaign uses 4 for a
    /// 33-atom ligand with binders up to 150 aa, so 4 is the safer default as
    /// systems grow. Not derived from free memory -- peak footprint barely moved
    /// between batch 1 and 32 while throughput collapsed above the optimum.
    var batchSize: Int = 4
    /// Two concurrent shape queues beat serial by 19.2%; four regressed.
    var queuesPerBin: Int = 2
    var precision: String = "bf16"
    var seedBase: Int = 0

    // --- Sequence design & verification ---
    var sequenceModel: RFD3SequenceModel = .lasermpnn
    var sequencesPerBackbone: Int = 4
    /// Sampling temperature for the inverse-folding step.
    var sequenceTemperature: Double = 0.10
    /// LASErMPNN only: the binding site gets its own temperature, because it
    /// decodes side-chain rotamers alongside the sequence.
    var firstShellTemperature: Double = 1.00
    var verification = RFD3Verification()

    init() {}

    // MARK: Derived

    /// Lengths of the discrete bins. A fixture is frozen at one binder length —
    /// different lengths cannot share a native tensor batch — so a length range
    /// is covered by evenly spaced bins, each internally batched by shape.
    var binLengths: [Int] {
        if !explicitLengths.isEmpty { return Array(Set(explicitLengths)).sorted() }
        let bins = max(1, numBins)
        guard bins > 1 else { return [minLength] }
        let step = Double(maxLength - minLength) / Double(bins - 1)
        return Array(Set((0..<bins).map { Int((Double(minLength) + step * Double($0)).rounded()) })).sorted()
    }

    var designsPerBin: Int { max(1, numDesigns / max(1, binLengths.count)) }

    var totalDesignedSequences: Int {
        max(1, numDesigns) * max(1, designMode == .partialDiffusion && preservePartialSequence
                                ? 1 : sequencesPerBackbone)
    }

    var selectedTargetChainIDs: [String] {
        targetChain.split(separator: ",", omittingEmptySubsequences: false)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() }
            .filter { !$0.isEmpty }
    }

    var targetSequenceResult: Result<[ProteinChainInput], ProteinSequenceInputError> {
        ProteinSequenceInput.parse(targetSequence, startingAt: 1, minimumLength: 5)
    }

    var targetChains: [ProteinChainInput] {
        guard case .success(let parsed) = targetSequenceResult,
              parsed.count == selectedTargetChainIDs.count else { return [] }
        return zip(selectedTargetChainIDs, parsed).map {
            ProteinChainInput(id: $0.0, sequence: $0.1.sequence)
        }
    }

    mutating func reconcileSelectionBudget() {
        verification.topN = min(max(1, verification.topN), totalDesignedSequences)
    }

    var requiredComponents: [InstallComponent] {
        var result: [InstallComponent] = [.rfd3]
        if !(designMode == .partialDiffusion && preservePartialSequence) {
            result.append(sequenceModel.component)
        }
        for predictor in verification.allPredictors(for: targetKind)
            where !result.contains(predictor.component) {
            result.append(predictor.component)
        }
        // Protenix has its own upstream MSA-server client. Boltz is only needed
        // as the generator when neither it nor Protenix is already selected.
        if targetKind == .protein && !result.contains(.boltz)
            && !result.contains(.protenixV2) && !result.contains(.protenixMini) {
            result.append(.boltz)
        }
        return result
    }

    /// Clamp the inverse folder to one that suits the current target.
    mutating func reconcileSequenceModel() {
        if !targetKind.sequenceModels.contains(sequenceModel) {
            sequenceModel = targetKind.sequenceModels.first ?? .solublempnn
            sequenceTemperature = sequenceModel.defaultTemperature
            firstShellTemperature = sequenceModel.defaultFirstShellTemperature
        }
    }

    mutating func reconcileVerification() {
        verification.extraPredictors = verification.effectiveExtraPredictors(for: targetKind)
        if targetKind == .protein {
            verification.runAffinityHead = false
            if !verification.usesBoltz(for: .protein) {
                verification.useBoltzPotentials = false
            }
        }
    }

    func sites(with condition: AtomCondition) -> [String] {
        conditions.filter { $0.value.contains(condition) }.keys.sorted()
    }

    var hasAnyHotspot: Bool { !sites(with: .hotspot).isEmpty }

    /// Estimated backbone-generation time, from the measured 6.95–8.00 s/design
    /// at batch 8 with two queues.
    var estimatedBackboneSeconds: Double {
        let perDesign = targetKind == .smallMolecule ? 6.95 : 8.00
        // Two concurrent shape queues measured 19.2% better than serial.
        let speedup = queuesPerBin >= 2 ? 1.192 : 1.0
        return Double(max(1, numDesigns)) * perDesign / speedup
    }

    var isRunnable: Bool {
        guard minLength >= 1, maxLength >= minLength, numDesigns >= 1 else { return false }
        if designMode != .deNovo {
            return targetKind == .protein && !targetStructurePath.isEmpty
        }
        switch targetKind {
        case .smallMolecule:
            switch ligandSource {
            case .smiles:        return !smiles.trimmingCharacters(in: .whitespaces).isEmpty
            case .structureFile: return !ligandStructurePath.isEmpty && !ligandResidueName.isEmpty
            }
        case .protein:
            return !targetStructurePath.isEmpty
        }
    }

    /// Blocking problems, phrased for someone who has not read the RFD3 docs.
    var validationIssues: [String] {
        var issues: [String] = []
        if minLength < 1 || maxLength < minLength { issues.append("Choose a valid binder-length range.") }
        if numDesigns < 1 { issues.append("Generate at least one backbone.") }
        if numBins < 1 { issues.append("Use at least one length bin.") }
        if timesteps < 1 || recycles < 0 || batchSize < 1 || queuesPerBin < 1 {
            issues.append("Sampling counts must be positive (recycles may be zero).")
        }
        if sequencesPerBackbone < 1 { issues.append("Design at least one sequence per backbone.") }
        if verification.topN < 1 || verification.topN > totalDesignedSequences {
            issues.append("Keep at most \(totalDesignedSequences) designs—the campaign only creates that many sequences.")
        }
        if !explicitLengths.isEmpty && explicitLengths.contains(where: { $0 < 1 }) {
            issues.append("Explicit binder lengths must all be positive.")
        }

        if designMode != .deNovo && targetKind != .protein {
            issues.append("Partial diffusion and motif scaffolding currently require a protein complex.")
        }
        if designMode == .partialDiffusion {
            if partialT < 0.1 || partialT > 15 {
                issues.append("Partial-diffusion noise must be between 0.1 and 15 Å.")
            }
            let binder = sourceBinderChain.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
            if binder.count != 1 || !binder.allSatisfy(\.isLetter) {
                issues.append("Choose one source binder chain, such as A.")
            }
            if selectedTargetChainIDs.contains(binder) {
                issues.append("The source binder chain and fixed target chains must be different.")
            }
        }
        if designMode == .motifScaffolding {
            let binder = sourceBinderChain.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
            if binder.count != 1 || !binder.allSatisfy(\.isLetter) {
                issues.append("Choose one source motif chain, such as A.")
            }
            if motifSites.isEmpty {
                issues.append("Add at least one motif residue and its functional atoms.")
            }
            let residues = motifSites.map { $0.residue.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() }
            if selectedTargetChainIDs.contains(binder) {
                issues.append("The source motif chain and fixed target chains must be different.")
            }
            if Set(residues).count != residues.count {
                issues.append("Each motif residue can only be listed once.")
            }
            let residuePattern = try? NSRegularExpression(pattern: "^[A-Z][1-9][0-9]*$")
            if residues.contains(where: { value in
                let range = NSRange(value.startIndex..<value.endIndex, in: value)
                return residuePattern?.firstMatch(in: value, range: range) == nil
                    || value.first.map(String.init) != binder
            }) {
                issues.append("Write each motif residue as its source chain and number, such as \(binder)42.")
            }
            if motifSites.contains(where: { $0.atoms.split(separator: ",").allSatisfy { $0.trimmingCharacters(in: .whitespaces).isEmpty } }) {
                issues.append("Every motif residue needs at least one explicit atom.")
            }
        }

        if targetKind == .smallMolecule {
            if ligandIsConjugated && (attachmentAtom == nil || attachmentLinkerAtom == nil) {
                issues.append("Choose both ends of the core-to-linker bond, or mark the molecule as free.")
            } else if !ligandIsConjugated &&
                        (attachmentAtom != nil || attachmentLinkerAtom != nil) {
                issues.append("Clear the saved linker bond or mark the molecule as attached.")
            }
            let rawCode = ligandSource == .smiles ? componentCode : ligandResidueName
            let code = rawCode.trimmingCharacters(in: .whitespaces).uppercased()
            if code.count < 1 || code.count > 3 || !code.allSatisfy({ $0.isLetter || $0.isNumber }) {
                issues.append(ligandSource == .smiles
                              ? "The component code must be 1–3 letters or digits, e.g. LG1."
                              : "The ligand residue name must be 1–3 letters or digits, e.g. FHE.")
            }
            if code == "LIG" {
                issues.append("\"LIG\" collides with a three-atom placeholder component and would silently truncate your molecule. Pick another code.")
            }
            if smiles.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                issues.append("Add the ligand SMILES; sequence design and holo verification need its chemistry even when you supply a 3D pose.")
            }
            if ligandSource == .structureFile,
               !FileManager.default.fileExists(atPath: ligandStructurePath) {
                issues.append("Choose an existing ligand PDB file.")
            }
        } else {
            if !FileManager.default.fileExists(atPath: targetStructurePath) {
                issues.append("Choose or predict an existing protein structure file.")
            }
            if case .failure(let error) = targetSequenceResult { issues.append(error.message) }
            if targetContig.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                issues.append("Read the target structure so Studio can verify the selected chain and residue range.")
            }
            let canonicalTarget = ProteinSequenceInput.canonical(targetSequence, startingAt: 1)
            let canonicalStructure = ProteinSequenceInput.canonical(structureTargetSequence, startingAt: 1)
            if canonicalStructure != nil && canonicalTarget != canonicalStructure {
                issues.append("The pasted target sequence does not match the selected structure chain. Use the sequence read from the structure or choose the matching chain.")
            }
            let chains = selectedTargetChainIDs
            if chains.isEmpty || chains.contains(where: { $0.count != 1 || !$0.allSatisfy(\.isLetter) })
                || Set(chains).count != chains.count {
                issues.append("Choose unique one-letter target chain identifiers, such as B,C.")
            } else if case .success(let sequences) = targetSequenceResult,
                      chains.count != sequences.count {
                issues.append("The number of selected structure chains must match the number of colon-separated target sequences.")
            }
            if verification.allPredictors(for: .protein).isEmpty {
                issues.append("Select at least one verification predictor for the protein campaign.")
            }
        }
        if designMode == .deNovo && targetKind == .protein {
            if originStrategy == .com {
                issues.append("Target-centre placement is unsafe for a fixed protein: choose Whole surface, Broad region, or Exact epitope.")
            }
            if originStrategy == .hotspots && !hasAnyHotspot {
                issues.append("Exact epitope needs at least one selected hotspot residue.")
            }
            if originStrategy == .surfacePatch && surfacePatchResidues.isEmpty {
                issues.append("Broad region needs at least one selected target residue.")
            }
            if originStrategy == .explicit &&
                (originXYZ.count != 3 || originXYZ.contains(where: { !$0.isFinite })) {
                issues.append("Manual XYZ requires three finite coordinates.")
            }
        }
        if maxLength - minLength > 0 && numBins > (maxLength - minLength + 1) {
            issues.append("More length bins than distinct lengths in the range — reduce the number of bins.")
        }
        return issues
    }

    private enum CodingKeys: String, CodingKey {
        case designMode, sourceBinderChain, partialT, preservePartialSequence, motifSites
        case targetKind, ligandSource, smiles, componentCode, ligandStructurePath, ligandResidueName
        case targetStructurePath, targetChain, targetContig, structureTargetSequence
        case conditions, originStrategy, surfacePatchResidues, originXYZ
        case minLength, maxLength, numBins, numDesigns, explicitLengths, preferStructured
        case timesteps, recycles, batchSize, queuesPerBin, precision, seedBase
        case sequencesPerBackbone, verification
        case targetSequence, sequenceModel, sequenceTemperature, firstShellTemperature
        case conformerPlan, ligandIsConjugated, attachmentAtom, attachmentLinkerAtom, searchPDB
    }

    /// Resilient decoding: every field defaults if absent.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let d = RFD3Request()
        designMode          = try c.decodeIfPresent(RFD3DesignMode.self, forKey: .designMode) ?? d.designMode
        sourceBinderChain   = try c.decodeIfPresent(String.self, forKey: .sourceBinderChain) ?? d.sourceBinderChain
        partialT            = try c.decodeIfPresent(Double.self, forKey: .partialT) ?? d.partialT
        preservePartialSequence = try c.decodeIfPresent(Bool.self, forKey: .preservePartialSequence) ?? d.preservePartialSequence
        motifSites         = try c.decodeIfPresent([RFD3MotifSite].self, forKey: .motifSites) ?? d.motifSites
        targetKind          = try c.decodeIfPresent(RFD3TargetKind.self, forKey: .targetKind) ?? d.targetKind
        ligandSource        = try c.decodeIfPresent(LigandSource.self, forKey: .ligandSource) ?? d.ligandSource
        smiles              = try c.decodeIfPresent(String.self, forKey: .smiles) ?? d.smiles
        componentCode       = try c.decodeIfPresent(String.self, forKey: .componentCode) ?? d.componentCode
        ligandStructurePath = try c.decodeIfPresent(String.self, forKey: .ligandStructurePath) ?? d.ligandStructurePath
        ligandResidueName   = try c.decodeIfPresent(String.self, forKey: .ligandResidueName) ?? d.ligandResidueName
        targetStructurePath = try c.decodeIfPresent(String.self, forKey: .targetStructurePath) ?? d.targetStructurePath
        targetChain         = try c.decodeIfPresent(String.self, forKey: .targetChain) ?? d.targetChain
        targetContig        = try c.decodeIfPresent(String.self, forKey: .targetContig) ?? d.targetContig
        conditions          = try c.decodeIfPresent([String: Set<AtomCondition>].self, forKey: .conditions) ?? d.conditions
        originStrategy      = try c.decodeIfPresent(OriginStrategy.self, forKey: .originStrategy) ?? d.originStrategy
        surfacePatchResidues = try c.decodeIfPresent(Set<String>.self, forKey: .surfacePatchResidues) ?? d.surfacePatchResidues
        originXYZ           = try c.decodeIfPresent([Double].self, forKey: .originXYZ) ?? d.originXYZ
        minLength           = try c.decodeIfPresent(Int.self, forKey: .minLength) ?? d.minLength
        maxLength           = try c.decodeIfPresent(Int.self, forKey: .maxLength) ?? d.maxLength
        numBins             = try c.decodeIfPresent(Int.self, forKey: .numBins) ?? d.numBins
        numDesigns          = try c.decodeIfPresent(Int.self, forKey: .numDesigns) ?? d.numDesigns
        explicitLengths     = try c.decodeIfPresent([Int].self, forKey: .explicitLengths) ?? d.explicitLengths
        preferStructured    = try c.decodeIfPresent(Bool.self, forKey: .preferStructured) ?? d.preferStructured
        timesteps           = try c.decodeIfPresent(Int.self, forKey: .timesteps) ?? d.timesteps
        recycles            = try c.decodeIfPresent(Int.self, forKey: .recycles) ?? d.recycles
        batchSize           = try c.decodeIfPresent(Int.self, forKey: .batchSize) ?? d.batchSize
        queuesPerBin        = try c.decodeIfPresent(Int.self, forKey: .queuesPerBin) ?? d.queuesPerBin
        precision           = try c.decodeIfPresent(String.self, forKey: .precision) ?? d.precision
        seedBase            = try c.decodeIfPresent(Int.self, forKey: .seedBase) ?? d.seedBase
        sequencesPerBackbone = try c.decodeIfPresent(Int.self, forKey: .sequencesPerBackbone) ?? d.sequencesPerBackbone
        targetSequence      = try c.decodeIfPresent(String.self, forKey: .targetSequence) ?? d.targetSequence
        structureTargetSequence = try c.decodeIfPresent(String.self, forKey: .structureTargetSequence) ?? d.structureTargetSequence
        sequenceModel       = try c.decodeIfPresent(RFD3SequenceModel.self, forKey: .sequenceModel) ?? d.sequenceModel
        sequenceTemperature = try c.decodeIfPresent(Double.self, forKey: .sequenceTemperature) ?? d.sequenceTemperature
        firstShellTemperature = try c.decodeIfPresent(Double.self, forKey: .firstShellTemperature) ?? d.firstShellTemperature
        conformerPlan       = try c.decodeIfPresent([ConformerChoice].self, forKey: .conformerPlan) ?? d.conformerPlan
        attachmentAtom      = try c.decodeIfPresent(Int.self, forKey: .attachmentAtom) ?? d.attachmentAtom
        attachmentLinkerAtom = try c.decodeIfPresent(Int.self, forKey: .attachmentLinkerAtom) ?? d.attachmentLinkerAtom
        ligandIsConjugated  = try c.decodeIfPresent(Bool.self, forKey: .ligandIsConjugated)
            ?? (attachmentAtom != nil || attachmentLinkerAtom != nil)
        searchPDB           = try c.decodeIfPresent(Bool.self, forKey: .searchPDB) ?? d.searchPDB
        verification        = try c.decodeIfPresent(RFD3Verification.self, forKey: .verification) ?? d.verification
        // Older protein projects used target COM (or an empty hotspot choice)
        // as the apparent "bind anywhere" default. That does not sample the
        // surface, so migrate it to the explicit whole-surface strategy.
        if targetKind == .protein && designMode == .deNovo {
            if originStrategy == .com || (originStrategy == .hotspots && !hasAnyHotspot) {
                originStrategy = .surfaceScan
            }
        }
        reconcileSequenceModel()
        reconcileVerification()
        reconcileSelectionBudget()
    }
}
