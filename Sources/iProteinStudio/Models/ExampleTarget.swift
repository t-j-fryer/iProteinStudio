import Foundation

/// Worked examples, so a new user can see the app do something real before
/// having a target of their own.
///
/// Both ship with everything needed to run immediately — including aCbx's
/// alignment, 1,148 sequences already generated. That matters more than it
/// sounds: without it the first thing a new user experiences is a wait on a
/// public MSA server, which frequently takes longer than the fold and sometimes
/// fails outright.
struct ExampleTarget: Identifiable, Hashable {
    enum Kind: Hashable { case protein, smallMolecule }

    var id: String
    var name: String
    var subtitle: String
    var kind: Kind
    /// What this example is good for, in the user's terms.
    var goodFor: String

    var sequence: String = ""
    var smiles: String = ""
    /// Suggested surface residues used by legacy workflow acceptance, as
    /// chain-B tokens. They are not a validated binder epitope.
    var hotspots: [String] = []
    /// Directed acyclic bond from recognition core into the linker.
    var attachmentCoreAtom: Int?
    var attachmentLinkerAtom: Int?

    static let acbx = ExampleTarget(
        id: "acbx",
        name: "α-Cobratoxin",
        subtitle: "71-residue snake toxin · alignment included",
        kind: .protein,
        goodFor: "Folding, and designing binders against a real antivenom target. Its alignment ships with the app, so nothing waits on a server.",
        sequence: "IRCFITPDITSKDCPNGHVCYTKTWCDAFCSIRGKRVDLGCAATCPTVKTGVDIQCCSTDNCNPFPTRKRP",
        hotspots: ["B67", "B69", "B71"])

    static let fluorescein = ExampleTarget(
        id: "fluorescein",
        name: "Fluorescein hydroxyethylamide",
        subtitle: "small molecule with a conjugation linker",
        kind: .smallMolecule,
        goodFor: "Designing a binding pocket around a small molecule, and seeing why a linker must be kept exposed rather than buried.",
        smiles: "O=C(NCCO)c1ccc(-c2c3ccc(=O)cc-3oc3cc([O-])ccc23)c(C(=O)[O-])c1",
        // The amide bond from the fluorescein core carbonyl into the
        // hydroxyethyl presentation arm.
        attachmentCoreAtom: 1,
        attachmentLinkerAtom: 2)

    static let all: [ExampleTarget] = [.acbx, .fluorescein]

    /// The structure file, for RFdiffusion3 — which designs against geometry,
    /// not sequence, so a protein target needs coordinates.
    var structurePath: String? {
        guard kind == .protein else { return nil }
        return AppPaths.examplesDir.appendingPathComponent("\(id)/target.pdb").path
    }
}

extension DesignRequest {
    /// Fill in an iterative-design run against this example.
    mutating func apply(_ example: ExampleTarget) {
        designType = .minibinder
        switch example.kind {
        case .protein:
            targetKind = .protein
            targetSequence = example.sequence
            targetSmiles = ""
            targetName = example.name
            epitopeResidues = example.hotspots.joined(separator: " ")
            ligandContactAtoms = []
            ligandAtomsGeneratedFor = ""
            ligandAttachmentAtom = nil
            ligandAttachmentLinkerAtom = nil
            ligandIsConjugated = false
        case .smallMolecule:
            targetKind = .ligand
            targetSmiles = example.smiles
            targetSequence = ""
            epitopeResidues = ""
            targetName = example.name
            ligandAttachmentAtom = example.attachmentCoreAtom
            ligandAttachmentLinkerAtom = example.attachmentLinkerAtom
            ligandIsConjugated = example.attachmentCoreAtom != nil && example.attachmentLinkerAtom != nil
        }
        reconcileDesigner()
        reconcilePredictors()
    }
}

extension RFD3Request {
    mutating func apply(_ example: ExampleTarget) {
        switch example.kind {
        case .protein:
            targetKind = .protein
            targetSequence = example.sequence
            structureTargetSequence = example.sequence
            targetStructurePath = example.structurePath ?? ""
            targetChain = "B"
            // The bundled example PDB contains the complete mature toxin as
            // chain B. Record the full motif explicitly: the protein campaign
            // needs the sequence to build its cached target MSA, while RFD3
            // needs the complete residue range rather than the one-residue
            // fallback used for an otherwise unspecified target.
            targetContig = "B1-\(example.sequence.count)"
            // No scientifically validated aCbx epitope ships with Studio.
            // Start a real campaign by sampling the solvent-accessible surface
            // instead of presenting the legacy B67/B69/B71 execution fixture
            // as a proven hotspot constraint.
            conditions = [:]
            surfacePatchResidues = []
            originStrategy = .surfaceScan
            verification.extraPredictors = [.boltz]
            verification.useBoltzPotentials = false
            attachmentAtom = nil
            attachmentLinkerAtom = nil
            ligandIsConjugated = false
        case .smallMolecule:
            targetKind = .smallMolecule
            ligandSource = .smiles
            smiles = example.smiles
            componentCode = "FLU"
            attachmentAtom = example.attachmentCoreAtom
            attachmentLinkerAtom = example.attachmentLinkerAtom
            ligandIsConjugated = example.attachmentCoreAtom != nil && example.attachmentLinkerAtom != nil
            conditions = [:]
            originStrategy = .com
            verification.extraPredictors = []
        }
        conformerPlan = []
        reconcileSequenceModel()
        reconcileVerification()
    }
}

