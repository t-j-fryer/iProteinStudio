import SwiftUI

/// Friendly first-run wizard. Hides all the venv/clone/download complexity
/// behind a single button with live progress, while still letting the user opt
/// into the heavier predictors and reuse an installation they already have.
struct SetupView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        InnerSetup(installer: app.installer)
    }
}

private struct InnerSetup: View {
    @ObservedObject var installer: PipelineInstaller
    @State private var showOptions = false

    var body: some View {
        ScrollView {
            VStack(spacing: 18) {
                Image(systemName: "atom")
                    .font(.system(size: 56))
                    .foregroundStyle(.tint)
                Text("Welcome to NanoHunter Studio")
                    .font(.largeTitle.bold())
                Text("Design binders against your target — no terminal required.")
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
            .frame(maxWidth: 620)
            .padding(40)
            .frame(maxWidth: .infinity)
        }
        .safeAreaInset(edge: .bottom) { footnote }
        .background(.background)
    }

    // MARK: Idle

    private var idleView: some View {
        VStack(spacing: 16) {
            if let existing = installer.detectedNanoHunter {
                reuseCard(existing)
            }

            Text("Setup installs the core design engines — Boltz-2, IntelliFold, AntiFold and the MPNN sequence designers — and downloads their model weights. One time, and it needs an internet connection.")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            DisclosureGroup(isExpanded: $showOptions) {
                optionalComponents
            } label: {
                Text("Optional extras").font(.callout.weight(.medium))
            }
            .frame(maxWidth: 480)

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

    /// A machine that already has NanoHunter installed should not download it
    /// twice — the environments and weights run to tens of gigabytes.
    private func reuseCard(_ existing: URL) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("You already have NanoHunter installed", systemImage: "checkmark.seal.fill")
                .font(.headline)
                .foregroundStyle(.green)
            Text("Found at \(existing.path). Studio can use those engines directly instead of downloading its own copy — this takes seconds instead of an hour, and saves tens of gigabytes.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if let rfd3 = installer.detectedRFD3 {
                Text("RFdiffusion3 found at \(rfd3.path) — it will be linked too.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Button {
                installer.linkExisting(nanoHunter: existing, rfd3: installer.detectedRFD3)
            } label: {
                Label("Use my existing installation", systemImage: "link")
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 12).fill(.green.opacity(0.10)))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(.green.opacity(0.35)))
    }

    private var optionalComponents: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("These add extra structure predictors you can use to double-check designs with an independent model. You can add them later.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            ForEach(InstallComponent.allCases.filter { !$0.isCore }) { component in
                Toggle(isOn: Binding(
                    get: { installer.optionalSelection.contains(component) },
                    set: { on in
                        if on { installer.optionalSelection.insert(component) }
                        else { installer.optionalSelection.remove(component) }
                    }
                )) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(component.label)
                        if let note = component.downloadNote {
                            Text(note).font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
                .toggleStyle(.checkbox)
            }
        }
        .padding(.top, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Running / failed

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
            .frame(maxWidth: .infinity)
            .background(.background)
    }
}
