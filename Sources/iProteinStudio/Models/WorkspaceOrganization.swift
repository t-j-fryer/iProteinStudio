import Foundation

enum DesignIntention: String, CaseIterable, Codable, Identifiable, Hashable {
    case monomer, minibinder, nanobody, smallMolecule, motif, optimize
    var id: String { rawValue }
    var label: String {
        switch self {
        case .monomer: return "Monomer"
        case .minibinder: return "Minibinder"
        case .nanobody: return "Nanobody"
        case .smallMolecule: return "Small-molecule binder"
        case .motif: return "Motif scaffolding"
        case .optimize: return "Optimize a structure"
        }
    }
    var artwork: String {
        switch self {
        case .monomer: return "workflow-monomer"
        case .minibinder: return "workflow-minibinder"
        case .nanobody: return "workflow-nanobody"
        case .smallMolecule: return "workflow-ligand"
        case .motif: return "workflow-motif"
        case .optimize: return "workflow-optimize"
        }
    }
    var introduction: String {
        switch self {
        case .monomer: return "Create a new protein fold and sequence."
        case .minibinder: return "Design a compact binder for a protein target."
        case .nanobody: return "Design binding loops on a fixed antibody framework."
        case .smallMolecule: return "Build a protein pocket around a molecule."
        case .motif: return "Build a new scaffold around a functional motif."
        case .optimize: return "Refine a sequence, reshape a structure or explore nearby designs."
        }
    }
    var routes: [DesignWorkflowRoute] {
        switch self {
        case .monomer: return [.rfd4, .rfd3Monomer, .proteinHunter]
        case .nanobody: return [.rfd4, .proteinHunter]
        case .smallMolecule: return [.rfd4, .rfd3, .nise, .proteinHunter]
        case .motif: return [.rfd4, .rfd3, .proteinHunter]
        case .minibinder, .optimize: return [.rfd4, .rfd3, .proteinHunter]
        }
    }

}

enum DesignWorkflowRoute: String, Codable, CaseIterable, Hashable {
    case rfd4, rfd3, rfd3Monomer, proteinHunter, nise
    var mode: WorkspaceMode {
        switch self {
        case .rfd4, .rfd3: return .rfdiffusion
        case .proteinHunter, .rfd3Monomer: return .iterative
        case .nise: return .nise
        }
    }
    var label: String {
        switch self {
        case .rfd4: return "RFD4"
        case .rfd3, .rfd3Monomer: return "RFdiffusion3"
        case .proteinHunter: return "X-token Hallucination"
        case .nise: return "NISE"
        }
    }
}

/// A versioned settings snapshot. Opening a button never submits a job.
struct SavedDesignWorkflow: Codable, Identifiable, Hashable {
    var id = UUID()
    var schema = 1
    var name: String
    var intention: DesignIntention
    var route: DesignWorkflowRoute
    var parameters: Data
    var createdAt = Date()
}

/// The workflow a workspace opens to. A workspace can use every workflow; this
/// is only its remembered starting point and never restricts its contents.
enum WorkspaceMode: String, CaseIterable, Codable, Identifiable, Hashable {
    case iterative
    case nise
    case rfdiffusion
    case predict

    static let designMethods: [WorkspaceMode] = [.iterative, .nise, .rfdiffusion]

    var id: String { rawValue }

    var label: String {
        switch self {
        case .iterative:   return "Protein Hunter"
        case .nise: return "NISE"
        case .rfdiffusion: return "RFdiffusion"
        case .predict:     return "Predict"
        }
    }

    var systemImage: String {
        switch self {
        case .iterative:   return "arrow.triangle.2.circlepath"
        case .nise: return "atom"
        case .rfdiffusion: return "sparkles"
        case .predict:     return "cube.transparent"
        }
    }

    var defaultWorkspaceName: String {
        switch self {
        case .iterative:   return "Untitled Workspace"
        case .nise: return "Untitled NISE"
        case .rfdiffusion: return "Untitled RFdiffusion"
        case .predict:     return "Untitled Prediction"
        }
    }
}

/// Pure naming rules shared by AppState and a standalone contract test.
enum WorkspaceNaming {
    static func uniqueName(base rawBase: String, existing: [String]) -> String {
        let trimmed = rawBase.trimmingCharacters(in: .whitespacesAndNewlines)
        let base = trimmed.isEmpty ? "Untitled Workspace" : trimmed
        let occupied = Set(existing.map(normalized))
        if !occupied.contains(normalized(base)) { return base }

        var suffix = 2
        while occupied.contains(normalized("\(base) \(suffix)")) { suffix += 1 }
        return "\(base) \(suffix)"
    }

    static func slugify(_ value: String) -> String {
        let allowed = CharacterSet.alphanumerics
        let mapped = value.lowercased().unicodeScalars.map {
            allowed.contains($0) ? Character($0) : "_"
        }
        var slug = String(mapped)
        while slug.contains("__") { slug = slug.replacingOccurrences(of: "__", with: "_") }
        slug = slug.trimmingCharacters(in: CharacterSet(charactersIn: "_"))
        return slug.isEmpty ? "workspace" : slug
    }

    static func uniqueSlug(for name: String, existing: [String]) -> String {
        let base = slugify(name)
        let occupied = Set(existing.map { $0.lowercased() })
        if !occupied.contains(base.lowercased()) { return base }

        var suffix = 2
        while occupied.contains("\(base)_\(suffix)".lowercased()) { suffix += 1 }
        return "\(base)_\(suffix)"
    }

    private static func normalized(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
            .folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current)
    }
}
