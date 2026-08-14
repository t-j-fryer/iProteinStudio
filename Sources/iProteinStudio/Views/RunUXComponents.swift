import SwiftUI
import AppKit

enum SetupExperience: String, CaseIterable, Identifiable {
    case quick = "Quick setup"
    case advanced = "Advanced"
    var id: String { rawValue }
}

struct SetupExperiencePicker: View {
    @Binding var selection: SetupExperience

    var body: some View {
        HStack(spacing: 12) {
            Picker("Setup detail", selection: $selection) {
                ForEach(SetupExperience.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .frame(width: 260)
            .accessibilityIdentifier("setup-experience-picker")
            Text(selection == .quick
                 ? "Recommended settings stay selected; only decisions needed to start are shown."
                 : "Inspect model, alignment, sampling, and throughput controls.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color.accentColor.opacity(0.07)))
    }
}

/// Leads with what failed and what the user can do. Technical output remains
/// available, but it no longer competes with the recovery action.
struct ActionableErrorCard: View {
    let title: String
    let message: String
    var retryTitle: String = "Retry"
    var retry: (() -> Void)?
    var output: URL?
    var log: [String] = []
    @State private var showDetails = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: "exclamationmark.triangle.fill")
                .font(.headline).foregroundStyle(.orange)
            Text(message).font(.callout).textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
            HStack {
                if let retry {
                    Button(retryTitle, action: retry)
                        .buttonStyle(.borderedProminent)
                }
                if let output {
                    Button { NSWorkspace.shared.activateFileViewerSelecting([output]) } label: {
                        Label("Reveal output", systemImage: "folder")
                    }
                }
                if !log.isEmpty {
                    Button(showDetails ? "Hide technical log" : "Show technical log") {
                        withAnimation { showDetails.toggle() }
                    }
                }
            }
            if showDetails, !log.isEmpty {
                ScrollView {
                    Text(log.suffix(120).joined(separator: "\n"))
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                }
                .frame(maxHeight: 180)
                .background(RoundedRectangle(cornerRadius: 8).fill(.background))
            }
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: 12).fill(Color.orange.opacity(0.09)))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.orange.opacity(0.25)))
        .accessibilityElement(children: .contain)
        .accessibilityLabel("\(title). \(message)")
    }
}

struct TechnicalLogDisclosure: View {
    let lines: [String]
    @State private var expanded = false

    var body: some View {
        DisclosureGroup("Technical log", isExpanded: $expanded) {
            ScrollView {
                Text(lines.suffix(200).joined(separator: "\n"))
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.secondary).textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(8)
            }
            .frame(maxHeight: 220)
            .background(RoundedRectangle(cornerRadius: 8).fill(.background))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(.quaternary))
        }
        .font(.callout)
    }
}
