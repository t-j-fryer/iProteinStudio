import SwiftUI
import Charts

struct ResourceUsageView: View {
    @ObservedObject var monitor: ResourceUsageMonitor
    @State private var showHistory = false

    private func memory(_ bytes: UInt64?) -> String {
        bytes.map { String(format: "%.1f GiB", Double($0) / 1_073_741_824) } ?? "Unavailable"
    }
    private func percent(_ value: Double?) -> String {
        value.map { String(format: "%.0f%%", $0) } ?? "Unavailable"
    }
    private func cell(_ title: String, _ value: String, detail: String? = nil) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.callout.monospacedDigit()).fontWeight(.medium)
            if let detail { Text(detail).font(.caption2).foregroundStyle(.secondary) }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label("Live resources · this Mac", systemImage: "gauge.with.dots.needle.33percent").font(.headline)
                Spacer()
                if let latest = monitor.latest {
                    TimelineView(.periodic(from: .now, by: 2)) { context in
                        let age = context.date.timeIntervalSince(latest.snapshot.date)
                        Text(age > 10 ? "Reading delayed · \(Int(age))s old" : "Updates every 2 seconds")
                            .font(.caption).foregroundStyle(age > 10 ? .orange : .secondary)
                    }
                }
            }
            if let latest = monitor.latest {
                let s = latest.snapshot
                HStack(alignment: .top, spacing: 12) {
                    cell("RAM used (estimate)", "\(memory(s.usedBytes)) / \(memory(s.totalBytes))",
                         detail: "Compressed: \(memory(s.compressedBytes))")
                    cell("Memory pressure", s.pressure ?? "Unavailable")
                    cell("Swap used", memory(s.swapBytes), detail: latest.swapOutBytesPerSecond.map {
                        String(format: "Writing %.1f MiB/s", $0 / 1_048_576)
                    } ?? "Swap rate: waiting for samples")
                }
                HStack(alignment: .top, spacing: 12) {
                    cell("GPU activity", percent(s.gpuPercent))
                    cell("CPU activity", monitor.samples.count < 2 ? "Measuring…" : percent(latest.cpuPercent))
                    cell("Thermal state", s.thermal)
                }
                if s.pressure == "Warning" || s.pressure == "Critical" {
                    Label("macOS reports elevated memory pressure. Other apps and running models may be competing for memory.", systemImage: "exclamationmark.triangle.fill")
                        .font(.caption).foregroundStyle(s.pressure == "Critical" ? .red : .orange)
                }
                DisclosureGroup("Recent RAM and GPU history", isExpanded: $showHistory) {
                    Chart(monitor.samples) { sample in
                        if let used = sample.snapshot.usedBytes, sample.snapshot.totalBytes > 0 {
                            LineMark(x: .value("Time", sample.snapshot.date),
                                     y: .value("Percent", 100 * Double(used) / Double(sample.snapshot.totalBytes)))
                                .foregroundStyle(by: .value("Metric", "RAM used"))
                        }
                        if let gpu = sample.snapshot.gpuPercent {
                            LineMark(x: .value("Time", sample.snapshot.date), y: .value("Percent", gpu))
                                .foregroundStyle(by: .value("Metric", "GPU activity"))
                        }
                    }.chartYScale(domain: 0...100).chartYAxisLabel("%")
                        .chartForegroundStyleScale(["RAM used": Color.blue, "GPU activity": Color.purple])
                        .frame(height: 100)
                }.font(.caption)
                Text("All apps combined, not just this job. CPU and GPU share RAM on Apple Silicon. Swap can remain allocated after pressure eases. Missing GPU readings mean macOS did not expose the counter.")
                    .font(.caption2).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            } else {
                Text("Reading this Mac’s resources…").font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(10).background(.quaternary, in: RoundedRectangle(cornerRadius: 8))
        .accessibilityIdentifier("live-resource-monitor")
    }
}
