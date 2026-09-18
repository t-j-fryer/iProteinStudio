import Foundation
import CryptoKit

enum StudioWorkflow: String, Codable {
    case iterative, nise, rfdiffusion3, prediction
    var label: String { rawValue }
}

@main
struct NISEResultsContractHarness {
    static func main() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent("nise-results-" + UUID().uuidString)
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: root) }
        func write(_ path: String, _ object: Any) throws {
            let url = root.appendingPathComponent(path)
            try fm.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try JSONSerialization.data(withJSONObject: object).write(to: url, options: .atomic)
        }
        func structure(_ path: String) throws {
            let url = root.appendingPathComponent(path)
            try fm.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try "ATOM fixture".write(to: url, atomically: true, encoding: .utf8)
        }
        func receipt(_ directory: String, _ name: String, copied: Bool = false) throws {
            let pdb = directory + "/out/" + name + ".pdb"
            try structure(pdb)
            try write(directory + "/completed.json", ["input": ["sequence": "AXAA", "phase": "structure"],
                "result": ["prediction": ["name": name, "pdb": copied ? "/old/copied/run/" + pdb : pdb,
                                           "ligand_plddt": 77.0, "pbind": NSNull()]], "files": [pdb: "fixture"]])
        }
        try write("config.json", ["num_starts": 3, "phase0_refine_cycles": 2])
        try receipt("phase0/cycle00/L000", "L000", copied: true)
        try receipt("phase0/cycle00/L001", "L001")
        try structure("phase0/cycle00/L002/out/unfinished.pdb")
        try receipt("phase0/cycle00/_batches/structure-copy/L000", "duplicate-must-not-appear")
        try write("phase0/cycle00/initial_geometry.json", ["passed": ["L000": true, "L001": false],
                "atom_checks": ["L001": ["failures": ["terminal atom not exposed"]]]])
        try receipt("phase0/cycle01/fold/L000_c1_0", "L000_c1_0")
        try structure("phase0/cycle01/fold/L000_c1_1/yaml/input.yaml")
        try write("phase0/cycle01/nesso/selection.json", ["input": ["sequences": ["a": "AAA", "b": "ACA", "c": "ADA"]], "result": ["a", "b"]])
        var snapshot = NISEResultsLoader.load(root: root)
        precondition(snapshot.records.count == 3)
        let initial = snapshot.stages.first { $0.id == "0|0" }!
        precondition(initial.planned == 3 && initial.completed == 2 && initial.geometryPassed == 1 && initial.geometryFailed == 1)
        let refinement = snapshot.stages.first { $0.id == "0|1" }!
        precondition(refinement.planned == 2 && refinement.completed == 1 && refinement.awaitingChecks == 1)
        precondition(refinement.screened == 3 && refinement.shortlisted == 2)
        let pending = snapshot.records.first { $0.item.title == "L000_c1_0" }!
        precondition(pending.geometryPassed == nil && pending.eligible == nil)
        precondition(!pending.item.metrics.contains { $0.kind == .bindingProbability || $0.kind == .rankingScore })
        precondition(snapshot.records.first { $0.item.title == "L001" }!.item.failedFilters == ["terminal atom not exposed"])
        precondition(Set(snapshot.items.map(\.groupID)).count == 2)
        precondition(snapshot.items.allSatisfy { $0.isHit == nil })

        // The scored candidate replaces, rather than duplicates, the live receipt.
        let candidate: [String: Any] = ["name": "L000_c1_0", "pdb": "phase0/cycle01/fold/L000_c1_0/out/L000_c1_0.pdb",
            "cycle": 1, "sequence": "ACAA", "geometry_passed": true, "passed": true,
            "score_status": "not_evaluated", "score": NSNull()]
        try write("candidates/L000_c1_0.json", candidate)
        snapshot = NISEResultsLoader.load(root: root)
        precondition(snapshot.records.count == 3)
        let waiting = snapshot.records.first { $0.id == pending.id }!
        precondition(waiting.geometryPassed == true && waiting.eligible == nil)
        var scored = candidate; scored["score_status"] = "scored"; scored["score"] = 1.7; scored["pbind"] = 0.9
        try write("candidates/L000_c1_0.json", scored)
        snapshot = NISEResultsLoader.load(root: root)
        precondition(snapshot.records.count == 3 && snapshot.records.first { $0.id == pending.id }!.eligible == true)

        // Phase 1 cycle01 has separate grouping and only saved beam membership means advanced.
        try receipt("cycle01/fold/c01_t0_n0_s0", "c01_t0_n0_s0")
        try receipt("cycle01/fold/c01_t0_n0_s1", "c01_t0_n0_s1")
        try write("cycle01/advancement.json", ["trajectories": [["trajectory": 0, "selected": ["c01_t0_n0_s1"]]]])
        snapshot = NISEResultsLoader.load(root: root)
        precondition(snapshot.records.filter { $0.phase == .optimisation }.count == 2)
        precondition(snapshot.records.first { $0.item.title == "c01_t0_n0_s1" }?.advanced == true)
        precondition(snapshot.records.first { $0.item.title == "c01_t0_n0_s0" }?.advanced == false)
        precondition(snapshot.records.first { $0.item.title == "L000_c1_0" }?.advanced == nil)

        // NESSO is useful before any fold/candidate record exists. Preserve its
        // probability and entropy separately from the later Boltz probability.
        let scores: [String: Any] = ["affinity_probability_binary": 0.73, "entropy_crop_pl": 0.2, "entropy_pl": 0.4]
        try write("cycle01/nesso/c01_t0_n0_s0/completed.json", ["input": ["sequence": "AXAA"], "result": ["scores": scores]])
        snapshot = NISEResultsLoader.load(root: root)
        precondition(snapshot.screening.first { $0.name == "c01_t0_n0_s0" }?.selected == nil)
        try write("cycle01/nesso/selection.json", ["input": ["sequences": ["c01_t0_n0_s0": "AXAA", "screened_out": "AAAA"],
            "scores": ["c01_t0_n0_s0": scores, "screened_out": scores],
            "assessments": ["c01_t0_n0_s0": ["score": 1.53], "screened_out": ["score": 1.53]]], "result": ["c01_t0_n0_s0"]])
        snapshot = NISEResultsLoader.load(root: root)
        precondition(snapshot.screening.contains { $0.name == "screened_out" && $0.selected == false })
        let nessoFold = snapshot.records.first { $0.item.title == "c01_t0_n0_s0" }!
        precondition(nessoFold.item.metrics.contains { $0.kind == .nessoBindingProbability && $0.value == 0.73 })
        precondition(nessoFold.item.metrics.contains { $0.kind == .nessoScreeningScore && $0.value == 1.53 })
        precondition(!nessoFold.item.metrics.contains { $0.kind == .bindingProbability })
        let completedData = try Data(contentsOf: root.appendingPathComponent("cycle01/fold/c01_t0_n0_s0/completed.json"))
        let digest = SHA256.hash(data: completedData).map { String(format: "%02x", $0) }.joined()
        let affinity: [String: Any] = ["input": ["structure_receipt_sha256": digest], "result": ["prediction": ["name": "c01_t0_n0_s0", "pbind": 0.81]]]
        try write("cycle01/fold/c01_t0_n0_s0/affinity_completed.json", affinity)
        snapshot = NISEResultsLoader.load(root: root)
        precondition(snapshot.records.first { $0.id == nessoFold.id }!.item.metrics.contains { $0.kind == .bindingProbability && $0.value == 0.81 })
        var invalidAffinity = affinity; invalidAffinity["input"] = ["structure_receipt_sha256": "wrong"]
        try write("cycle01/fold/c01_t0_n0_s0/affinity_completed.json", invalidAffinity)
        snapshot = NISEResultsLoader.load(root: root)
        precondition(!snapshot.records.first { $0.id == nessoFold.id }!.item.metrics.contains { $0.kind == .bindingProbability })

        // RFdiffusion3's committed initial set has no invented Boltz confidence.
        try structure("phase0/cycle00/L003_ref.pdb")
        try write("phase0/cycle00/initial_backbones.json", ["result": ["L003": "phase0/cycle00/L003_ref.pdb"]])
        snapshot = NISEResultsLoader.load(root: root)
        let rfd = snapshot.records.first { $0.item.title == "L003" }!
        precondition(rfd.item.scoreSource == "RFdiffusion3" && rfd.item.metrics.isEmpty)

        // Phase labels follow saved refinement settings across backbone routes.
        try write("config.json", ["num_starts": 3, "phase0_refine_cycles": 3, "backbone_method": "rfdiffusion3"])
        snapshot = NISEResultsLoader.load(root: root)
        precondition(snapshot.stages.first { $0.id == "0|4" }?.title == "Unrestrained geometry gate")
        precondition(snapshot.stages.first { $0.id == "0|5" }?.title == "Seed expansion")

        // Arbitrary outside references, escaping symlinks and missing structures are not rendered.
        try write("candidates/escape.json", ["name": "escape", "pdb": "../outside.pdb"])
        try write("candidates/missing.json", ["name": "missing", "pdb": "absent.pdb"])
        try fm.createSymbolicLink(atPath: root.appendingPathComponent("external.pdb").path, withDestinationPath: "/etc/hosts")
        try write("candidates/symlink.json", ["name": "symlink", "pdb": "external.pdb"])
        snapshot = NISEResultsLoader.load(root: root)
        precondition(!snapshot.warnings.isEmpty && snapshot.records.count == 6)
        precondition(!snapshot.items.contains { ["escape", "missing", "symlink"].contains($0.title) })

        // A malformed committed receipt is reported, while an unfinished raw
        // structure without any receipt remains ordinary pending work.
        let broken = root.appendingPathComponent("phase0/cycle01/fold/broken/completed.json")
        try fm.createDirectory(at: broken.deletingLastPathComponent(), withIntermediateDirectories: true)
        try "{truncated".write(to: broken, atomically: true, encoding: .utf8)
        snapshot = NISEResultsLoader.load(root: root)
        precondition(snapshot.records.count == 6 && !snapshot.warnings.isEmpty)

        // Apo rows retain their exact identity; they do not inflate Phase 1 counts.
        try structure("apo.pdb")
        try write("preorg.json", ["ranked": [["name": "c01_t0_n0_s1", "apo_pdb": "apo.pdb", "preorg_rmsd": 0.5, "combined_score": 2.0]]])
        snapshot = NISEResultsLoader.load(root: root)
        precondition(snapshot.records.filter { $0.phase == .finalChecks }.count == 1)
        precondition(snapshot.stages.first { $0.id == "1|1" }?.completed == 2)
        precondition(snapshot.items.allSatisfy { $0.isHit == nil })
        print("PASS NISE live checkpoints, phase/stage separation, pending checks, scoring promotion, NESSO counts, RFD3, beam selection, final checks and portable path safety")

        if let path = ProcessInfo.processInfo.environment["STUDIO_NISE_LIVE_RUN"] {
            let live = NISEResultsLoader.load(root: URL(fileURLWithPath: path))
            let stage = live.stages.first { $0.id == "0|0" }!
            precondition(stage.completed == 1000 && stage.geometryPassed == 422 && stage.geometryFailed == 578)
            precondition(live.stages.first { $0.id == "0|1" }!.completed >= 370)
            precondition(live.stages.first { $0.id == "0|1" }!.planned == 1266)
            precondition(live.warnings.isEmpty)
            print("PASS existing biotin run: \(live.items.count) structures visible; 1000 starts, 422 initial geometry pass; \(live.stages.first { $0.id == "0|1" }!.completed)/1266 cycle01 folds")
        }
    }
}
