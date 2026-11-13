import Foundation

/// Bounds native controls/card allocation while preserving the full export set.
struct ResultPage {
    static let size = 25
    let count: Int
    let number: Int
    var pageCount: Int { max(1, (count + Self.size - 1) / Self.size) }
    var range: Range<Int> {
        let start = min(count, number * Self.size)
        return start..<min(count, start + Self.size)
    }
    init(count: Int, requested: Int) {
        self.count = max(0, count)
        number = min(max(0, requested), max(0, (max(0, count) - 1) / Self.size))
    }
}
