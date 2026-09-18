import Foundation

/// Stable value passed to SwiftUI's results WindowGroup. Results belong in a
/// normal, movable macOS window rather than a sheet attached to whichever
/// popover happened to launch them.
struct RunResultsWindowRequest: Codable, Hashable {
    let rootPath: String
    let workflow: StudioWorkflow
    let title: String

    init(root: URL, workflow: StudioWorkflow, title: String? = nil) {
        self.rootPath = root.path
        self.workflow = workflow
        self.title = title ?? "\(workflow.label) results"
    }

    var root: URL { URL(fileURLWithPath: rootPath, isDirectory: true) }
}

enum StudioResultStage: String, Hashable {
    case prediction
    case startingStructure
    case design
    case postPrediction
    case generatedBackbone
    case verificationPrediction
    case rankedDesign

    var label: String {
        switch self {
        case .prediction: return "Prediction"
        case .startingStructure: return "Unoptimized starting structure"
        case .design: return "Design stage"
        case .postPrediction: return "Independent post-prediction"
        case .generatedBackbone: return "RFdiffusion3 backbone"
        case .verificationPrediction: return "RFdiffusion3 verification in progress"
        case .rankedDesign: return "Ranked verification"
        }
    }
}

/// Scientific role of a file inside one design. Keeping this separate from the
/// workflow stage lets the UI compare the generated/design structure, the
/// independently refolded complex and the binder-alone fold without flattening
/// them into unrelated rows.
enum StudioResultArtifactRole: String, Hashable {
    case prediction
    case startingStructure
    case designedComplex
    case generatedBackbone
    case complexReprediction
    case binderAlone

    var label: String {
        switch self {
        case .prediction: return "Prediction"
        case .startingStructure: return "Starting structure"
        case .designedComplex: return "Design structure"
        case .generatedBackbone: return "Generated backbone"
        case .complexReprediction: return "Complex reprediction"
        case .binderAlone: return "Binder alone"
        }
    }

    var sortOrder: Int {
        switch self {
        case .startingStructure: return 0
        case .designedComplex, .generatedBackbone: return 1
        case .complexReprediction: return 2
        case .binderAlone: return 3
        case .prediction: return 4
        }
    }
}

/// A structure and its most useful engine-emitted confidence summaries.
/// Values stay numeric here so every workflow uses the same formatting in the UI.
struct StudioResultItem: Identifiable, Hashable {
    let id: String
    let title: String
    let subtitle: String
    let structureURL: URL
    let sequence: String?
    let metrics: [StudioResultMetric]
    let confidenceURL: URL?
    let stage: StudioResultStage
    /// The engine that emitted `metrics`; never inferred from the engine that
    /// happened to create an earlier structure in the workflow.
    let scoreSource: String
    /// Stable design identity shared by all structures that should be compared
    /// together. This is the run for iterative design and source-backbone ID
    /// for RFdiffusion3.
    let groupID: String
    let groupTitle: String
    /// Optional identity below the top-level scientific object. RFdiffusion3
    /// uses one variant per MPNN sequence; iterative design uses one variant
    /// per cycle. Complex and binder-alone checks share this identity.
    let variantID: String?
    let variantTitle: String?
    let artifactRole: StudioResultArtifactRole
    /// Explicit workflow verdict read from disk. Nil means that workflow did
    /// not apply a multi-metric filter; it must never be inferred silently.
    let isHit: Bool?
    let failedFilters: [String]
    /// Source motif residue -> generated chain-A residue. Kept on every stage
    /// so a design never loses the identity of its functional atoms merely
    /// because it has progressed from diffusion to MPNN or prediction.
    let motifMapping: [String: String]
    /// Optional per-source-residue geometry diagnostics. These are emitted by
    /// the MLX generator and independent-prediction recovery scorer, never
    /// inferred by the presentation layer.
    let motifResidueRMSDs: [String: Double]
    var frameworkID: String? = nil
    var frameworkName: String? = nil
    var campaignID: String? = nil
    var designEngine: String? = nil
    var designHitThreshold: Double? = nil

    init(id: String, title: String, subtitle: String, structureURL: URL,
         sequence: String?, metrics: [StudioResultMetric], confidenceURL: URL?,
         stage: StudioResultStage, scoreSource: String, isHit: Bool? = nil,
         failedFilters: [String] = [], motifMapping: [String: String] = [:],
         motifResidueRMSDs: [String: Double] = [:], groupID: String? = nil,
         groupTitle: String? = nil,
         variantID: String? = nil, variantTitle: String? = nil,
         artifactRole: StudioResultArtifactRole = .prediction) {
        self.id = id
        self.title = title
        self.subtitle = subtitle
        self.structureURL = structureURL
        self.sequence = sequence
        self.metrics = metrics
        self.confidenceURL = confidenceURL
        self.stage = stage
        self.scoreSource = scoreSource
        self.groupID = groupID ?? id
        self.groupTitle = groupTitle ?? title
        self.variantID = variantID
        self.variantTitle = variantTitle
        self.artifactRole = artifactRole
        self.isHit = isHit
        self.failedFilters = failedFilters
        self.motifMapping = motifMapping
        self.motifResidueRMSDs = motifResidueRMSDs
    }

