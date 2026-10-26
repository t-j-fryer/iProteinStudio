import SwiftUI

struct MemoryPolicyControl: View {
    @AppStorage("overrideMemoryCheck") private var overrideMemoryCheck = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Toggle("Override memory check for new runs", isOn: $overrideMemoryCheck)
            Text(overrideMemoryCheck
                 ? "Runs may proceed even when memory is insufficient or the estimate is unavailable. Your choice and sampled usage are saved with each job."
                 : "Memory checks are enabled. You can override them to run an uncalibrated workload.")
                .font(.caption).foregroundStyle(overrideMemoryCheck ? Color.orange : Color.secondary)
            Text("Applies across Studio. Queued and resumed jobs keep their saved choice.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .accessibilityIdentifier("memory-policy-control")
    }
}
