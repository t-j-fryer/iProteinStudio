import Foundation

/// Uses the same component/dependency graph as engine admission.
struct EngineRequirementIssue: Identifiable {
    let component: InstallComponent
    let dependencies: [InstallComponent]
    var id: String { component.rawValue }

    static func missing(_ required: [InstallComponent], installed: (InstallComponent) -> Bool) -> [Self] {
        var seen: Set<InstallComponent> = []
        return required.compactMap { component in
            guard seen.insert(component).inserted else { return nil }
            let missing = component.requires.filter { !installed($0) }
            guard !installed(component) || !missing.isEmpty else { return nil }
            return Self(component: component, dependencies: missing)
        }
    }

    static func message(_ issues: [Self]) -> String {
        guard !issues.isEmpty else { return "" }
        return "Install or repair \(issues.map { $0.component.label }.joined(separator: ", ")) in Engines before starting."
    }
}