    var primaryMetric: StudioResultMetric? {
        metrics.first { $0.kind == .iptm }
            ?? metrics.first { $0.kind == .ipsaeMinimum }
            ?? metrics.first { $0.kind == .plddt }
            ?? metrics.first
    }
}

/// One MPNN derivative or iterative-design cycle within a top-level result.
/// This is the unit that receives an independent verdict and contributes one
/// value to score distributions.
struct StudioResultVariant: Identifiable, Hashable {
    let id: String
    let title: String
    let items: [StudioResultItem]

    var sortedItems: [StudioResultItem] {
        items.sorted {
            if $0.artifactRole.sortOrder != $1.artifactRole.sortOrder {
                return $0.artifactRole.sortOrder < $1.artifactRole.sortOrder
            }
            return $0.title.localizedStandardCompare($1.title) == .orderedAscending
        }
    }

    var isHit: Bool? {
        let verdicts = items.compactMap(\.isHit)
        guard !verdicts.isEmpty else { return nil }
        return verdicts.contains(true)
    }

    var failedFilters: [String] {
        Array(Set(items.flatMap(\.failedFilters))).sorted()
    }

    var sequence: String? {
        items.compactMap(\.sequence).first { !$0.isEmpty }
    }

    func metric(_ kind: StudioResultMetric.Kind) -> StudioResultMetric? {
        sortedItems.sorted {
            StudioResultGroup.metricPriority($0.artifactRole)
                < StudioResultGroup.metricPriority($1.artifactRole)
        }.compactMap { item in item.metrics.first { $0.kind == kind } }.first
    }
}

/// One scientific design and every durable structure generated to assess it.
/// The saved multi-filter verdict is deliberately aggregated here so every
/// results surface uses exactly the same definition of a hit.
struct StudioResultGroup: Identifiable, Hashable {
    let id: String
    let title: String
    let items: [StudioResultItem]

    var sortedItems: [StudioResultItem] {
        items.sorted {
            if $0.artifactRole.sortOrder != $1.artifactRole.sortOrder {
                return $0.artifactRole.sortOrder < $1.artifactRole.sortOrder
            }
            return $0.title.localizedStandardCompare($1.title) == .orderedAscending
        }
    }

    var primaryItems: [StudioResultItem] {
        sortedItems.filter { $0.variantID == nil }
    }

    var variants: [StudioResultVariant] {
        Dictionary(grouping: items.filter { $0.variantID != nil }) {
            $0.variantID!
        }.map { id, members in
            StudioResultVariant(id: id,
                                title: members.first?.variantTitle ?? id,
                                items: members)
        }.sorted { $0.id.localizedStandardCompare($1.id) == .orderedAscending }
    }

    /// Exactly one design-stage complex per iterative cycle, ordered from the
    /// starting structure through the final cycle. Independent checks are not
    /// mixed into the optimization trajectory.
    var iterativeTrajectoryItems: [StudioResultItem] {
        guard id.hasPrefix("iterative|") else { return [] }
        return variants.compactMap { variant in
            variant.sortedItems.first {
                $0.artifactRole == .startingStructure || $0.artifactRole == .designedComplex
            }
        }
    }

    var isHit: Bool? {
        let verdicts = items.compactMap(\.isHit)
        guard !verdicts.isEmpty else { return nil }
        return verdicts.contains(true)
    }

    var failedFilters: [String] {
        Array(Set(items.flatMap(\.failedFilters))).sorted()
    }

    var sequence: String? {
        items.compactMap(\.sequence).first { !$0.isEmpty }
    }

    /// Use each metric once per design. Prefer the independently predicted
    /// complex, then the generated/design structure, and use binder-alone only
    /// for metrics that exist nowhere else.
    func metric(_ kind: StudioResultMetric.Kind) -> StudioResultMetric? {
        let preferred = sortedItems.sorted {
            Self.metricPriority($0.artifactRole) < Self.metricPriority($1.artifactRole)
        }
        return preferred.compactMap { item in item.metrics.first { $0.kind == kind } }.first
    }

    fileprivate static func metricPriority(_ role: StudioResultArtifactRole) -> Int {
        switch role {
        case .complexReprediction: return 0
        case .designedComplex, .generatedBackbone: return 1
        case .binderAlone: return 2
        case .startingStructure, .prediction: return 3
        }
    }
}

