import Foundation

enum ResultFileStamp {
    static func read(_ url: URL) -> String? {
        // URL resource values can remain cached after a pose is replaced.
        guard let values = try? FileManager.default.attributesOfItem(atPath: url.path),
              let size = values[.size] as? NSNumber, let date = values[.modificationDate] as? Date else { return nil }
        return "\(size.int64Value)|\(date.timeIntervalSince1970)"
    }
}
