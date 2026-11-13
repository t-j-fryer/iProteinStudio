import AppKit
import CryptoKit

/// Pass local coordinates or a hash-bound style script to a selected viewer.
/// Uses native document handoff without a shell, downloads or remote services.
@MainActor
enum ExternalStructureViewer {
    private static let preference = "results.externalViewerApplication"
    static var application: URL? {
        guard let path = UserDefaults.standard.string(forKey: preference) else { return nil }
        let url = URL(fileURLWithPath: path)
        return validApplication(url) ? url : nil
    }

    static func validApplication(_ url: URL) -> Bool {
        url.isFileURL && url.pathExtension.lowercased() == "app"
            && Bundle(url: url)?.bundleIdentifier != nil
            && FileManager.default.fileExists(atPath: url.path)
    }

    static func validStructure(_ url: URL) -> Bool {
        url.isFileURL && ["pdb", "cif", "mmcif"].contains(url.pathExtension.lowercased())
            && (try? url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true
    }

    static func chooseAndOpen(_ structure: URL, recordedChains: [String] = []) {
        let panel = NSOpenPanel()
        panel.title = "Choose ChimeraX or another structure viewer"
        panel.prompt = "Choose viewer"
        panel.allowedContentTypes = [.applicationBundle]
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.directoryURL = FileManager.default.urls(for: .applicationDirectory, in: .localDomainMask).first
        guard panel.runModal() == .OK else { return }
        guard let app = panel.url, validApplication(app) else {
            showError("Choose an installed macOS viewer application.")
            return
        }
        UserDefaults.standard.set(app.path, forKey: preference)
        open(structure, application: app, recordedChains: recordedChains)
    }

    static func isChimeraX(_ app: URL) -> Bool { Bundle(url: app)?.bundleIdentifier == "edu.ucsf.cgl.ChimeraX" }

    static func saveStyle(_ structure: URL, recordedChains: [String] = []) {
        let panel = NSSavePanel(); panel.allowedContentTypes = [.pythonScript]
        panel.nameFieldStringValue = structure.deletingPathExtension().lastPathComponent + "_manuscript_style.py"
        guard panel.runModal() == .OK, let destination = panel.url else { return }
        prepareStyle(structure, recordedChains: recordedChains) { script in
            do { try script.write(to: destination, atomically: true, encoding: .utf8) }
            catch { showError(error.localizedDescription) }
        }
    }

    private static func styleKey(_ structure: URL) -> String {
        "results.chimeraxEmphasizedChains." + SHA256.hash(data: Data(structure.standardizedFileURL.path.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    private static func prepareStyle(_ structure: URL, recordedChains: [String], completion: @escaping (String) -> Void) {
        let selected = UserDefaults.standard.string(forKey: styleKey(structure)) ?? ""
        let chains = selected.isEmpty ? recordedChains.joined(separator: ",") : selected
        Task {
            let result = await Task.detached(priority: .utility) { Result { try ChimeraXPublicationStyle.script(structure: structure, emphasizedChains: chains) } }.value
            switch result {
            case .success(let script): completion(script)
            case .failure(let error): showError(error.localizedDescription)
            }
        }
    }

    static func styleSettings(_ structure: URL) {
        let alert = NSAlert(); alert.messageText = "Manuscript-style chain colours"
        alert.informativeText = "Emphasized protein chain IDs for this structure, comma-separated. They use the paper’s teal cartoons; other protein chains use grey cartoons/surfaces. Leave blank to use explicitly recorded design-chain roles, or otherwise a neutral complex/coloured monomer. Ligand pockets automatically use grey protein and gold ligand surfaces. Use IDs from the exact structure."
        let field = NSTextField(string: UserDefaults.standard.string(forKey: styleKey(structure)) ?? "")
        field.frame = NSRect(x: 0, y: 0, width: 340, height: 26); field.placeholderString = "Emphasized protein chains (optional)"
        alert.accessoryView = field; alert.addButton(withTitle: "Save"); alert.addButton(withTitle: "Cancel")
        if alert.runModal() == .alertFirstButtonReturn { UserDefaults.standard.set(field.stringValue, forKey: styleKey(structure)) }
    }

    static func open(_ structure: URL, application app: URL, manuscriptStyle: Bool = true, recordedChains: [String] = []) {
        guard validApplication(app), validStructure(structure) else {
            showError("The structure file or viewer application is unavailable. Choose an installed viewer and an existing PDB/CIF file.")
            return
        }
        if manuscriptStyle && isChimeraX(app) {
            prepareStyle(structure, recordedChains: recordedChains) { script in
                do {
                    let directory = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first!.appendingPathComponent("iProteinStudio/ChimeraX")
                    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                    let path = directory.appendingPathComponent(UUID().uuidString + ".py")
                    try script.write(to: path, atomically: true, encoding: .utf8)
                    handoff(path, app: app)
                } catch { showError(error.localizedDescription) }
            }
        } else { handoff(structure, app: app) }
    }

    private static func handoff(_ file: URL, app: URL) {
        NSWorkspace.shared.open([file], withApplicationAt: app, configuration: NSWorkspace.OpenConfiguration()) { _, error in
            if let error { Task { @MainActor in showError(error.localizedDescription) } }
        }
    }

    private static func showError(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "Could not open external viewer"
        alert.informativeText = message
        alert.runModal()
    }
}
