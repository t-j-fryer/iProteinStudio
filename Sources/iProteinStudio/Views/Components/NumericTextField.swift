import SwiftUI

/// Synchronously tracks invalid editors so Start cannot submit an older value.
final class NumericInputValidation: ObservableObject {
    @Published private(set) var invalidEditors: Set<UUID> = []
    func update(_ id: UUID, valid: Bool) {
        if valid { invalidEditors.remove(id) } else { invalidEditors.insert(id) }
    }
}

/// Exact length lists also keep a draft, including an unfinished trailing comma.
struct IntegerListTextField: View {
    let title: String
    @Binding var values: [Int]
    @Environment(\.numericInputValidation) private var validation
    @State private var editorID = UUID()
    @State private var draft: String

    init(_ title: String, values: Binding<[Int]>) {
        self.title = title; _values = values
        _draft = State(initialValue: values.wrappedValue.map(String.init).joined(separator: ","))
    }
    private var parsed: [Int]? { NumericInputValue.integerList(draft) }
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            TextField(title, text: Binding(get: { draft }, set: { text in
                draft = text
                validation?.update(editorID, valid: parsed != nil)
                if let parsed { values = parsed }
            })).textFieldStyle(.roundedBorder).accessibilityLabel(title)
            if parsed == nil { Text("Enter distinct positive lengths separated by commas, or clear to use the range.").font(.caption).foregroundStyle(.red) }
        }
        .onAppear { validation?.update(editorID, valid: parsed != nil) }
        .onDisappear { validation?.update(editorID, valid: true) }
        .onChange(of: values) { _, new in
            if parsed != new { draft = new.map(String.init).joined(separator: ",") }
            validation?.update(editorID, valid: parsed != nil)
        }
    }
}
private struct NumericInputValidationKey: EnvironmentKey {
    static let defaultValue: NumericInputValidation? = nil
}
extension EnvironmentValues {
    var numericInputValidation: NumericInputValidation? {
        get { self[NumericInputValidationKey.self] }
        set { self[NumericInputValidationKey.self] = newValue }
    }
}


/// Keeps unfinished edits visible; only complete valid numbers reach the model.
/// A required blank blocks Start. An optional blank explicitly disables its gate.
struct NumericTextField<Value: NumericInputNumber>: View {
    let title: String
    @Binding private var value: Value?
    private let allowsEmpty: Bool
    private let range: ClosedRange<Value>?
    @Environment(\.locale) private var locale
    @Environment(\.numericInputValidation) private var validation
    @State private var editorID = UUID()
    @State private var draft: String

    init(_ title: String, value: Binding<Value>, in range: ClosedRange<Value>? = nil) {
        self.title = title; self.range = range; allowsEmpty = false
        _value = Binding(get: { value.wrappedValue }, set: { if let n = $0 { value.wrappedValue = n } })
        _draft = State(initialValue: value.wrappedValue.inputString)
    }

    init(_ title: String, value: Binding<Value?>, in range: ClosedRange<Value>? = nil) {
        self.title = title; self.range = range; allowsEmpty = true
        _value = value
        _draft = State(initialValue: value.wrappedValue?.inputString ?? "")
    }

    private var parsed: Value? { Value.parseInput(draft, locale: locale) }
    private var valid: Bool {
        if draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return allowsEmpty }
        guard let parsed else { return false }
        return range?.contains(parsed) ?? true
    }
    private func display(_ value: Value?) -> String {
        (value?.inputString ?? "").replacingOccurrences(of: ".", with: locale.decimalSeparator ?? ".")
    }
    private func edit(_ text: String) {
        draft = text
        let accepted = valid
        validation?.update(editorID, valid: accepted)
        if accepted { value = parsed }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            TextField(title, text: Binding(get: { draft }, set: edit))
                .textFieldStyle(.roundedBorder).monospacedDigit()
                .accessibilityLabel(title)
            if !valid {
                Text("Enter \(Value.inputDescription)\(range.map { " from \($0.lowerBound.inputString) to \($0.upperBound.inputString)" } ?? "").")
                    .font(.caption).foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .onAppear {
            draft = display(value)
            validation?.update(editorID, valid: valid)
        }
        .onDisappear { validation?.update(editorID, valid: true) }
        .onChange(of: range) { _, _ in validation?.update(editorID, valid: valid) }
        .onChange(of: value) { _, new in
            // Keep '1.', '01' and an unfinished edit through unrelated renders.
            // Explicit presets and other external model changes still refresh it.
            if parsed != new { draft = display(new) }
            validation?.update(editorID, valid: valid)
        }
    }
}
