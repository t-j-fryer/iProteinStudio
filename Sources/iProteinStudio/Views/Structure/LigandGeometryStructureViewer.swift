import SwiftUI

/// Display the recorded classifier samples over the exact tested holo pose.
struct LigandGeometryStructureViewer: View {
    let structureURL: URL
    @State private var showGeometry = false
    @StateObject private var preview = LigandGeometryPreview()
    private var result: [String: Any]? { LigandGeometryResult.read(structureURL) ?? (preview.structurePath == structureURL.path ? preview.result : nil) }
    var body: some View {
        VStack(spacing: 4) {
            if let result, let payload = LigandGeometryResult.spatialPayload(structureURL, result: result) {
                HStack {
                    Toggle("Show linker-exit cone", isOn: $showGeometry).toggleStyle(.switch)
                    if let exit = result["linker_exit"] as? [String: Any], let label = exit["label"] as? String { Text("Exit: " + label).font(.caption) }
                }.padding(.horizontal, 8)
                if showGeometry { LigandSpatialViewer(payload: payload) }
                else { StructureViewer(structurePath: structureURL.path) }
            } else {
                if LigandGeometryPreview.hasRecordedGeometry(structureURL) {
                    HStack {
                        Button("Inspect recorded linker-exit cone") { preview.load(structureURL); showGeometry = true }.disabled(preview.busy)
                        if preview.busy { ProgressView().controlSize(.small) }
                    }
                    if let error = preview.error { Text(error).font(.caption).foregroundStyle(.orange) }
                }
                StructureViewer(structurePath: structureURL.path)
            }
        }.id(structureURL.path)
    }
}
