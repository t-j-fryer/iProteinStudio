import SwiftUI

struct EngineRequirementWarning: View {
    let issues: [EngineRequirementIssue]
    var body: some View {
        if !issues.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Label(EngineRequirementIssue.message(issues), systemImage: "shippingbox")
                ForEach(issues.filter { !$0.dependencies.isEmpty }) { issue in
                    Text("\(issue.component.label) needs: \(issue.dependencies.map(\.label).joined(separator: ", ")).")
                        .font(.caption)
                }
            }
            .foregroundStyle(.orange)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("missing-engine-requirements")
        }
    }
}
