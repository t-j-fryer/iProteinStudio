import Foundation

/// Support exports use an allowlist. Raw errors/logs may contain unpublished
/// sequences, paths, SMILES or credentials; guessing regex redactions is unsafe.
public enum SupportReport {
    public static func make(version: String, system: String, memoryBytes: UInt64,
                            message: String, log: [String]) -> String {
        let lower = message.lowercased()
        let category: String
        if lower.contains("space") || lower.contains("write") || lower.contains("saved") { category = "Storage or saved settings" }
        else if lower.contains("msa") || lower.contains("alignment") { category = "Alignment preparation" }
        else if lower.contains("engine") || lower.contains("weight") || lower.contains("checkpoint is missing") { category = "Engine availability" }
        else if lower.contains("digest") || lower.contains("provenance") { category = "Recorded workflow provenance" }
        else { category = "Workflow needs attention" }
        let markers = ["PBFAIL", "RFFAIL", "NHFAIL", "PREPFAIL"].filter { marker in
            log.contains { $0.hasPrefix(marker + "|") }
        }
        return """
        iProteinStudio support report
        Version: \(version)
        System: \(system)
        Physical memory: \(memoryBytes / 1_073_741_824) GiB
        Category: \(category)
        Failure markers: \(markers.isEmpty ? "none recorded" : markers.joined(separator: ", "))

        This report includes no sequences, structures, paths, credentials or raw log text.
        Describe the action you were taking when requesting support.
        """
    }
}
