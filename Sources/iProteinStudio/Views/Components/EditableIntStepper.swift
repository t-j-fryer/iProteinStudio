import SwiftUI

/// Valid edits update the request in the TextField setter, before a Run click.
/// Invalid edits stay visible and block submission instead of silently clamping.
struct EditableIntStepper: View {
    @Binding private var value: Int
    let range: ClosedRange<Int>
    let step: Int
    let suffix: String
    let accessibilityLabel: String
    let showsStepper: Bool
    init(value: Binding<Int>, in range: ClosedRange<Int>, step: Int = 1,
         suffix: String = "", accessibilityLabel: String, showsStepper: Bool = true) {
        _value = value; self.range = range; self.step = max(1, step)
        self.suffix = suffix; self.accessibilityLabel = accessibilityLabel
        self.showsStepper = showsStepper
    }
    var body: some View {
        HStack(alignment: .top, spacing: 5) {
            NumericTextField(accessibilityLabel, value: $value, in: range)
                .multilineTextAlignment(.trailing).frame(width: 76)
            if !suffix.isEmpty { Text(suffix).foregroundStyle(.secondary) }
            if showsStepper {
                Stepper("", value: $value, in: range, step: step)
                    .labelsHidden().fixedSize().accessibilityLabel("Adjust \(accessibilityLabel)")
            }
        }
    }
}
