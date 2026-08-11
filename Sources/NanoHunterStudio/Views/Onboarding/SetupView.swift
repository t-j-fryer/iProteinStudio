import SwiftUI

/// Friendly first-run wizard. Hides all the venv/clone/download complexity
/// behind a single "Set up" button with live progress.
struct SetupView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        InnerSetup(installer: app.installer)
    }
}

private struct InnerSetup: View {
    @ObservedObject var installer: PipelineInstaller

    var body: some View {
        VStack(spacing: 0) {
            Spacer()
            VStack(spacing: 18) {
                Image(systemName: "atom")
                    .font(.system(size: 64))
                    .foregroundStyle(.tint)
                Text("Welcome to NanoHunter Studio")
                    .font(.largeTitle.bold())
                Text("Design nanobodies against your target — no terminal required.")
                    .font(.title3)
                    .foregroundStyle(.secondary)

                if installer.isInstalling {
                    installingView
                } else if let failure = installer.failure {
                    failureView(failure)
                } else {
                    idleView
                }
            }
            .frame(maxWidth: 560)
            .padding(40)
            Spacer()
            footnote
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.background)
    }

    private var idleView: some View {
        VStack(spacing: 14) {
            Text("First-time setup installs the design engines (Boltz, IntelliFold, AntiFold and the MPNN designers) and downloads their model weights. This is a one-time step and needs an internet connection.")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Button {
                installer.install()
            } label: {
                Label("Set Up NanoHunter", systemImage: "arrow.down.circle.fill")
                    .frame(maxWidth: 260)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            Text("Downloads are several GB and can take a while on first run.")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
    }

    private var installingView: some View {
        VStack(spacing: 14) {
            ProgressView(value: installer.progress)
                .progressViewStyle(.linear)
                .frame(maxWidth: 420)
            Text(installer.currentMessage)
                .font(.headline)
            Text("\(Int(installer.progress * 100))%")
                .font(.caption).foregroundStyle(.secondary)
            recentSteps
            Button("Cancel", role: .cancel) { installer.cancel() }
                .controlSize(.small)
        }
    }

    private func failureView(_ failure: String) -> some View {
        VStack(spacing: 14) {
            Label("Setup didn't finish", systemImage: "exclamationmark.triangle.fill")
                .font(.headline)
                .foregroundStyle(.orange)
            Text(failure)
                .font(.callout)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
            Button {
                installer.install()
            } label: {
                Label("Try Again", systemImage: "arrow.clockwise")
            }
            .buttonStyle(.borderedProminent)
        }
    }

    private var recentSteps: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(installer.steps.suffix(4)) { step in
                HStack(spacing: 6) {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(.green).font(.caption)
                    Text(step.message).font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .frame(maxWidth: 420, alignment: .leading)
    }

    private var footnote: some View {
        Text("Runs entirely on your Mac. Your sequences never leave your machine except to fetch public MSAs.")
            .font(.caption2)
            .foregroundStyle(.tertiary)
            .padding(.bottom, 16)
    }
}
