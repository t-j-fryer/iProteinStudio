import Foundation

/// Atomic, validated persistence. An unreadable primary is never treated as an
/// empty library, and saving cannot overwrite one until recovery succeeds.
public final class RecoverableJSONStore<Value: Codable> {
    public let url: URL
    public var backupURL: URL { url.appendingPathExtension("previous") }
    public init(url: URL) { self.url = url }

    public func load() throws -> Value? {
        guard FileManager.default.fileExists(atPath: url.path) else {
            if FileManager.default.fileExists(atPath: backupURL.path) {
                throw StoreError.recoveryRequired
            }
            return nil
        }
        return try JSONDecoder().decode(Value.self, from: Data(contentsOf: url))
    }

    /// Keep the damaged bytes for diagnosis, then restore the last valid copy.
    public func recover() throws -> Value {
        let data = try Data(contentsOf: backupURL)
        let value = try JSONDecoder().decode(Value.self, from: data)
        if FileManager.default.fileExists(atPath: url.path) {
            try FileManager.default.copyItem(at: url, to: url.appendingPathExtension("unreadable-\(UUID().uuidString)"))
        }
        try data.write(to: url, options: .atomic)
        return value
    }

    public func save(_ value: Value) throws {
        let data = try encoded(value)
        // A missing primary with a surviving backup also requires recovery.
        _ = try load()
        if FileManager.default.fileExists(atPath: url.path) {
            try Data(contentsOf: url).write(to: backupURL, options: .atomic)
        }
        try data.write(to: url, options: .atomic)
    }

    public func encoded(_ value: Value) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return try encoder.encode(value)
    }

    public enum StoreError: LocalizedError {
        case recoveryRequired
        public var errorDescription: String? { "The workspace index needs recovery from its previous copy." }
    }
}
