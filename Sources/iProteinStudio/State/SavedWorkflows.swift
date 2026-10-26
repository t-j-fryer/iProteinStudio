import Foundation

extension AppState {
    @discardableResult
    func saveWorkflow(name: String, project: Project, route: DesignWorkflowRoute) -> Bool {
        guard storageAvailable else { return false }
        let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return false }
        do {
            let encoder = JSONEncoder()
            let data: Data
            switch route {
            case .rfd4: data = try encoder.encode(project.rfd4)
            case .rfd3: data = try encoder.encode(project.rfd3)
            case .proteinHunter, .rfd3Monomer: data = try encoder.encode(project.request)
            case .nise: data = try encoder.encode(project.nise)
            }
            savedWorkflows.append(SavedDesignWorkflow(name: name, intention: project.designIntention ?? .minibinder,
                                                      route: route, parameters: data))
            return save()
        } catch { storageMessage = "Could not save this workflow: \(error.localizedDescription)"; return false }
    }

    @discardableResult
    func openWorkflow(_ workflow: SavedDesignWorkflow, projectID: UUID) -> Bool {
        guard storageAvailable else { return false }
        guard workflow.schema == 1 else { storageMessage = "This saved workflow needs a newer Studio version. Its settings were preserved."; return false }
        guard let index = projects.firstIndex(where: { $0.id == projectID }) else { return false }
        do {
            var project = projects[index]
            let decoder = JSONDecoder()
            switch workflow.route {
            case .rfd4: project.rfd4 = try decoder.decode(RFD4Request.self, from: workflow.parameters); project.diffusionEngine = "rfd4"
            case .rfd3: project.rfd3 = try decoder.decode(RFD3Request.self, from: workflow.parameters); project.diffusionEngine = "rfd3"
            case .proteinHunter, .rfd3Monomer: project.request = try decoder.decode(DesignRequest.self, from: workflow.parameters)
            case .nise: project.nise = try decoder.decode(NISERequest.self, from: workflow.parameters)
            }
            project.designIntention = workflow.intention; project.preferredMode = workflow.route.mode
            projects[index] = project
            return save()
        } catch {
            storageMessage = "This workflow could not be opened. Its saved settings were preserved: \(error.localizedDescription)"
            return false
        }
    }
}
