import Foundation
import Combine
import StudioCore

/// Root application state: the project list, selection, and persistence.
@MainActor
final class AppState: ObservableObject {
    @Published var projects: [Project] = []
    @Published var selectedProjectID: Project.ID?
    @Published private(set) var archivedProjects: [Project] = []
    @Published private(set) var runtimeNotice: String?
    private var observers = Set<AnyCancellable>()
    @Published var storageMessage: String?
    @Published private(set) var storageAvailable = true
    @Published var scaffolds: [Scaffold] = []

    let installer = PipelineInstaller()
    let run = RunController()
    let rfd3 = RFD3Controller()
    let prediction = PredictionController()
    let nise = NISEController()
    let metrics = MetricsWatcher()
    let thumbnails = ThumbnailStore()
    let smilesThumbnails = SmilesThumbnailStore()
    let predictions = PredictionStore()
    let history = RunHistoryStore()

    private struct Persisted: Codable {
        var projects: [Project]
        var archivedProjects: [Project] = []
        enum CodingKeys: String, CodingKey { case projects, archivedProjects }
        init(projects: [Project], archivedProjects: [Project] = []) {
            self.projects = projects; self.archivedProjects = archivedProjects
        }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            projects = try c.decode([Project].self, forKey: .projects)
            archivedProjects = try c.decodeIfPresent([Project].self, forKey: .archivedProjects) ?? []
        }
    }
    private var lastSaved = Persisted(projects: [])
    private var store: RecoverableJSONStore<Persisted> { RecoverableJSONStore(url: AppPaths.configFile) }

    init() {
        load()
        // Refresh vendored scripts on every launch so app updates ship pipeline
        // fixes without requiring a full reinstall. Only touches pipeline/
        // (scripts + examples); never the installed venvs or cloned tools.
        if AppPaths.bundledPipeline != nil {
            do { try AppPaths.stagePipelineAssets() }
            catch ExecutionLease.LeaseError.busy { runtimeNotice = "Workflow updates will be applied after active jobs finish." }
            catch { storageMessage = "Studio could not refresh its bundled workflow files: \(error.localizedDescription)" }
        }
        scaffolds = ScaffoldCatalog.load()
        if selectedProjectID == nil { selectedProjectID = projects.first?.id }
        history.refresh(projects: projects)
        // Ask the pipeline which backends are actually present, so the design
        // form can refuse to offer a predictor that would fail at run time.
        installer.detectComponents()
        JobCenter.shared.start()
        JobCenter.shared.$jobs.sink { [weak self] jobs in
            guard let self, self.runtimeNotice != nil, !jobs.contains(where: \.isActive) else { return }
            do {
                try AppPaths.stagePipelineAssets()
                self.scaffolds = ScaffoldCatalog.load()
                self.runtimeNotice = nil
            }
            catch { /* The execution lease remains authoritative between polls. */ }
        }.store(in: &observers)
        nise.objectWillChange.sink { [weak self] _ in self?.objectWillChange.send() }.store(in: &observers)
        run.$campaignRoot.removeDuplicates().sink { [weak self] root in
            if let root { self?.metrics.start(root: root) }
            else { self?.metrics.stop() }
        }.store(in: &observers)
        reattachManagedRuns()
    }

    var selectedProject: Project? {
        get { projects.first { $0.id == selectedProjectID } }
        set {
            guard let nv = newValue, let idx = projects.firstIndex(where: { $0.id == nv.id }) else { return }
            projects[idx] = nv
            save()
        }
    }

    func addProject(name: String, preferredMode: WorkspaceMode = .iterative) {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let displayName = trimmed.isEmpty
            ? WorkspaceNaming.uniqueName(base: preferredMode.defaultWorkspaceName,
                                         existing: projects.map(\.name))
            : trimmed
        var p = Project(name: displayName, preferredMode: preferredMode)
        let diskSlugs = (try? AppPaths.fm.contentsOfDirectory(atPath: AppPaths.projects.path)) ?? []
        p.slug = WorkspaceNaming.uniqueSlug(for: displayName,
                                            existing: projects.map(\.slug) + diskSlugs)
        // Seed with the recommended default scaffold if available.
        if let s = scaffolds.first(where: { $0.id == p.request.scaffoldID }) ?? scaffolds.first {
            p.request.scaffoldID = s.id
            p.request.scaffoldSequence = s.sequence
        }
        projects.append(p)
        selectedProjectID = p.id
        save()
        history.refresh(projects: projects)
    }

    func renameProject(_ project: Project, to newName: String) {
        let trimmed = newName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, let idx = projects.firstIndex(where: { $0.id == project.id }) else { return }
        projects[idx].name = trimmed
        save()
    }

    /// Archive is reversible and keeps original launch paths recoverable on
    /// Restore. Registry and execution leases exclude both GUI and MCP work.
    func deleteProject(_ project: Project) {
        transferProject(project, archiving: true)
    }

    func restoreProject(_ project: Project) { transferProject(project, archiving: false) }

    private func transferProject(_ project: Project, archiving: Bool) {
        guard storageAvailable else { return }
        guard !run.isRunning, !rfd3.isRunning, !rfd3.isPreparing, !prediction.isRunning, !nise.isRunning else {
            storageMessage = "Wait for active work to finish before archiving or restoring a workspace."
            return
        }
        do {
            let agent = AppPaths.support.appendingPathComponent("agent")
            let registry = try ExecutionLease(directory: agent, name: "registry.lock")
            let execution = try ExecutionLease(directory: agent)
            try withExtendedLifetime((registry, execution)) {
                guard try !JobCenter.workspaceHasJobs(project.slug) else {
                    throw NHError.message("This workspace has a queued or active job. Finish or stop it before archiving.")
                }
                let original = AppPaths.projects.appendingPathComponent(project.slug)
                let archive = AppPaths.support.appendingPathComponent("archived-workspaces/\(project.id.uuidString)")
                let source = archiving ? original : archive
                let destination = archiving ? archive : original
                var next = lastSaved
                if archiving {
                    next.projects.removeAll { $0.id == project.id }
                    next.archivedProjects.append(project)
                } else {
                    next.archivedProjects.removeAll { $0.id == project.id }
                    next.projects.append(project)
                }
                try WorkspaceTransfer(root: AppPaths.support).move(from: source, to: destination, saving: next, in: store)
                lastSaved = next
                projects = next.projects; archivedProjects = next.archivedProjects
                if archiving && selectedProjectID == project.id { selectedProjectID = projects.first?.id }
                if !archiving { selectedProjectID = project.id }
                history.refresh(projects: projects)
            }
        } catch {
            // A cleanup failure can occur after the index committed. Reload
            // its authoritative state rather than leaving the old sidebar live.
            let message = error.localizedDescription
            load()
            storageMessage = message
        }
    }

    func updateSelected(_ mutate: (inout Project) -> Void) {
        guard let id = selectedProjectID else { return }
        updateProject(id: id, mutate)
    }

    /// A delayed form callback belongs to its original workspace even if the
    /// user has since selected another one. Archived/deleted work is left alone.
    func updateProject(id: Project.ID, _ mutate: (inout Project) -> Void) {
        guard let idx = projects.firstIndex(where: { $0.id == id }) else { return }
        mutate(&projects[idx])
        save()
    }

    /// Ensure the catalog is loaded once the pipeline is staged (post-install).
    func reloadScaffoldsIfNeeded() {
        if scaffolds.isEmpty { scaffolds = ScaffoldCatalog.load() }
    }

    // MARK: Persistence

    @discardableResult
    func save() -> Bool {
        guard storageAvailable else { return false }
        do {
            let next = Persisted(projects: projects, archivedProjects: archivedProjects)
            try store.save(next)
            lastSaved = next
            return true
        } catch {
            projects = lastSaved.projects
            archivedProjects = lastSaved.archivedProjects
            storageMessage = "This change could not be saved. Your previous settings were kept. \(error.localizedDescription)"
            return false
        }
    }

    func reloadSavedWorkspaces() {
        load()
        if storageAvailable { history.refresh(projects: projects) }
    }

    private func load() {
        do {
            if FileManager.default.fileExists(atPath: WorkspaceTransfer(root: AppPaths.support).journalURL.path) {
                let registry = try ExecutionLease(directory: AppPaths.support.appendingPathComponent("agent"), name: "registry.lock")
                let execution = try ExecutionLease(directory: AppPaths.support.appendingPathComponent("agent"))
                try withExtendedLifetime((registry, execution)) { try WorkspaceTransfer(root: AppPaths.support).recover() }
            }
            let saved: Persisted
            do { saved = try store.load() ?? Persisted(projects: []) }
            catch {
                saved = try store.recover()
                storageMessage = "Studio recovered the previous workspace index. The unreadable file was preserved; your latest unsaved edits may need to be entered again."
            }
            lastSaved = saved
            projects = saved.projects; archivedProjects = saved.archivedProjects
            storageAvailable = true
        } catch {
            storageAvailable = false
            storageMessage = "Your workspace settings could not be read or recovered. Studio has kept the files and paused editing. \(error.localizedDescription)"
        }
    }

    private func reattachManagedRuns() {
        Task {
            await JobCenter.shared.refresh()
            for job in JobCenter.shared.active {
                guard let project = projects.first(where: { $0.slug == job.project }), let root = job.output else { continue }
                if job.kind.contains("iterative") { run.reattach(project: project, root: root, jobID: job.id) }
                else if job.kind.contains("nise") { nise.reattach(root: root, jobID: job.id) }
                else if job.kind.contains("prediction") { prediction.reattach(root: root, jobID: job.id) }
                else if job.kind.contains("rfd3") || job.kind.contains("rfdiffusion3") { rfd3.reattach(root: root, jobID: job.id) }
            }
            if let root = run.campaignRoot, run.isRunning { metrics.start(root: root) }
        }
    }
}
