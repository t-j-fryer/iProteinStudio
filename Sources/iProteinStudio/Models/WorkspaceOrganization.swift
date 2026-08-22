import Foundation

/// The workflow a workspace opens to. A workspace can use every workflow; this
/// is only its remembered starting point and never restricts its contents.
enum WorkspaceMode: String, CaseIterable, Codable, Identifiable, Hashable {
    case iterative
    case rfdiffusion
    case predict

    var id: String { rawValue }

    var label: String {
        switch self {
        case .iterative:   return "Iterative design"
        case .rfdiffusion: return "RFdiffusion3"
        case .predict:     return "Predict"
        }
    }

    var systemImage: String {
        switch self {
        case .iterative:   return "arrow.triangle.2.circlepath"
        case .rfdiffusion: return "sparkles"
        case .predict:     return "cube.transparent"
        }
    }

    var defaultWorkspaceName: String {
        switch self {
        case .iterative:   return "Untitled Workspace"
        case .rfdiffusion: return "Untitled RFdiffusion3"
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
