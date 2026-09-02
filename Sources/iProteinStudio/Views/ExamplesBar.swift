import SwiftUI

/// Offers the worked examples at the top of a tab.
///
/// A new user with no target of their own otherwise has nothing to press. Both
/// examples are real: α-cobratoxin is an antivenom target and ships with its
/// alignment already generated, so pressing one of these does not begin with a
/// wait on a public server.
struct ExamplesBar: View {
    /// Only examples this tab can actually use.
    var kinds: Set<ExampleTarget.Kind> = [.protein, .smallMolecule]
    var onPick: (ExampleTarget) -> Void

    private var available: [ExampleTarget] {
        ExampleTarget.all.filter { kinds.contains($0.kind) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Try an example", systemImage: "sparkles")
                .font(.callout.weight(.medium))
            HStack(alignment: .top, spacing: 10) {
                ForEach(available) { example in
                    Button { onPick(example) } label: {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(example.name).font(.callout.weight(.medium))
                            Text(example.subtitle).font(.caption2).foregroundStyle(.secondary)
                            Text(example.goodFor).font(.caption2).foregroundStyle(.tertiary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                    }
                    .buttonStyle(.plain)
                    .background(RoundedRectangle(cornerRadius: 8).fill(.quaternary.opacity(0.35)))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("Try the \(example.name) example")
                    .accessibilityHint(example.goodFor)
                    .accessibilityIdentifier("example-\(example.id)")
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 10).fill(.tint.opacity(0.06)))
    }
}

/// A compact mode-specific companion to ``ExamplesBar`` for workflows that
/// need a complete starting complex rather than only a target.
struct RFD3WorkflowExamplesBar: View {
    var mode: RFD3DesignMode
    var onPick: (RFD3WorkflowExample) -> Void

    private var available: [RFD3WorkflowExample] {
        RFD3WorkflowExample.examples(for: mode)
    }

    var body: some View {
        if !available.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Label("Try a worked \(mode.label.lowercased()) example", systemImage: "sparkles")
                    .font(.callout.weight(.medium))
                ForEach(available) { example in
                    Button { onPick(example) } label: {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(example.name).font(.callout.weight(.medium))
                            Text(example.subtitle).font(.caption2).foregroundStyle(.secondary)
                            Text(example.goodFor).font(.caption2).foregroundStyle(.tertiary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                    }
                    .buttonStyle(.plain)
                    .background(RoundedRectangle(cornerRadius: 8).fill(.quaternary.opacity(0.35)))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("Try the \(example.name) example")
                    .accessibilityHint(example.goodFor)
                    .accessibilityIdentifier("example-\(example.id)")
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 10).fill(.tint.opacity(0.06)))
        }
    }
}
