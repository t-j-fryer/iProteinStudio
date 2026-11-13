import SwiftUI

struct ExternalStructureViewerButton: View {
    let structureURL: URL
    var recordedChains: [String] = []
    var body: some View {
        Menu {
            if let app = ExternalStructureViewer.application {
                Button("Open in \(app.deletingPathExtension().lastPathComponent)" + (ExternalStructureViewer.isChimeraX(app) ? " · manuscript style" : "")) {
                    ExternalStructureViewer.open(structureURL, application: app, recordedChains: recordedChains)
                }
                if ExternalStructureViewer.isChimeraX(app) {
                    Button("Open coordinates without styling") { ExternalStructureViewer.open(structureURL, application: app, manuscriptStyle: false) }
                }
            }
            Button("Save manuscript-style ChimeraX script…") { ExternalStructureViewer.saveStyle(structureURL, recordedChains: recordedChains) }
            Button("Manuscript style settings…") { ExternalStructureViewer.styleSettings(structureURL) }
            Button("Choose ChimeraX or another viewer…") { ExternalStructureViewer.chooseAndOpen(structureURL, recordedChains: recordedChains) }
        } label: {
            Label("External viewer", systemImage: "arrow.up.forward.app")
        }.menuStyle(.borderlessButton).fixedSize()
            .help("Open this local PDB/CIF in an installed viewer; the app is remembered for future designs")
    }
}