struct StudioResultMetric: Identifiable, Hashable {
    enum Kind: String, CaseIterable, Hashable {
        case plddt
        case ligandPLDDT, ligandRMSD, pocketPreorgRMSD, preorgScore
        case iptm
        case ptm
        case interfacePAEMinimum
        case ipsaeMinimum
        case interfacePDE
        case minimumIPTM
        case meanIPTM
        case bindingProbability, nessoBindingProbability, nessoAffinity, nessoPlacementEntropy, nessoInterfaceEntropy, nessoScreeningScore
        case rankingScore
        case pocketMeanDistance
        case pocketFractionWithinCutoff
        case complexRMSD
        case binderBackboneRMSD
        case binderPLDDT
        case binderRMSD
        case motifInsertionRMSD
        case motifPredictionRMSD
        case motifMaximumDrift
        case backboneCAValidity

        var label: String {
            switch self {
            case .ligandPLDDT: return "ligand pLDDT"
            case .ligandRMSD: return "ligand pose RMSD"
            case .pocketPreorgRMSD: return "pocket preorganisation RMSD"
            case .preorgScore: return "final preorganisation score"
            case .plddt: return "pLDDT"
            case .iptm: return "iPTM"
            case .ptm: return "pTM"
            case .interfacePAEMinimum: return "min interface PAE"
            case .ipsaeMinimum: return "ipSAE(min)"
            case .interfacePDE: return "interface PDE"
            case .minimumIPTM: return "minimum iPTM"
            case .meanIPTM: return "mean iPTM"
            case .bindingProbability: return "P(bind)"
            case .nessoBindingProbability: return "NESSO P(bind)"
            case .nessoAffinity: return "NESSO log10(IC50/µM)"
            case .nessoPlacementEntropy: return "NESSO full PL entropy"
            case .nessoInterfaceEntropy: return "NESSO interface entropy"
            case .nessoScreeningScore: return "NESSO screening score"
            case .rankingScore: return "ranking score"
            case .pocketMeanDistance: return "epitope distance"
            case .pocketFractionWithinCutoff: return "epitope coverage"
            case .complexRMSD: return "binder pose RMSD"
            case .binderBackboneRMSD: return "binder fold RMSD"
            case .binderPLDDT: return "binder pLDDT"
            case .binderRMSD: return "binder-alone RMSD"
            case .motifInsertionRMSD: return "motif placement RMSD"
            case .motifPredictionRMSD: return "predicted motif RMSD"
            case .motifMaximumDrift: return "fixed-atom drift"
            case .backboneCAValidity: return "valid Cα spacing"
            }
        }

        var explanation: String {
            switch self {
            case .ligandPLDDT: return "Mean ligand-atom confidence on the 0–100 scale."
            case .ligandRMSD: return "Ligand heavy-atom RMSD in the fitted binder frame relative to its parent design."
            case .pocketPreorgRMSD: return "Apo/holo pocket heavy-atom RMSD after fitting pocket backbone atoms."
            case .preorgScore: return "Base score plus the recorded pocket and whole-fold rewards; only compared within the apo-tested shortlist."
            case .plddt: return "Local structural confidence; shown on the conventional 0–100 scale."
            case .iptm: return "Confidence in the relative placement of chains; higher is better."
            case .ptm: return "Confidence in the overall fold; higher is better."
            case .interfacePAEMinimum:
                return "The lowest predicted aligned error across a pair of different chains, in Å. Lower is better."
            case .ipsaeMinimum:
                return "The conservative smaller directional ipSAE score calculated from the engine's PAE. Higher is better."
            case .interfacePDE:
                return "Boltz interface predicted distance error, in Å. This is not relabelled as PAE. Lower is better."
            case .minimumIPTM: return "The weakest iPTM across the verification engines; higher is better."
            case .meanIPTM: return "Mean iPTM across the verification engines; higher is better."
            case .nessoBindingProbability: return "NESSO binding probability, one component of its screening score; not calibrated against Boltz probabilities."
            case .nessoPlacementEntropy: return "Full protein–ligand distogram entropy (entropy_pl), retained for historical scores and diagnostics. Current screening uses pocket-cropped entropy."
            case .nessoInterfaceEntropy: return "Pocket-cropped protein–ligand distogram entropy (entropy_crop_pl). Current screening requires a finite value greater than 0.000001 and at most 1; zero can indicate failed ligand placement."
            case .nessoScreeningScore: return "Recorded NESSO screening score, higher is better. Current runs use P(bind) + (1 − pocket-cropped interface entropy); older runs retain their recorded policy. Structural confidence is independent."
            case .nessoAffinity: return "NESSO predicted log10(IC50/µM); lower predicts stronger affinity. Reported separately and not used in the Boltz search objective."
            case .bindingProbability: return "Boltz probability that the small molecule binds; higher is better."
            case .rankingScore: return "The workflow's own score used to order these results."
            case .pocketMeanDistance:
                return "Mean nearest Cα distance from each requested epitope residue to the binder. This reports response to the soft pocket prior; lower is closer."
            case .pocketFractionWithinCutoff:
                return "Fraction of requested epitope residues whose nearest binder Cα is within the recorded Protenix pocket cutoff. This is geometry, not evidence of binding."
            case .complexRMSD:
                return "Cα RMSD of the complex binder to its designed pose after fitting the fixed target. This detects a good fold predicted on the wrong target surface; lower is better."
            case .binderBackboneRMSD:
                return "Cα RMSD of the independently predicted complex binder to the designed backbone after fitting the binder itself. This measures fold recovery without interface placement; lower is better."
            case .binderPLDDT:
                return "Local confidence of the binder predicted without its target. Higher is better."
            case .binderRMSD:
                return "Cα RMSD between binder-alone and complex predictions after fitting the binder. Lower suggests preorganisation."
            case .motifInsertionRMSD:
                return "Atom RMSD used to assign each unindexed source motif token to a generated scaffold residue before the fixed atoms are copied into the output. Lower is better."
            case .motifPredictionRMSD:
                return "RMSD of the explicitly selected motif atoms in an independent sequence prediction after fitting those motif atoms to the generated design. Lower means the functional geometry was recovered."
            case .motifMaximumDrift:
                return "Largest displacement of an explicitly fixed motif atom during RFdiffusion3 sampling. It should remain near zero."
            case .backboneCAValidity:
                return "Percentage of adjacent binder Cα distances between 3.6 and 4.0 Å in the generated backbone."
            }
        }
    }

