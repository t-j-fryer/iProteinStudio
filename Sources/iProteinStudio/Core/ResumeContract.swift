import Foundation

/// Operational arguments added when the user explicitly asks Studio to resume.
/// Scientific settings remain exactly as recorded in `studio_run.json`.
enum ResumeContract {
    static func arguments(from recorded: [String]) -> [String] {
        var arguments = recorded.filter { $0 != "--resume" }
        arguments.append("--resume")
        return arguments
    }
}
