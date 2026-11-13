import SwiftUI

struct ResultPageControls: View {
    let count: Int
    @Binding var page: Int
    var body: some View {
        let current = ResultPage(count: count, requested: page)
        if current.pageCount > 1 {
            HStack {
                Button("Previous") { page = current.number - 1 }.disabled(current.number == 0)
                Text("\(current.range.lowerBound + 1)–\(current.range.upperBound) of \(count)")
                    .font(.caption).monospacedDigit()
                Button("Next") { page = current.number + 1 }.disabled(current.number + 1 >= current.pageCount)
                Spacer()
            }.padding(8)
        }
    }
}
