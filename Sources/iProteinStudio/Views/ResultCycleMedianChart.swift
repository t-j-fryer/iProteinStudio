import SwiftUI
import Charts

struct ResultCycleMedianChart: View {
    let items: [StudioResultItem]
    let metric: StudioResultMetric.Kind
    var prepared: [ResultAnalysis.CycleMedian]? = nil

    var body: some View {
        let medians = prepared ?? ResultAnalysis.cycleMedians(items: items, metric: metric)
        if let first = medians.map(\.cycle).min(), let last = medians.map(\.cycle).max() {
            let domain = first == last ? (Double(first) - 0.5)...(Double(last) + 0.5) : Double(first)...Double(last)
            VStack(alignment: .leading, spacing: 8) {
                Text("Median \(metric.label) by cycle").font(.headline)
                Text("All scored candidates in this selection; unoptimized starting structures excluded. Lines separate score sources and assessment types. Confidence scores describe predictions, not measured binding.")
                    .font(.caption).foregroundStyle(.secondary)
                Chart(medians) { point in
                    LineMark(x: .value("Cycle", point.cycle), y: .value("Median", point.median))
                        .foregroundStyle(by: .value("Assessment", point.series))
                    PointMark(x: .value("Cycle", point.cycle), y: .value("Median", point.median))
                        .foregroundStyle(by: .value("Assessment", point.series))
                        .accessibilityLabel("\(point.series), cycle \(point.cycle)")
                        .accessibilityValue("Median \(point.median), \(point.count) scored candidates")
                }.chartXScale(domain: domain)
                    .chartXAxis { AxisMarks(values: Array(Set(medians.map(\.cycle))).sorted()) }
                    .chartXAxisLabel("Cycle").chartYAxisLabel(ResultAnalysis.metricLabel(metric))
                    .frame(height: 240)
            }
            .padding(14).background(RoundedRectangle(cornerRadius: 12).fill(.quaternary.opacity(0.20)))
        }
    }
}