/// Mode-specific RFdiffusion3 examples.  These are separate from
/// ``ExampleTarget`` because partial diffusion and motif scaffolding require a
/// complete starting complex, a source chain, and mode-specific controls rather
/// than only a target.
struct RFD3WorkflowExample: Identifiable, Hashable {
    var id: String
    var name: String
    var subtitle: String
    var goodFor: String
    var mode: RFD3DesignMode

    static let p53Partial = RFD3WorkflowExample(
        id: "p53-mdm2-partial",
        name: "p53–MDM2 local exploration",
        subtitle: "PDB 1YCR · 1 Å partial diffusion",
        goodFor: "Perturb the bound p53 helix while every MDM2 atom stays fixed. The starting sequence is preserved, so this is a small and interpretable first partial-diffusion run.",
        mode: .partialDiffusion)

    static let p53Motif = RFD3WorkflowExample(
        id: "p53-mdm2-motif",
        name: "p53–MDM2 motif scaffold",
        subtitle: "Published binder-motif example · PDB 1YCR",
        goodFor: "Build a new 70-residue binder around the three canonical p53 side chains F19, W23 and L26 that occupy the MDM2 cleft. Studio records where all three land in every design and verifies their recovery after prediction.",
        mode: .motifScaffolding)

    static func examples(for mode: RFD3DesignMode) -> [RFD3WorkflowExample] {
        switch mode {
        case .deNovo: return []
        case .partialDiffusion: return [.p53Partial]
        case .motifScaffolding: return [.p53Motif]
        }
    }

    private static var complexPath: String {
        AppPaths.examplesDir.appendingPathComponent("p53_mdm2/1YCR.pdb").path
    }

    /// Exact observed MDM2 residues A25–109 in the bundled crystal structure.
    /// Using the observed sequence, rather than SEQRES with missing termini,
    /// keeps structure/MSA validation exact.
    private static let mdm2Sequence =
        "ETLVRPKPLLLKLLKSVGAQKDTYTMKEVLFYLGQYIMTKRLYDEKQQHIVYCSNDLLGDLFGVPSFSVKEHRKIYTMIYRNLVV"

    func apply(to request: inout RFD3Request) {
        request.designMode = mode
        request.targetKind = .protein
        request.targetStructurePath = Self.complexPath
        request.sourceBinderChain = "B"
        request.targetChain = "A"
        request.targetContig = "A25-109"
        request.targetSequence = Self.mdm2Sequence
        request.structureTargetSequence = Self.mdm2Sequence
        request.conditions = [:]
        request.originStrategy = .com
        request.minLength = 70
        request.maxLength = 70
        request.numBins = 1
        request.explicitLengths = [70]
        request.numDesigns = 8
        request.sequenceModel = .solublempnn
        request.sequenceTemperature = request.sequenceModel.defaultTemperature
        request.sequencesPerBackbone = 2
        request.verification.extraPredictors = [.boltz]
        request.verification.useBoltzPotentials = false
        request.verification.runAffinityHead = false
        request.verification.runApoCheck = true

        switch mode {
        case .partialDiffusion:
            request.partialT = 1.0
            request.preservePartialSequence = true
            request.motifSites = []
        case .motifScaffolding:
            request.preservePartialSequence = false
            // Multiple atoms per side chain preserve both position and
            // orientation. These are the three deeply buried p53 recognition
            // residues used in the published p53–MDM2 RFdiffusion experiment.
            request.motifSites = [
                RFD3MotifSite(residue: "B19", atoms: "CG,CE1,CZ"),
                RFD3MotifSite(residue: "B23", atoms: "CG,NE1,CH2"),
                RFD3MotifSite(residue: "B26", atoms: "CG,CD1,CD2"),
            ]
        case .deNovo:
            break
        }
        request.reconcileSequenceModel()
        request.reconcileVerification()
        request.verification.topN = request.totalDesignedSequences
    }
}

extension PredictionRequest {
    mutating func apply(_ example: ExampleTarget) {
        guard example.kind == .protein else { return }
        pastedSequences = ">\(example.name)\n\(example.sequence)\n"
        sequenceFile = ""
        pairing = .monomer
        // The alignment ships with the app, so this costs nothing.
        binderMSA = .auto
        jobs = []
        parsedInputSignature = ""
    }
}
