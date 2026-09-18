import SwiftUI
import AppKit

/// Synchronously tracks invalid editors so Start cannot submit an older value.
final class NumericInputValidation: ObservableObject {
    @Published private(set) var invalidEditors: Set<UUID> = []
    func update(_ id: UUID, valid: Bool) {
        if valid { invalidEditors.remove(id) } else { invalidEditors.insert(id) }
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

/// Valid edits update the request in the TextField setter, before a Run click.
/// Invalid edits stay visible and block submission instead of silently clamping.
struct EditableIntStepper: View {
    @Binding private var value: Int
    let range: ClosedRange<Int>
    let step: Int
    let suffix: String
    let accessibilityLabel: String
    @Environment(\.numericInputValidation) private var validation
    @State private var editorID = UUID()
    @State private var draft: String
    @FocusState private var isFocused: Bool

    init(value: Binding<Int>, in range: ClosedRange<Int>, step: Int = 1,
         suffix: String = "", accessibilityLabel: String) {
        _value = value; self.range = range; self.step = max(1, step)
        self.suffix = suffix; self.accessibilityLabel = accessibilityLabel
        _draft = State(initialValue: String(value.wrappedValue))
    }
    private var parsed: Int? {
        guard let n = Int(draft.trimmingCharacters(in: .whitespacesAndNewlines)), range.contains(n) else { return nil }
        return n
    }
    private func edit(_ text: String) {
        draft = text
        let valid = NumericInputValue.apply(text, in: range) { value = $0 }
        validation?.update(editorID, valid: valid)
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 5) {
                TextField(accessibilityLabel, text: Binding(get: { draft }, set: edit))
                    .textFieldStyle(.roundedBorder).multilineTextAlignment(.trailing)
                    .monospacedDigit().frame(width: 76).focused($isFocused)
                    .accessibilityLabel(accessibilityLabel)
                if !suffix.isEmpty { Text(suffix).foregroundStyle(.secondary) }
                Stepper("", value: Binding(get: { value }, set: { edit(String($0)) }), in: range, step: step)
                    .labelsHidden().fixedSize().accessibilityLabel("Adjust \(accessibilityLabel)")
            }
            if parsed == nil {
                Text("Enter a whole number from \(range.lowerBound) to \(range.upperBound).")
                    .font(.caption).foregroundStyle(.red)
            }
        }
        .onAppear { validation?.update(editorID, valid: parsed != nil) }
        .onDisappear { validation?.update(editorID, valid: true) }
        .onChange(of: range) { _, _ in validation?.update(editorID, valid: parsed != nil) }
        .onChange(of: value) { _, n in
            if !isFocused { draft = String(n); validation?.update(editorID, valid: parsed != nil) }
        }
    }
}

enum SetupExperience: String, CaseIterable, Identifiable {
    case quick = "Quick setup"
    case advanced = "Advanced"
    var id: String { rawValue }
}

struct SetupExperiencePicker: View {
    @Binding var selection: SetupExperience

    var body: some View {
        HStack(spacing: 12) {
            Picker("Setup detail", selection: $selection) {
                ForEach(SetupExperience.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .frame(width: 260)
            .accessibilityIdentifier("setup-experience-picker")
            Text(selection == .quick
                 ? "Keeps the workspace's current settings and shows only the decisions needed to start."
                 : "Inspect model, alignment, sampling, and throughput controls.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color.accentColor.opacity(0.07)))
    }
}

/// Leads with what failed and what the user can do. Technical output remains
/// available, but it no longer competes with the recovery action.
struct ActionableErrorCard: View {
    let title: String
    let message: String
    var retryTitle: String = "Retry"
    var retry: (() -> Void)?
    var output: URL?
    var log: [String] = []
    @State private var showDetails = false
    @State private var showSupport = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: "exclamationmark.triangle.fill")
                .font(.headline).foregroundStyle(.orange)
            Text(message).font(.callout).textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
            HStack {
                if let retry {
                    Button(retryTitle, action: retry)
                        .buttonStyle(.borderedProminent)
                }
                if let output {
                    Button { NSWorkspace.shared.activateFileViewerSelecting([output]) } label: {
                        Label("Reveal output", systemImage: "folder")
                    }
                }
                if !log.isEmpty {
                    Button(showDetails ? "Hide technical log" : "Show technical log") {
                        withAnimation(reduceMotion ? nil : .default) { showDetails.toggle() }
                    }
                }
                Button("Export support report…") { showSupport = true }
            }
            if showDetails, !log.isEmpty {
                ScrollView {
                    Text(log.suffix(120).joined(separator: "\n"))
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                }
                .frame(maxHeight: 180)
                .background(RoundedRectangle(cornerRadius: 8).fill(.background))
            }
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: 12).fill(Color.orange.opacity(0.09)))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.orange.opacity(0.25)))
        .accessibilityElement(children: .contain)
        .accessibilityLabel("\(title). \(message)")
        .sheet(isPresented: $showSupport) { SupportReportView(message: message, log: log) }
    }
}

struct TechnicalLogDisclosure: View {
    let lines: [String]
    @State private var expanded = false

    var body: some View {
        DisclosureGroup("Technical log", isExpanded: $expanded) {
            ScrollView {
                Text(lines.suffix(200).joined(separator: "\n"))
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.secondary).textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(8)
            }
            .frame(maxHeight: 220)
            .background(RoundedRectangle(cornerRadius: 8).fill(.background))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
        }
        .font(.callout)
    }
}
