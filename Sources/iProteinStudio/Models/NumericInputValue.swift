import Foundation

/// Apply a valid edit immediately. The return value gates submission; invalid
/// text never silently reuses or clamps a previous budget.
enum NumericInputValue {
    @discardableResult
    static func apply(_ text: String, in range: ClosedRange<Int>, update: (Int) -> Void) -> Bool {
        guard let n = Int(text.trimmingCharacters(in: .whitespacesAndNewlines)), range.contains(n) else { return false }
        update(n)
        return true
    }
}
