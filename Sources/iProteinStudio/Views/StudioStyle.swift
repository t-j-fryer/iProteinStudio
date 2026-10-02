import SwiftUI
import AppKit

/// Shared native surfaces. Scientific status colours retain their own semantics.
/// Adaptive colours keep the mineral palette legible in both system appearances.
enum StudioPalette {
    private static func adaptive(_ name: String, light: UInt32, dark: UInt32) -> Color {
        Color(nsColor: NSColor(name: NSColor.Name(name)) { appearance in
            let value = appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua ? dark : light
            return NSColor(srgbRed: CGFloat((value >> 16) & 255) / 255,
                           green: CGFloat((value >> 8) & 255) / 255,
                           blue: CGFloat(value & 255) / 255, alpha: 1)
        })
    }
    static let canvas = adaptive("StudioPaper", light: 0xF7F5F0, dark: 0x202722)
    static let panel = adaptive("StudioChalk", light: 0xFDFBF7, dark: 0x2B332D)
    static let sidebar = adaptive("StudioSage", light: 0xECEEE4, dark: 0x252D27)
    static let ink = adaptive("StudioInk", light: 0x243C30, dark: 0xEEEFE6)
    static let secondary = adaptive("StudioSecondary", light: 0x62695F, dark: 0xBCC6B8)
    static let accent = adaptive("StudioMoss", light: 0x3C5846, dark: 0xB6C9A6)
    static let clay = adaptive("StudioClay", light: 0x9C573B, dark: 0xDBA589)
    static let line = adaptive("StudioLine", light: 0xD8D9CE, dark: 0x505E51)
}

struct StudioAppearance: ViewModifier {
    @AppStorage("studio.appearance") private var appearance = "system"
    func body(content: Content) -> some View {
        content
            .tint(StudioPalette.accent)
            .accentColor(StudioPalette.accent)
            .background(StudioPalette.canvas)
            .groupBoxStyle(StudioGroupBoxStyle())
            .preferredColorScheme(appearance == "dark" ? .dark : appearance == "light" ? .light : nil)
    }
}

struct StudioSurface: ViewModifier {
    @Environment(\.colorSchemeContrast) private var contrast
    func body(content: Content) -> some View {
        content
            .background(StudioPalette.panel, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12)
                .stroke(contrast == .increased ? StudioPalette.ink : StudioPalette.line,
                        lineWidth: contrast == .increased ? 1.5 : 0.75))
    }
}

struct StudioGroupBoxStyle: GroupBoxStyle {
    func makeBody(configuration: Configuration) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            configuration.label.font(.headline)
            configuration.content
        }
        .padding(18).frame(maxWidth: .infinity, alignment: .leading)
        .modifier(StudioSurface())
    }
}

/// Images are cached once, decorative, and never used instead of control labels.
struct StudioArtwork: View {
    let name: String
    var template = false
    private static var images: [String: NSImage] = [:]
    private var image: NSImage? {
        if let cached = Self.images[name] { return cached }
        guard let url = AppPaths.brandArtwork(name), let image = NSImage(contentsOf: url) else { return nil }
        Self.images[name] = image
        return image
    }
    var body: some View {
        if let image {
            Image(nsImage: image)
                .renderingMode(template ? .template : .original)
                .resizable().aspectRatio(contentMode: .fit)
                .accessibilityHidden(true)
        }
    }
}

extension WorkspaceMode {
    var artwork: String {
        switch self {
        case .iterative: return "hunter-trajectories"
        case .nise: return "nise"
        case .rfdiffusion: return "backbone"
        case .predict: return "predict-object"
        }
    }
    var introduction: String {
        switch self {
        case .iterative: return "Explore protein binders through iterative design and independent checks."
        case .nise: return "Explore sequences around a small molecule through selection and expansion."
        case .rfdiffusion: return "Generate a backbone, explore a nearby shape, or scaffold a motif."
        case .predict: return "Predict the structure of sequences you already have."
        }
    }
}

struct StudioWorkflowHeader: View {
    let mode: WorkspaceMode
    let subtitle: String
    var body: some View {
        HStack(alignment: .center, spacing: 16) {
            StudioWorkflowArtwork(mode: mode)
                .frame(width: 68, height: 68)
                .clipShape(RoundedRectangle(cornerRadius: 14))
            VStack(alignment: .leading, spacing: 5) {
                Text(mode.label).font(.largeTitle.weight(.semibold))
                Text(subtitle).foregroundStyle(StudioPalette.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 6)
    }
}

struct StudioAppearanceSettings: View {
    @AppStorage("studio.appearance") private var appearance = "system"
    var body: some View {
        Form {
            Section("Appearance") {
                Picker("Appearance", selection: $appearance) {
                    Text("Follow System").tag("system")
                    Text("Light").tag("light")
                    Text("Dark").tag("dark")
                }
                .pickerStyle(.segmented)
                Text("Chalk, moss, and clay. The same workspace, adapted to your preferred appearance.")
                    .font(.callout).foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .frame(width: 620, height: 300)
    }
}

/// Preserve the website sculptures' original materials and colours in both appearances.
struct StudioWorkflowArtwork: View {
    let mode: WorkspaceMode
    var body: some View {
        StudioArtwork(name: mode.artwork)
    }
}
