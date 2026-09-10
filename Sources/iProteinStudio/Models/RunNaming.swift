import Foundation

/// A human label is metadata, never a filesystem path or a pipeline identifier.
enum RunNaming {
    static func normalized(_ value: String) -> String {
        String(value.split(whereSeparator: { $0.isWhitespace || $0.isNewline }).joined(separator: " ").prefix(120))
    }

    static func write(_ value: String, to root: URL) throws {
        let name = normalized(value)
        guard !name.isEmpty else { return }
        try JSONEncoder().encode(["name": name])
            .write(to: root.appendingPathComponent("studio_run_label.json"), options: .atomic)
    }

    static func read(at root: URL, fallback: String) -> String {
        guard let data = try? Data(contentsOf: root.appendingPathComponent("studio_run_label.json")),
              let label = try? JSONDecoder().decode([String: String].self, from: data),
              let name = label["name"], !normalized(name).isEmpty else { return fallback }
        return normalized(name)
    }
}
