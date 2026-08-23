import SwiftUI

/// A compact structure tile: predicted structure + run/cycle + iPTM badge.
/// Tapping opens a large inspector. Shared by the Structures grid and Hits.
struct DesignTile: View {
    @EnvironmentObject var thumbnails: ThumbnailStore
    let point: DesignPoint
    var threshold: Double? = nil          // if set, badge turns green when a hit
    var tileHeight: CGFloat = 150
    @State private var showInspector = false

    private var isHit: Bool {
        guard let threshold else { return false }
        return point.iptm >= threshold
    }

    var body: some View {
        VStack(spacing: 0) {
            StructureThumbnail(store: thumbnails, structurePath: point.structurePath)
                .frame(height: tileHeight)
                .background(RoundedRectangle(cornerRadius: 8).fill(.black.opacity(0.04)))
            HStack {
                Text(point.label).font(.caption2).bold().lineLimit(1)
                Spacer()
                VStack(alignment: .trailing, spacing: 1) {
                    Text("iPTM \(point.iptmText)")
                    if let ipsae = point.ipsaeText {
                        Text("ipSAE(min) \(ipsae)").foregroundStyle(.teal)
                    }
                }
                .font(.caption2).monospacedDigit()
                .padding(.horizontal, 5).padding(.vertical, 1)
                .background(Capsule().fill(isHit ? Color.green.opacity(0.22) : Color.secondary.opacity(0.15)))
                .foregroundStyle(isHit ? .green : .secondary)
            }
            .padding(.horizontal, 8).padding(.vertical, 6)
        }
        .background(RoundedRectangle(cornerRadius: 10).fill(.quaternary.opacity(0.4)))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(isHit ? .green.opacity(0.35) : .clear))
        .contentShape(Rectangle())
        .onTapGesture { showInspector = true }
        .sheet(isPresented: $showInspector) {
            StructureInspector(point: point) { showInspector = false }
        }
    }
}

struct StructureInspector: View {
    let point: DesignPoint
    var close: () -> Void
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading) {
                    Text("\(point.stage.label) · \(point.label)").font(.headline)
                    HStack(spacing: 12) {
                        Text("iPTM \(point.iptmText)").foregroundStyle(.green)
                        if let ipsae = point.ipsaeText {
                            Text("ipSAE(min) \(ipsae)").foregroundStyle(.teal)
                        }
                        if point.plddt.isFinite {
                            Text("pLDDT \(point.plddtText)").foregroundStyle(.blue)
                        }
                    }
                    .font(.subheadline)
                }
                Spacer()
                Button("Done", action: close).keyboardShortcut(.defaultAction)
            }
            .padding()
            StructureViewer(structurePath: point.structurePath)
                .frame(minWidth: 620, minHeight: 460)
            Text(point.sequence)
                .font(.system(.caption, design: .monospaced))
                .textSelection(.enabled)
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.quaternary.opacity(0.3))
        }
        .frame(width: 720, height: 660)
    }
}

/// Shared "nothing here yet" placeholder.
struct EmptyHint: View {
    let text: String
    let detail: String
    let systemImage: String
    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: systemImage).font(.system(size: 32)).foregroundStyle(.secondary)
            Text(text).font(.headline)
            Text(detail).font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, minHeight: 160)
        .padding()
    }
}
