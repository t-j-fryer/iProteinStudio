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
    /// Surface residues the validated work targeted, as chain-B tokens.
    var hotspots: [String] = []
    /// Atom the linker leaves from, for a conjugated ligand.
    var attachmentAtom: Int?

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
        // The amide nitrogen where the hydroxyethyl arm leaves the core.
        attachmentAtom: 2)

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
            targetName = example.name
            epitopeResidues = example.hotspots.joined(separator: " ")
        case .smallMolecule:
            targetKind = .ligand
            targetSmiles = example.smiles
            targetName = example.name
            ligandAttachmentAtom = example.attachmentAtom
        }
        reconcileDesigner()
    }
}

extension RFD3Request {
    mutating func apply(_ example: ExampleTarget) {
        switch example.kind {
        case .protein:
            targetKind = .protein
            targetStructurePath = example.structurePath ?? ""
            targetChain = "B"
            // The validated surface patch, and the origin strategy that goes
            // with aiming at one face rather than the whole molecule.
            conditions = Dictionary(uniqueKeysWithValues:
                example.hotspots.map { ($0, Set([AtomCondition.hotspot])) })
            originStrategy = .hotspots
        case .smallMolecule:
            targetKind = .smallMolecule
            ligandSource = .smiles
            smiles = example.smiles
            componentCode = "FLU"
            attachmentAtom = example.attachmentAtom
            originStrategy = .com
        }
        conformerPlan = []
        reconcileSequenceModel()
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
    }
}
