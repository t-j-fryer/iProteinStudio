import SwiftUI

struct MemoryPolicyControl: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("Review memory before starting", systemImage: "memorychip")
            Text("Studio will show estimated peak memory for the saved settings and largest complex, then ask whether to proceed. Estimates without a matching measured profile are marked unavailable.")
                .font(.caption).foregroundStyle(.secondary)
            Text("Your choice applies to that run. Existing jobs keep their saved settings.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .accessibilityIdentifier("memory-policy-control")
    }
}
