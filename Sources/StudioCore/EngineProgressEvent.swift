import Foundation

/// A host milestone is not a GPU-completion measurement. Never invent a percent.
public struct EngineProgressEvent: Equatable {
    public let engine: String
    public let event: String
    public let stage: String
    public let pid: String
    public let date: Date?
    public let call: String?
    public let elapsed: String?
    public let sinceProgress: String?

    public init?(line: String) {
        let parts = line.split(separator: "|", omittingEmptySubsequences: false)
        guard parts.first == "IPROTEINSTUDIO_PROGRESS" else { return nil }
        var fields: [String: String] = [:]
        for part in parts.dropFirst() {
            let pair = part.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
            if pair.count == 2 { fields[String(pair[0])] = String(pair[1]) }
        }
        guard let engine = fields["engine"], !engine.isEmpty,
              let event = fields["event"], let stage = fields["stage"],
              ["host_enter", "host_return", "host_error", "heartbeat", "hook_unavailable"].contains(event)
        else { return nil }
        self.engine = engine; self.event = event; self.stage = stage
        pid = fields["pid"] ?? "—"
        date = fields["utc"].flatMap { ISO8601DateFormatter().date(from: $0) }
        call = fields["call"]; elapsed = fields["elapsed_s"]
        sinceProgress = fields["since_host_progress_s"]
    }

    public var stageLabel: String { stage.replacingOccurrences(of: "_", with: " ").capitalized }
    public var logSummary: String {
        var pieces = [engine, stageLabel, explanation]
        if let call { pieces.append("call \(call)") }
        if let elapsed { pieces.append("\(elapsed) s") }
        if let sinceProgress { pieces.append("\(sinceProgress) s since host progress") }
        return pieces.joined(separator: " · ")
    }
    public var explanation: String {
        switch event {
        case "heartbeat": return "Worker heartbeat. Computation progress is unknown."
        case "host_return": return "Model call returned. GPU completion was not measured."
        case "host_error": return "Model call raised an error. See the log below."
        case "hook_unavailable": return "Detailed logging is unavailable for this stage."
        default: return "Execution reached this stage."
        }
    }
}
