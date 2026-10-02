import SwiftUI

struct StudioSectionTab: View {
    let title: String
    let artwork: String
    let selected: Bool
    let action: () -> Void
    @State private var hovering = false
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                StudioArtwork(name: artwork).frame(width: 34, height: 34)
                Text(title).font(.headline)
            }
            .foregroundStyle(selected ? StudioPalette.ink : StudioPalette.secondary)
            .padding(.horizontal, 14).padding(.vertical, 6)
            .background(selected || hovering ? StudioPalette.sidebar : .clear,
                        in: RoundedRectangle(cornerRadius: 9))
            .overlay(RoundedRectangle(cornerRadius: 9)
                .stroke(selected ? StudioPalette.accent : .clear, lineWidth: contrast == .increased ? 2 : 1))
            .contentShape(RoundedRectangle(cornerRadius: 9))
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
        .accessibilityLabel(title)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier("section-\(title.lowercased())")
        .help(title == "Design" ? "Choose a design method" : "Predict structures from existing sequences")
    }
}

struct DesignMethodChooser: View {
    let previousMode: WorkspaceMode
    let onSelect: (WorkspaceMode) -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack(spacing: 16) {
                    StudioArtwork(name: "design-object")
                        .frame(width: 68, height: 68)
                    VStack(alignment: .leading, spacing: 5) {
                        Text("Design").font(.largeTitle.weight(.semibold))
                        Text("Choose how to explore your next candidate.")
                            .foregroundStyle(StudioPalette.secondary)
                    }
                }
                ForEach(WorkspaceMode.designMethods) { method in
                    Button { onSelect(method) } label: {
                        HStack(spacing: 18) {
                            StudioWorkflowArtwork(mode: method).frame(width: 76, height: 76)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    Text(method.label).font(.title3.weight(.semibold))
                                    if method == previousMode {
                                        Text("Last opened").font(.caption).foregroundStyle(.secondary)
                                    }
                                }
                                Text(description(method)).font(.callout)
                                    .foregroundStyle(StudioPalette.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            Spacer(minLength: 0)
                            Image(systemName: "chevron.right").foregroundStyle(StudioPalette.accent)
                        }
                        .padding(18).frame(maxWidth: .infinity, alignment: .leading)
                        .modifier(StudioSurface())
                        .contentShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Open \(method.label)")
                    .accessibilityHint(description(method))
                    .accessibilityIdentifier("design-method-\(method.rawValue)")
                }
                Text("Choosing a method opens its inputs and saved work. It does not start a run.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            .padding(28).frame(maxWidth: 880, alignment: .leading).frame(maxWidth: .infinity)
        }
        .background(StudioPalette.canvas)
        .accessibilityIdentifier("design-method-chooser")
    }

    private func description(_ method: WorkspaceMode) -> String {
        switch method {
        case .iterative:
            return "Start from multiple candidates and refine each trajectory independently through design and checking."
        case .nise:
            return "Explore small-molecule binding pockets through sequence selection and expansion."
        case .rfdiffusion:
            return "Generate backbones, explore nearby structures, or scaffold a functional motif."
        case .predict:
            return method.introduction
        }
    }
}
