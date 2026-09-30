import SwiftUI

/// All workflows edit the same per-engine scientific settings. The bundled
/// registry is also read by the Python adapters, avoiding a second defaults list.
struct PredictionSettingsView: View {
    @Binding var settings: [String: [String: Int]]
    private var defaults: [String: [String: Int]] {
        guard let file = AppPaths.bundledPipeline?.appendingPathComponent("scripts/prediction_profiles.json"),
              let data = try? Data(contentsOf: file),
              let values = try? JSONDecoder().decode([String: [String: Int]].self, from: data) else { return [:] }
        return values
    }
    private func binding(_ engine: String, _ key: String) -> Binding<Int> {
        Binding(get: { settings[engine]?[key] ?? defaults[engine]?[key] ?? 0 },
                set: { settings[engine, default: [:]][key] = $0 })
    }
    private func name(_ engine: String) -> String {
        ["boltz": "Boltz2", "intellifold": "IntelliFold Flash", "intellifold-full": "IntelliFold Full",
         "protenix-v2": "Protenix v2", "protenix-mini": "Protenix Mini",
         "protenix-constraint-v0.5": "Protenix Constraint", "openfold-3-mlx": "OpenFold3",
         "esmfold2-full-mlx": "ESMFold2 Full", "esmfold2-fast-mlx": "ESMFold2 Fast"][engine] ?? engine
    }
    var body: some View {
        DisclosureGroup("Prediction accuracy & compute") {
            if defaults.isEmpty {
                Text("Prediction settings are unavailable. Reinstall the app before starting a new run.")
                    .foregroundStyle(.red)
            } else {
                Text("Settings apply when an engine is selected, including verification. MSA depth includes the query; 0 preserves the full supplied alignment. Designed binders retain their single-sequence policy. Smaller budgets may change predictions.")
                    .font(.caption).foregroundStyle(.secondary)
                ForEach(defaults.keys.sorted(), id: \.self) { engine in
                    DisclosureGroup(name(engine)) {
                        Grid(alignment: .leading) {
                            if engine != "esmfold2-fast-mlx" {
                                GridRow {
                                    Text("Maximum MSA rows")
                                    EditableIntStepper(value: binding(engine, "msa_depth"), in: 0...1_000_000,
                                                       accessibilityLabel: "\(engine) MSA depth")
                                }
                            } else {
                                Text("Sequence-only model")
                            }
                            GridRow {
                                Text("Diffusion steps")
                                EditableIntStepper(value: binding(engine, "diffusion_steps"), in: 1...10_000,
                                                   accessibilityLabel: "\(engine) diffusion steps")
                            }
                            GridRow {
                                Text(engine.hasPrefix("esmfold2") ? "Trunk loops" : "Recycles")
                                EditableIntStepper(value: binding(engine, "recycles"), in: 0...1_000,
                                                   accessibilityLabel: "\(engine) recycles or loops")
                            }
                        }
                    }
                }
                Button("Restore prediction defaults") { settings = [:] }
            }
        }
    }
}
