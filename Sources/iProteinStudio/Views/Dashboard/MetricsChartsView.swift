import SwiftUI
import Charts

/// Live iPTM chart: one point per design, colored by run, with the hit
/// threshold drawn as a rule and the best-so-far trend.
struct MetricsChartsView: View {
    let points: [DesignPoint]
    let threshold: Double

    private var bestSoFar: [DesignPoint] {
        var best = -1.0
        var out: [DesignPoint] = []
        for p in points.sorted(by: { ($0.run, $0.cycle) < ($1.run, $1.cycle) }) {
            if p.iptm > best { best = p.iptm; out.append(p) }
        }
        return out
    }

    var body: some View {
        Chart {
            ForEach(points) { p in
                PointMark(
                    x: .value("Cycle", p.cycle),
                    y: .value("iPTM", p.iptm)
                )
                .foregroundStyle(by: .value("Run", "run \(p.run)"))
                .symbolSize(p.iptm >= threshold ? 90 : 40)
                .opacity(p.iptm >= threshold ? 1.0 : 0.55)
            }
            RuleMark(y: .value("Hit threshold", threshold))
                .foregroundStyle(.green.opacity(0.8))
                .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [6, 4]))
                .annotation(position: .top, alignment: .leading) {
                    Text("hit ≥ \(String(format: "%.2f", threshold))")
                        .font(.caption2).foregroundStyle(.green)
                }
        }
        .chartYScale(domain: 0...1)
        .chartYAxisLabel("iPTM")
        .chartXAxisLabel("Optimization cycle")
        .chartLegend(position: .trailing, alignment: .top)
        .frame(minHeight: 240)
    }
}

private func < (lhs: (Int, Int), rhs: (Int, Int)) -> Bool {
    lhs.0 != rhs.0 ? lhs.0 < rhs.0 : lhs.1 < rhs.1
}
