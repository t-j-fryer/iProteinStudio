import SwiftUI

/// Form labels remain visible when a value replaces the text-field placeholder.
struct StudioFormField<Content: View>: View {
    let title: String
    let explanation: String
    let content: Content
    init(_ title: String, explanation: String = "", @ViewBuilder content: () -> Content) {
        self.title = title; self.explanation = explanation; self.content = content()
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.callout)
            content
            if !explanation.isEmpty { Text(explanation).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true) }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}
