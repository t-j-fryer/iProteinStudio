import SwiftUI

/// Static, cached structure image for grid tiles. Shows a placeholder until the
/// thumbnail has been rendered offscreen, then refreshes.
struct StructureThumbnail: View {
    @ObservedObject var store: ThumbnailStore
    let structurePath: String

    var body: some View {
        // Depend on `version` so the view refreshes when the thumbnail lands.
        let _ = store.version
        ZStack {
            if let img = store.image(for: structurePath) {
                Image(nsImage: img)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: .fit)
            } else {
                VStack(spacing: 6) {
                    ProgressView().controlSize(.small)
                    Image(systemName: "atom").foregroundStyle(.tertiary)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
