// Exercise production SwiftUI text controls in a standalone synthetic window.
// Does not load AppState, preferences, workspace files, engines or the broker.
import AppKit
import SwiftUI

// Ancillary model type required by Predictor; no runtime or engine is created.
enum IntelliFoldModel: String, Codable, Hashable { case v2flash = "v2-flash", v2 }

@MainActor final class NumericFixture: ObservableObject {
    @Published var length = 75
    @Published var minutes = 60.0
    @Published var optionalCutoff: Double? = 0.5
    @Published var showCutoff = true
    @Published var exactLengths = [60, 70]
    @Published var other = 0
    @Published var submissions = 0
}
// Native probe for SwiftUI's submission enabled state; no production controller.
struct FixtureSubmitButton: NSViewRepresentable {
    @Environment(\.isEnabled) private var enabled
    let action: () -> Void
    final class Coordinator: NSObject {
        var action: () -> Void
        init(_ action: @escaping () -> Void) { self.action = action }
        @objc func submit(_ sender: NSButton) { if sender.isEnabled { action() } }
    }
    func makeCoordinator() -> Coordinator { Coordinator(action) }
    func makeNSView(context: Context) -> NSButton {
        NSButton(title: "Submit fixture", target: context.coordinator, action: #selector(Coordinator.submit(_:)))
    }
    func updateNSView(_ view: NSButton, context: Context) {
        view.isEnabled = enabled; context.coordinator.action = action
    }
}
struct NumericFixtureView: View {
    @ObservedObject var model: NumericFixture
    @ObservedObject var validation: NumericInputValidation
    var body: some View {
        VStack {
            EditableIntStepper(value: $model.length, in: 1...2000, accessibilityLabel: "Binder length")
            NumericTextField("Minutes", value: $model.minutes)
            if model.showCutoff { NumericTextField("Optional cutoff", value: $model.optionalCutoff) }
            IntegerListTextField("Exact lengths", values: $model.exactLengths)
            Text("Unrelated render \(model.other)")
            FixtureSubmitButton { model.submissions += 1 }.disabled(!validation.invalidEditors.isEmpty)
        }.padding(20).environment(\.numericInputValidation, validation).environment(\.locale, Locale(identifier: "en_US"))
    }
}
@main struct NumericEntryHarness {
    @MainActor static func main() {
        let en = Locale(identifier: "en_US"), de = Locale(identifier: "de_DE")
        for invalid in ["", "+", "-", ".", "1e", "1e+", "NaN", "inf", "1e999", "1.2x", "1,000"] {
            precondition(Double.parseInput(invalid, locale: en) == nil, invalid)
        }
        precondition(Double.parseInput("-0.25", locale: en) == -0.25)
        precondition(Double.parseInput("1e-8", locale: en) == 1e-8)
        precondition(Double.parseInput("1,25", locale: de) == 1.25)
        precondition(Int.parseInput("999999999999999999999", locale: en) == nil)
        let available: Set<InstallComponent> = [.rfd4, .esmfold2Full]
        let issues = EngineRequirementIssue.missing([.rfd4, .esmfold2Full, .boltzAffinity, .rfd4]) { available.contains($0) }
        precondition(issues.map(\.component) == [.esmfold2Full, .boltzAffinity])
        precondition(issues[0].dependencies == [.esmfold2] && issues[1].dependencies == [.boltz])
        precondition(EngineRequirementIssue.message(issues).contains("ESMFold2 Full MLX"))
        precondition(EngineRequirementIssue.message(issues).contains("Boltz-2 binding-affinity checkpoint"))
        precondition(EngineRequirementIssue.missing([.rfd4]) { _ in true }.isEmpty)
        precondition(EngineRequirementIssue.missing([.rfd4]) { _ in false }.map(\.component) == [.rfd4])
        let app = NSApplication.shared; app.setActivationPolicy(.accessory)
        let model = NumericFixture(), validation = NumericInputValidation()
        let root = NSHostingView(rootView: NumericFixtureView(model: model, validation: validation))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 520, height: 400),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.title = "Numeric entry test — synthetic values"
        window.contentView = root; window.makeKeyAndOrderFront(nil)
        app.activate(ignoringOtherApps: true)
        func settle() { RunLoop.current.run(until: Date().addingTimeInterval(0.1)) }
        func fields(_ view: NSView) -> [NSTextField] {
            (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(fields)
        }
        func buttons(_ view: NSView) -> [NSButton] {
            (view as? NSButton).map { [$0] } ?? view.subviews.flatMap(buttons)
        }
        settle()
        let submit = buttons(root).first { $0.title == "Submit fixture" }!
        precondition(submit.isEnabled)
        let inputs = fields(root).filter(\.isEditable)
        precondition(inputs.count == 4, "Expected four native numeric text fields, found \(inputs.count)")
        func field(_ label: String) -> NSTextField {
            inputs.first { $0.placeholderString == label || $0.accessibilityLabel() == label }!
        }
        func replace(_ input: NSTextField, _ text: String) {
            window.makeFirstResponder(input); settle()
            let editor = input.currentEditor() as! NSTextView
            editor.setSelectedRange(NSRange(location: 0, length: (editor.string as NSString).length))
            if text.isEmpty { editor.deleteBackward(nil) } else { editor.insertText(text, replacementRange: editor.selectedRange()) }
            settle()
        }
        let length = field("Binder length")
        replace(length, "")
        precondition(length.stringValue.isEmpty && model.length == 75 && !validation.invalidEditors.isEmpty)
        precondition(!submit.isEnabled)
        submit.performClick(nil); settle()
        precondition(model.submissions == 0, "Invalid draft submitted a stale numeric value")
        model.other += 1; settle()
        precondition(length.stringValue.isEmpty, "Unrelated render restored a deleted value")
        window.makeFirstResponder(nil); settle()
        precondition(length.stringValue.isEmpty && !validation.invalidEditors.isEmpty, "Blur restored the old value")
        replace(length, "120")
        precondition(model.length == 120 && validation.invalidEditors.isEmpty, "Replacement did not commit before Return/blur")
        precondition(submit.isEnabled)
        submit.performClick(nil); settle()
        precondition(model.submissions == 1)
        replace(length, "2001")
        precondition(model.length == 120 && !validation.invalidEditors.isEmpty)
        replace(length, "90")
        precondition(model.length == 90 && validation.invalidEditors.isEmpty)
        let minutes = field("Minutes")
        replace(minutes, "")
        precondition(minutes.stringValue.isEmpty && model.minutes == 60 && !validation.invalidEditors.isEmpty)
        replace(minutes, "-")
        precondition(minutes.stringValue == "-" && !validation.invalidEditors.isEmpty)
        replace(minutes, "1.")
        precondition(minutes.stringValue == "1." && model.minutes == 1 && validation.invalidEditors.isEmpty)
        replace(minutes, "1.25")
        precondition(model.minutes == 1.25 && validation.invalidEditors.isEmpty)
        replace(minutes, "1e")
        precondition(minutes.stringValue == "1e" && !validation.invalidEditors.isEmpty)
        replace(minutes, "1e2")
        precondition(model.minutes == 100 && validation.invalidEditors.isEmpty)
        let cutoff = field("Optional cutoff")
        replace(cutoff, "")
        precondition(model.optionalCutoff == nil && validation.invalidEditors.isEmpty)
        replace(cutoff, "0.75")
        precondition(model.optionalCutoff == 0.75 && validation.invalidEditors.isEmpty)
        let exact = field("Exact lengths")
        replace(exact, "60,")
        precondition(exact.stringValue == "60," && model.exactLengths == [60, 70] && !validation.invalidEditors.isEmpty)
        replace(exact, "60,80")
        precondition(model.exactLengths == [60, 80] && validation.invalidEditors.isEmpty)
        replace(exact, "60,60")
        precondition(model.exactLengths == [60, 80] && !validation.invalidEditors.isEmpty)
        replace(exact, "")
        precondition(model.exactLengths.isEmpty && validation.invalidEditors.isEmpty)
        model.minutes = 25; settle()
        precondition(minutes.stringValue == "25", "External preset did not refresh the draft")
        replace(cutoff, "--")
        precondition(!validation.invalidEditors.isEmpty)
        model.showCutoff = false; settle()
        precondition(validation.invalidEditors.isEmpty && submit.isEnabled, "Removed field left a stale submission blocker")
        window.orderOut(nil)
        print("PASS native numeric clear/replace, blur/rerender, partial decimal/exponent, optional clear, range rejection, presets and engine/dependency warnings")
    }
}
