import SwiftUI

/// Compact colon input plus an immediate, unambiguous view of the chain map.
struct ProteinChainInputView: View {
    @Binding var text: String
    let startingAt: Int
    let placeholder: String
    var minimumLength: Int = 1

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            SequenceEditor(text: $text, placeholder: placeholder)
            Text("Separate chains with a colon — for example, SEQUENCE1:SEQUENCE2.")
                .font(.caption2).foregroundStyle(.secondary)
            ProteinChainSummaryView(text: text, startingAt: startingAt,
                                    minimumLength: minimumLength)
        }
    }
}

/// Reusable immediate chain map for fields which also accept batch/FASTA input.
struct ProteinChainSummaryView: View {
    let text: String
    let startingAt: Int
    var minimumLength: Int = 1
    var showsAssignedIDs: Bool = true

    var body: some View {
        Group {
            switch ProteinSequenceInput.parse(text, startingAt: startingAt,
                                               minimumLength: minimumLength) {
            case .success(let chains):
                Label(showsAssignedIDs
                      ? "\(chains.count) chain\(chains.count == 1 ? "" : "s") detected: \(chains.map(\.id).joined(separator: ", "))"
                      : "\(chains.count) partner subunit\(chains.count == 1 ? "" : "s") detected",
                      systemImage: chains.count > 1 ? "link" : "circle")
                    .font(.caption.weight(.medium)).foregroundStyle(.secondary)
                VStack(spacing: 5) {
                    ForEach(Array(chains.enumerated()), id: \.element.id) { index, chain in
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(showsAssignedIDs ? "Chain \(chain.id)" : "Subunit \(index + 1)")
                                .font(.caption.weight(.semibold))
                                .frame(width: 62, alignment: .leading)
                            Text(chain.sequence).font(.system(.caption2, design: .monospaced))
                                .textSelection(.enabled).lineLimit(2)
                            Spacer(minLength: 4)
                            Text("\(chain.sequence.count) aa").font(.caption2.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                        .padding(.horizontal, 8).padding(.vertical, 5)
                        .background(RoundedRectangle(cornerRadius: 6).fill(.quaternary.opacity(0.35)))
                    }
                }
            case .failure(let error):
                if !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Label(error.message, systemImage: "exclamationmark.triangle.fill")
                        .font(.caption).foregroundStyle(.orange)
                }
            }
        }
    }
}
