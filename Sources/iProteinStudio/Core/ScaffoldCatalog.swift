import Foundation

/// A nanobody (VHH) scaffold from the bundled catalog.
struct Scaffold: Identifiable, Hashable {
    let id: String            // scaffold_id
    let displayName: String
    let recommendedUse: String
    let sequence: String
    let notes: String
    var cdrRanges: String = ""

    var shortName: String { displayName }
}

/// Loads the vendored scaffold catalog (examples/nanobody_scaffolds/catalog.tsv).
enum ScaffoldCatalog {
    static func load() -> [Scaffold] {
        // The app catalogue matches the snapshot submitted by this version; do not
        // hide newly bundled frameworks behind an older staged catalogue.
        let candidates: [URL?] = [
            AppPaths.bundledPipeline?.appendingPathComponent("examples/nanobody_scaffolds/catalog.tsv"),
            AppPaths.isPipelineStaged ? AppPaths.catalogTSV : nil,
        ]
        guard let url = candidates.compactMap({ $0 }).first(where: { FileManager.default.fileExists(atPath: $0.path) }),
              let text = try? String(contentsOf: url, encoding: .utf8)
        else { return [] }

        var rows = text.split(separator: "\n", omittingEmptySubsequences: true).map(String.init)
        guard !rows.isEmpty else { return [] }
        let header = rows.removeFirst().split(separator: "\t").map(String.init)
        func idx(_ name: String) -> Int? { header.firstIndex(of: name) }

        let iID = idx("scaffold_id"), iName = idx("display_name")
        let iUse = idx("recommended_use"), iSeq = idx("sequence"), iNotes = idx("notes")

        var out: [Scaffold] = []
        for row in rows {
            let cols = row.components(separatedBy: "\t")
            func col(_ i: Int?) -> String { (i.flatMap { $0 < cols.count ? cols[$0] : nil }) ?? "" }
            let seq = col(iSeq)
            guard !seq.isEmpty else { continue }
            out.append(Scaffold(
                id: col(iID).isEmpty ? seq.prefix(8).description : col(iID),
                displayName: col(iName).isEmpty ? col(iID) : col(iName),
                recommendedUse: col(iUse),
                sequence: seq,
                notes: col(iNotes),
                cdrRanges: ["cdr1", "cdr2", "cdr3"].enumerated().map { "CDR\($0.offset + 1):" + col(idx($0.element + "_range_1based")) }.joined(separator: ",")
            ))
        }
        return out
    }
}
