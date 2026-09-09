import SwiftUI
import UniformTypeIdentifiers
import StudioCore

private struct SupportDocument: FileDocument {
    static var readableContentTypes: [UTType] { [.plainText] }
    var text: String
    init(text: String) { self.text = text }
    init(configuration: ReadConfiguration) throws {
        text = String(decoding: configuration.file.regularFileContents ?? Data(), as: UTF8.self)
    }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        FileWrapper(regularFileWithContents: Data(text.utf8))
    }
}

struct SupportReportView: View {
    let message: String
    let log: [String]
    @Environment(\.dismiss) private var dismiss
    @State private var export = false
    @State private var error: String?
    private var document: SupportDocument {
        let bundle = Bundle.main
        let version = "\(bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "development") (\(bundle.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "local"))"
        return SupportDocument(text: SupportReport.make(version: version,
            system: ProcessInfo.processInfo.operatingSystemVersionString,
            memoryBytes: ProcessInfo.processInfo.physicalMemory, message: message, log: log))
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Review support report").font(.title2.bold())
            ScrollView { Text(document.text).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
            if let error { Text(error).foregroundStyle(.red) }
            HStack {
                Button("Close") { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Save Report…") { export = true }.keyboardShortcut(.defaultAction)
            }
        }
        .padding(24).frame(minWidth: 480, idealWidth: 560, minHeight: 360)
        .fileExporter(isPresented: $export, document: document, contentType: .plainText,
                      defaultFilename: "iProteinStudio-support") { result in
            if case .failure(let failure) = result { error = failure.localizedDescription }
        }
    }
}
