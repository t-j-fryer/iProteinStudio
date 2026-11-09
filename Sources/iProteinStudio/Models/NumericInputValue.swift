import Foundation

/// Strict, locale-aware editing without formatter coercion or prefix parsing.
protocol NumericInputNumber: Comparable {
    static func parseInput(_ text: String, locale: Locale) -> Self?
    var inputString: String { get }
    static var inputDescription: String { get }
}

extension Int: NumericInputNumber {
    static func parseInput(_ text: String, locale: Locale) -> Int? {
        Int(text.trimmingCharacters(in: .whitespacesAndNewlines))
    }
    var inputString: String { String(self) }
    static var inputDescription: String { "a whole number" }
}

extension Double: NumericInputNumber {
    static func parseInput(_ text: String, locale: Locale) -> Double? {
        let decimal = locale.decimalSeparator ?? "."
        let normalized = text.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: decimal, with: ".")
        guard normalized.range(of: #"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$"#,
                               options: .regularExpression) != nil,
              let value = Double(normalized), value.isFinite else { return nil }
        return value
    }
    var inputString: String {
        let text = String(self)
        return text.hasSuffix(".0") ? String(text.dropLast(2)) : text
    }
    static var inputDescription: String { "a finite number" }
}

/// Apply a valid edit immediately. The return value gates submission; invalid
/// text never silently reuses or clamps a previous budget.
enum NumericInputValue {
    static func integerList(_ text: String) -> [Int]? {
        if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return [] }
        let parts = text.split(separator: ",", omittingEmptySubsequences: false)
        let numbers = parts.compactMap { Int($0.trimmingCharacters(in: .whitespacesAndNewlines)) }
        guard numbers.count == parts.count, numbers.allSatisfy({ $0 > 0 }), Set(numbers).count == numbers.count else { return nil }
        return numbers
    }

    @discardableResult
    static func apply(_ text: String, in range: ClosedRange<Int>, update: (Int) -> Void) -> Bool {
        guard let n = Int(text.trimmingCharacters(in: .whitespacesAndNewlines)), range.contains(n) else { return false }
        update(n)
        return true
    }
}
