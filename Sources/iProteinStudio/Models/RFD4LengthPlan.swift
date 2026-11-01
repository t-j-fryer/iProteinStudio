import Foundation

/// Frozen allocation, one independent family per requested start. Counts are
/// interleaved so a time-limited campaign does not exhaust one length first.
struct RFD4LengthPlan: Codable, Hashable {
    var minimum = 75
    var maximum = 120
    var counts: [String: Int]?
    func issues(count: Int) -> [String] {
        guard (1...2000).contains(minimum), (minimum...2000).contains(maximum) else { return ["Choose an increasing length range from 1 to 2,000 residues."] }
        if let counts {
            guard !counts.isEmpty, counts.allSatisfy({ key, value in
                guard let length = Int(key) else { return false }
                return String(length) == key && (minimum...maximum).contains(length) && (1...10000).contains(value)
            }), counts.values.reduce(0, +) == count else { return ["Custom length counts must be positive, within the range, and add up to the family count."] }
        }
        return []
    }
    func lengths(count: Int) -> [Int] {
        guard (1...10000).contains(count), issues(count: count).isEmpty else { return [] }
        if let counts {
            var left = Dictionary(uniqueKeysWithValues: counts.map { (Int($0.key)!, $0.value) })
            let keys = left.keys.sorted()
            var values: [Int] = []
            while values.count < count {
                for key in keys where left[key, default: 0] > 0 { values.append(key); left[key]! -= 1 }
            }
            return values
        }
        let span = maximum - minimum + 1
        if count < span {
            if count == 1 { return [(minimum + maximum) / 2] }
            return (0..<count).map { minimum + Int((Double($0 * (maximum - minimum)) / Double(count - 1)).rounded()) }
        }
        return (0..<count).map { minimum + $0 % span }
    }
}