    let kind: Kind
    let value: Double
    var id: String { kind.rawValue }

    var displayValue: String {
        switch kind {
        case .ligandPLDDT: return String(format: "%.1f", value)
        case .plddt:
            let conventional = value <= 1.000_001 ? value * 100 : value
            return String(format: "%.1f", conventional)
        case .interfacePAEMinimum, .interfacePDE, .pocketMeanDistance,
             .complexRMSD, .binderBackboneRMSD, .binderRMSD, .ligandRMSD, .pocketPreorgRMSD,
             .motifInsertionRMSD, .motifPredictionRMSD, .motifMaximumDrift:
            return String(format: "%.2f Å", value)
        case .binderPLDDT:
            let conventional = value <= 1.000_001 ? value * 100 : value
            return String(format: "%.1f", conventional)
        case .pocketFractionWithinCutoff:
            return String(format: "%.0f%%", value * 100)
        case .backboneCAValidity:
            return String(format: "%.0f%%", value)
        default:
            return String(format: "%.3f", value)
        }
    }
}

/// Minimal RFC 4180 reader. RFdiffusion3 stores JSON maps in quoted CSV cells,
/// so splitting on commas would silently attach structures to the wrong design.
enum CSVTable {
    static func rows(at url: URL) -> [[String: String]] {
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return [] }
        let records = parse(text)
        guard let rawHeader = records.first else { return [] }
        let header = rawHeader.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        guard !header.contains(""), Set(header).count == header.count else { return [] }
        return records.dropFirst().filter { $0.count == header.count && !$0.allSatisfy(\.isEmpty) }.map { values in
            Dictionary(uniqueKeysWithValues: header.enumerated().map { index, name in
                (name.trimmingCharacters(in: .whitespacesAndNewlines), index < values.count ? values[index] : "")
            })
        }
    }

    private static func parse(_ text: String) -> [[String]] {
        // Swift treats CRLF as a single extended grapheme cluster, so normalize
        // it before the character state machine looks for line boundaries.
        let text = text.replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")
        var records: [[String]] = []
        var record: [String] = []
        var field = ""
        var quoted = false
        var index = text.startIndex
        while index < text.endIndex {
            let character = text[index]
            if quoted {
                if character == "\"" {
                    let next = text.index(after: index)
                    if next < text.endIndex, text[next] == "\"" {
                        field.append("\"")
                        index = next
                    } else {
                        quoted = false
                    }
                } else {
                    field.append(character)
                }
            } else {
                switch character {
                case "\"": quoted = true
                case ",": record.append(field); field = ""
                case "\n":
                    record.append(field); records.append(record)
                    record = []; field = ""
                case "\r": break
                default: field.append(character)
                }
            }
            index = text.index(after: index)
        }
        if !quoted && (!field.isEmpty || !record.isEmpty) { record.append(field); records.append(record) }
        return records
    }
}
