import Foundation

/// A workspace for prediction, iterative design, RFdiffusion3, or any
/// combination of them. The historical `Project` type and on-disk `projects/`
/// directory remain unchanged so existing users need no migration.
struct Project: Identifiable, Codable, Hashable {
    var id: UUID = UUID()
    var name: String
    var createdAt: Date = Date()
    var request: DesignRequest = DesignRequest()
    /// RFdiffusion3 settings for this project. Kept alongside the iterative
    /// design request rather than in a separate project type, so a target can be
    /// approached both ways without re-entering it.
    var rfd3: RFD3Request = RFD3Request()
    /// Prediction-only batches for this project.
    var prediction: PredictionRequest = PredictionRequest()
    /// The workflow this workspace reopens to. This is presentation state, not
    /// a restriction: every workspace always offers all workflows.
    var preferredMode: WorkspaceMode = .iterative
    /// Slug used as the on-disk folder name and pipeline --run-name.
    var slug: String

    init(name: String, preferredMode: WorkspaceMode = .iterative) {
        self.name = name
        self.preferredMode = preferredMode
        self.slug = Project.slugify(name)
    }

    private enum CodingKeys: String, CodingKey {
        case id, name, createdAt, request, rfd3, prediction, preferredMode, slug
    }

    /// Resilient decoding so schema changes never drop saved projects.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        name = try c.decodeIfPresent(String.self, forKey: .name) ?? "Untitled Workspace"
        createdAt = try c.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
        request = try c.decodeIfPresent(DesignRequest.self, forKey: .request) ?? DesignRequest()
        rfd3 = try c.decodeIfPresent(RFD3Request.self, forKey: .rfd3) ?? RFD3Request()
        prediction = try c.decodeIfPresent(PredictionRequest.self, forKey: .prediction) ?? PredictionRequest()
        preferredMode = try c.decodeIfPresent(WorkspaceMode.self, forKey: .preferredMode) ?? .iterative
        slug = try c.decodeIfPresent(String.self, forKey: .slug) ?? Project.slugify(name)
    }

    static func slugify(_ s: String) -> String {
        WorkspaceNaming.slugify(s)
    }

    /// Short, truthful sidebar copy. `preferredMode` covers a new/empty
    /// workspace; configured inputs add any other workflows already used here.
    var workflowSummary: String {
        var modes: [WorkspaceMode] = [preferredMode]
        let iterativeConfigured = !request.targetSequence.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || !request.targetSmiles.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        let rfd3Configured = !rfd3.targetSequence.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || !rfd3.targetStructurePath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || !rfd3.smiles.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        let predictionConfigured = !prediction.pastedSequences.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || !prediction.sequenceFile.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || !prediction.jobs.isEmpty

        if iterativeConfigured, !modes.contains(.iterative) { modes.append(.iterative) }
        if rfd3Configured, !modes.contains(.rfdiffusion) { modes.append(.rfdiffusion) }
        if predictionConfigured, !modes.contains(.predict) { modes.append(.predict) }
        return modes.map(\.label).joined(separator: " · ")
    }
}

/// Lifecycle of a running / installed pipeline.
enum RunPhase: Equatable {
    case idle
    case running
    case finished
    case failed(String)
    case cancelled
}
