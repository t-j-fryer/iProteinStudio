import Foundation
import Combine

/// Root application state: the project list, selection, and persistence.
@MainActor
final class AppState: ObservableObject {
    @Published var projects: [Project] = []
    @Published var selectedProjectID: Project.ID?
    @Published var scaffolds: [Scaffold] = []

    let installer = PipelineInstaller()
    let run = RunController()
    let rfd3 = RFD3Controller()
    let metrics = MetricsWatcher()
    let thumbnails = ThumbnailStore()
    let smilesThumbnails = SmilesThumbnailStore()
    let predictions = PredictionStore()

    private struct Persisted: Codable { var projects: [Project] }

    init() {
        load()
        // Refresh vendored scripts on every launch so app updates ship pipeline
        // fixes without requiring a full reinstall. Only touches pipeline/
        // (scripts + examples); never the installed venvs or cloned tools.
        if AppPaths.bundledPipeline != nil {
            try? AppPaths.stagePipelineAssets()
        }
        scaffolds = ScaffoldCatalog.load()
        if selectedProjectID == nil { selectedProjectID = projects.first?.id }
        // Ask the pipeline which backends are actually present, so the design
        // form can refuse to offer a predictor that would fail at run time.
        installer.detectComponents()
    }

    var selectedProject: Project? {
        get { projects.first { $0.id == selectedProjectID } }
        set {
            guard let nv = newValue, let idx = projects.firstIndex(where: { $0.id == nv.id }) else { return }
            projects[idx] = nv
            save()
        }
    }

    func addProject(name: String) {
        var p = Project(name: name.isEmpty ? "Untitled Design" : name)
        // Seed with the recommended default scaffold if available.
        if let s = scaffolds.first(where: { $0.id == p.request.scaffoldID }) ?? scaffolds.first {
            p.request.scaffoldID = s.id
            p.request.scaffoldSequence = s.sequence
        }
        projects.append(p)
        selectedProjectID = p.id
        save()
    }

    func renameProject(_ project: Project, to newName: String) {
        let trimmed = newName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, let idx = projects.firstIndex(where: { $0.id == project.id }) else { return }
        projects[idx].name = trimmed
        save()
    }

    func deleteProject(_ project: Project) {
        projects.removeAll { $0.id == project.id }
        if selectedProjectID == project.id { selectedProjectID = projects.first?.id }
        // Remove on-disk outputs.
        try? AppPaths.fm.removeItem(at: AppPaths.projectDir(project))
        save()
    }

    func updateSelected(_ mutate: (inout Project) -> Void) {
        guard let id = selectedProjectID, let idx = projects.firstIndex(where: { $0.id == id }) else { return }
        mutate(&projects[idx])
        save()
    }

    /// Ensure the catalog is loaded once the pipeline is staged (post-install).
    func reloadScaffoldsIfNeeded() {
        if scaffolds.isEmpty { scaffolds = ScaffoldCatalog.load() }
    }

    // MARK: Persistence

    func save() {
        let data = try? JSONEncoder().encode(Persisted(projects: projects))
        try? data?.write(to: AppPaths.configFile)
    }

    private func load() {
        guard let data = try? Data(contentsOf: AppPaths.configFile),
              let p = try? JSONDecoder().decode(Persisted.self, from: data) else { return }
        projects = p.projects
    }
}
