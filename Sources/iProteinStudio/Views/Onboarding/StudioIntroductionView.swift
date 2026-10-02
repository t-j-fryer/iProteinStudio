import SwiftUI

/// Orientation only: no engine installation, project mutation, or job submission.
/// Both first launch and Help reuse this view; completing it never marks setup done.
struct StudioIntroductionView: View {
    var completionTitle = "Open Studio"
    let onFinish: () -> Void
    @State private var page = 0

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    HStack(spacing: 12) {
                        StudioArtwork(name: "terra-loop").frame(width: 58, height: 58)
                        VStack(alignment: .leading, spacing: 3) {
                            Text("iProteinStudio").font(.title3.weight(.semibold))
                            Text("Protein science. At home on your Mac.")
                                .font(.callout).foregroundStyle(StudioPalette.secondary)
                        }
                        Spacer()
                        Text("\(page + 1) of 3").font(.caption.monospacedDigit()).foregroundStyle(StudioPalette.secondary)
                    }
                    Group {
                        switch page {
                        case 0: welcome
                        case 1: workflows
                        default: evidence
                        }
                    }
                }
                .padding(32)
                .frame(maxWidth: 850, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
            Divider()
            HStack {
                Button("Skip introduction", action: onFinish).keyboardShortcut(.cancelAction)
                Spacer()
                if page > 0 { Button("Back") { page -= 1 } }
                Button(page == 2 ? completionTitle : "Continue") {
                    if page == 2 { onFinish() } else { page += 1 }
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
            }
            .padding(20)
        }
        .modifier(StudioAppearance())
        .accessibilityIdentifier("studio-introduction")
    }

    private var welcome: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("From a question to a possibility.")
                .font(.system(size: 29, weight: .semibold))
            Text("A native workspace for protein design and structure prediction. Prepare your inputs, choose a method, and keep each result connected to the work that produced it.")
                .font(.body).foregroundStyle(StudioPalette.secondary).fixedSize(horizontal: false, vertical: true)
            StudioArtwork(name: "branching-possibilities")
                .frame(maxHeight: 235).clipShape(RoundedRectangle(cornerRadius: 12))
            HStack(spacing: 24) {
                Label("Work locally", systemImage: "desktopcomputer")
                Label("Follow the process", systemImage: "point.3.connected.trianglepath.dotted")
                Label("Inspect the evidence", systemImage: "cube.transparent")
            }
            .font(.callout).foregroundStyle(StudioPalette.accent)
            Text("Start with this short introduction, or go straight to Studio. You can find it again in Help.")
                .font(.callout).foregroundStyle(StudioPalette.secondary)
        }
    }

    private var workflows: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Start with your scientific question.").font(.title.weight(.semibold))
            Text("Use Predict for sequences you have. Open Design to choose Protein Hunter, NISE, or RFdiffusion3. A workspace keeps their related runs together.")
                .foregroundStyle(StudioPalette.secondary)
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 14) {
                ForEach(WorkspaceMode.allCases) { mode in
                    HStack(alignment: .top, spacing: 12) {
                        StudioWorkflowArtwork(mode: mode).frame(width: 52, height: 52)
                            .clipShape(RoundedRectangle(cornerRadius: 11))
                        VStack(alignment: .leading, spacing: 6) {
                            Text(mode.label).font(.headline)
                            Text(mode.introduction).font(.callout).foregroundStyle(StudioPalette.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(16).frame(maxWidth: .infinity, minHeight: 116, alignment: .topLeading)
                    .modifier(StudioSurface())
                }
            }
            Text("Engines have their own macOS, memory, and download requirements. Studio checks availability before you run anything.")
                .font(.callout).foregroundStyle(StudioPalette.secondary)
        }
    }

    private var evidence: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Keep the thread, from input to result.").font(.title.weight(.semibold))
            StudioArtwork(name: "workflow-stages").frame(maxHeight: 210)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            VStack(alignment: .leading, spacing: 12) {
                guidance("Prepare with intention", "Start with a target, sequence, or example. Review inputs and engine requirements before submitting a run.", symbol: "slider.horizontal.3")
                guidance("Return to your work", "The queue tracks submitted jobs. Supported campaigns keep checkpoints so interrupted work can resume.", symbol: "clock.arrow.circlepath")
                guidance("Look beyond a score", "Inspect structures and independent checks. A predicted candidate is a hypothesis to test experimentally.", symbol: "magnifyingglass")
            }
            Text("The science comes from the upstream research community. Studio brings those methods into one workspace. Engine downloads and any enabled external alignment service require a network connection; review their details during setup.")
                .font(.caption).foregroundStyle(StudioPalette.secondary).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func guidance(_ title: String, _ detail: String, symbol: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: symbol).font(.title3).foregroundStyle(StudioPalette.clay).frame(width: 26)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.headline)
                Text(detail).font(.callout).foregroundStyle(StudioPalette.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

struct StudioIntroductionWindow: View {
    @Environment(\.dismissWindow) private var dismissWindow
    var body: some View {
        StudioIntroductionView { dismissWindow(id: "studio-introduction") }
            .frame(minWidth: 720, minHeight: 580)
    }
}
