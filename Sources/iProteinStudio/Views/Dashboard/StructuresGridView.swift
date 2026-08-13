import SwiftUI

/// Live grid of every design structure: one row per design run, columns by
/// optimization cycle. Both axes scroll. Tiles load lazily.
struct StructuresGridView: View {
    @ObservedObject var metrics: MetricsWatcher
    var threshold: Double

    var body: some View {
        if metrics.designPoints.isEmpty {
            EmptyHint(text: "No structures yet",
                      detail: "Predicted structures appear here as each design cycle completes — one row per run, one column per cycle.",
                      systemImage: "square.grid.3x3")
        } else {
            ScrollView([.vertical]) {
                LazyVStack(alignment: .leading, spacing: 18) {
                    ForEach(metrics.runNumbers, id: \.self) { run in
                        VStack(alignment: .leading, spacing: 6) {
                            HStack(spacing: 6) {
                                Text("Design run \(run)").font(.headline)
                                let hits = metrics.designPoints(forRun: run).filter { $0.iptm >= threshold }.count
                                if hits > 0 {
                                    Text("\(hits) hit\(hits == 1 ? "" : "s")")
                                        .font(.caption2)
                                        .padding(.horizontal, 6).padding(.vertical, 1)
                                        .background(Capsule().fill(.green.opacity(0.2)))
                                        .foregroundStyle(.green)
                                }
                            }
                            ScrollView(.horizontal, showsIndicators: true) {
                                LazyHStack(spacing: 12) {
                                    ForEach(metrics.designPoints(forRun: run)) { p in
                                        DesignTile(point: p, threshold: threshold, tileHeight: 140)
                                            .frame(width: 180)
                                    }
                                }
                                .padding(.vertical, 2)
                            }
                        }
                    }
                }
                .padding(4)
            }
        }
    }
}
