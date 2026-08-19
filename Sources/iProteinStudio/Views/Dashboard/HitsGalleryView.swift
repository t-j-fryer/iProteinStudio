import SwiftUI

/// Hits split into two sections:
///  • Design hits — cleared the iPTM threshold under the selected design engine.
///  • Validation hits — cleared it under any selected independent checker.
struct HitsGalleryView: View {
    let designHits: [DesignPoint]
    let validationHits: [DesignPoint]
    let threshold: Double

    private let columns = [GridItem(.adaptive(minimum: 190, maximum: 240), spacing: 14)]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                section(
                    title: "Design hits",
                    subtitle: "Passed iPTM ≥ \(String(format: "%.2f", threshold)) under the selected design engine.",
                    hits: designHits,
                    emptyDetail: "Designs that clear the threshold under the design engine will appear here."
                )
                Divider()
                section(
                    title: "Passing independent checks",
                    subtitle: "Passed under a selected checking engine; each tile names the engine that produced it.",
                    hits: validationHits,
                    emptyDetail: "Independent checks run after design finishes. Passing results will appear here."
                )
            }
            .padding(4)
        }
    }

    @ViewBuilder
    private func section(title: String, subtitle: String, hits: [DesignPoint], emptyDetail: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text(title).font(.title3.bold())
                Text("\(hits.count)")
                    .font(.subheadline).monospacedDigit()
                    .padding(.horizontal, 8).padding(.vertical, 1)
                    .background(Capsule().fill(.green.opacity(0.2)))
                    .foregroundStyle(.green)
            }
            Text(subtitle).font(.caption).foregroundStyle(.secondary)
            if hits.isEmpty {
                EmptyHint(text: "None yet", detail: emptyDetail, systemImage: "sparkle.magnifyingglass")
            } else {
                LazyVGrid(columns: columns, spacing: 14) {
                    ForEach(hits.sorted { $0.iptm > $1.iptm }) { hit in
                        DesignTile(point: hit, threshold: threshold, tileHeight: 150)
                    }
                }
            }
        }
    }
}
