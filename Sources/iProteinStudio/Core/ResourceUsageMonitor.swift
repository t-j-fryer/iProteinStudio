import Foundation
import Combine
import StudioCore

@MainActor
final class ResourceUsageMonitor: ObservableObject {
    struct Sample: Identifiable {
        let id = UUID()
        let snapshot: SystemResourceSnapshot
        let cpuPercent: Double?
        let swapOutBytesPerSecond: Double?
    }
    @Published private(set) var samples: [Sample] = []
    var latest: Sample? { samples.last }

    func refresh() async {
        let snapshot = await Task.detached(priority: .utility) { SystemResourceSnapshot.capture() }.value
        guard !Task.isCancelled else { return }
        let previous = latest?.snapshot
        samples.append(Sample(snapshot: snapshot,
            cpuPercent: SystemResourceSnapshot.cpuUtilization(previous: previous?.cpuTicks, current: snapshot.cpuTicks),
            swapOutBytesPerSecond: SystemResourceSnapshot.swapOutRate(previousBytes: previous?.swapOutBytes,
                currentBytes: snapshot.swapOutBytes, seconds: snapshot.uptime - (previous?.uptime ?? snapshot.uptime))))
        // Five minutes at the nominal two-second interval; strictly bounded.
        if samples.count > 150 { samples.removeFirst(samples.count - 150) }
    }

    var supportText: String {
        guard !samples.isEmpty else { return "Resource readings: not yet sampled.\n" }
        func number(_ value: Double?) -> String { value.map { String(format: "%.2f", $0) } ?? "unavailable" }
        func bytes(_ value: UInt64?) -> String { value.map(String.init) ?? "unavailable" }
        let iso = ISO8601DateFormatter()
        var lines = ["Live resource history: this Mac, all apps; collected only while Job progress is open.",
                     "RAM is an estimate excluding reclaimable file cache; compressed RAM is included in RAM used. GPU is an optional driver counter. CPU is a percentage of total CPU capacity.",
                     "utc\tram_used_bytes\tram_total_bytes\tcompressed_bytes\tpressure\tswap_used_bytes\tswap_out_bytes_per_second\tgpu_percent\tcpu_percent\tthermal"]
        lines += samples.map { sample in
            let s = sample.snapshot
            return [iso.string(from: s.date), bytes(s.usedBytes), String(s.totalBytes), bytes(s.compressedBytes),
                    s.pressure ?? "unavailable", bytes(s.swapBytes), number(sample.swapOutBytesPerSecond),
                    number(s.gpuPercent), number(sample.cpuPercent), s.thermal].joined(separator: "\t")
        }
        return lines.joined(separator: "\n") + "\n"
    }
}
