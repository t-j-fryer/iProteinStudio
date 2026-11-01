import Foundation

extension RFD4Request {
    var requiredComponents: [InstallComponent] {
        var result: [InstallComponent] = starting_structures.isEmpty || native_search ? [.rfd4] : []
        if needsPrediction {
            if let option = RFD4Predictor(rawValue: predictor) { result.append(option.component) }
            if task == .ligand { result.append(.boltzAffinity) }
            if target_msa == "auto" || scaffold_msa == "auto" { result.append(.boltz) }
        }
        if search != .native { result.append(task == .ligand ? .lasermpnn : task == .nanobody ? .abmpnn : .mpnn) }
        return Array(Set(result))
    }
}
