import Foundation

extension RFD4Request {
    var requiredComponents: [InstallComponent] {
        var result: [InstallComponent] = starting_structures.isEmpty || native_search ? [.rfd4] : []
        if needsPrediction {
            result.append(predictor == "boltz" ? .boltz : predictor == "esmfold2-fast-mlx" ? .esmfold2Fast : .esmfold2Full)
            if task == .ligand { result.append(.boltzAffinity) }
            if target_msa == "auto" { result.append(.boltz) }
        }
        if search != .native { result.append(task == .ligand ? .lasermpnn : task == .nanobody ? .abmpnn : .mpnn) }
        return Array(Set(result))
    }
}
