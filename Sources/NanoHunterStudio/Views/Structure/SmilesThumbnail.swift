import SwiftUI

/// Static cached 2D depiction of a SMILES (for project rows / dashboard).
struct SmilesThumbnail: View {
    @ObservedObject var store: SmilesThumbnailStore
    let smiles: String
    var cornerRadius: CGFloat = 6

    var body: some View {
        let _ = store.version   // refresh when a thumbnail lands
        ZStack {
            RoundedRectangle(cornerRadius: cornerRadius).fill(.white)
            if let img = store.image(for: smiles) {
                Image(nsImage: img)
                    .resizable().interpolation(.high).aspectRatio(contentMode: .fit)
                    .padding(2)
            } else {
                Image(systemName: "atom").foregroundStyle(.tertiary).font(.caption)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
    }
}
