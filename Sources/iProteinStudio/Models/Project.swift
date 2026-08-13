import Foundation

/// A design campaign. Each project owns an output directory under the app's
/// managed `projects/` folder.
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
    /// Slug used as the on-disk folder name and pipeline --run-name.
    var slug: String

    init(name: String) {
        self.name = name
        self.slug = Project.slugify(name)
    }

    private enum CodingKeys: String, CodingKey { case id, name, createdAt, request, rfd3, prediction, slug }

    /// Resilient decoding so schema changes never drop saved projects.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        name = try c.decodeIfPresent(String.self, forKey: .name) ?? "Untitled Design"
        createdAt = try c.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
        request = try c.decodeIfPresent(DesignRequest.self, forKey: .request) ?? DesignRequest()
        rfd3 = try c.decodeIfPresent(RFD3Request.self, forKey: .rfd3) ?? RFD3Request()
        prediction = try c.decodeIfPresent(PredictionRequest.self, forKey: .prediction) ?? PredictionRequest()
        slug = try c.decodeIfPresent(String.self, forKey: .slug) ?? Project.slugify(name)
    }

    static func slugify(_ s: String) -> String {
        let allowed = CharacterSet.alphanumerics
        let mapped = s.lowercased().unicodeScalars.map { allowed.contains($0) ? Character($0) : "_" }
        var slug = String(mapped)
        while slug.contains("__") { slug = slug.replacingOccurrences(of: "__", with: "_") }
        slug = slug.trimmingCharacters(in: CharacterSet(charactersIn: "_"))
        return slug.isEmpty ? "project" : slug
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
