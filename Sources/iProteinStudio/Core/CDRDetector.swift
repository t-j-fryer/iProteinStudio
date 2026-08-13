import Foundation

/// Runs the vendored `scripts/nanobody_cdrs.py` to resolve CDR ranges for a
/// scaffold sequence. Used to pass explicit `--nanobody-cdr-ranges` to the
/// pipeline so seed/calibration/contacts never fall back to a length-unaware
/// guess that can overflow short scaffolds.
enum CDRDetector {
    /// Returns e.g. "CDR1:26-33,CDR2:51-58,CDR3:98-108", or nil on any failure
    /// (in which case the caller simply omits the flag).
    static func ranges(forScaffold sequence: String) -> String? {
        let script = AppPaths.pipeline.appendingPathComponent("scripts/nanobody_cdrs.py")
        guard FileManager.default.fileExists(atPath: script.path) else { return nil }
        guard let python = pythonExecutable() else { return nil }

        let proc = Process()
        proc.executableURL = python
        proc.arguments = [script.path, "--seq", TemplateWriter.clean(sequence),
                          "--cdrs", "CDR1 CDR2 CDR3", "--emit", "ranges"]
        let out = Pipe()
        proc.standardOutput = out
        proc.standardError = Pipe()
        do { try proc.run() } catch { return nil }
        proc.waitUntilExit()
        guard proc.terminationStatus == 0 else { return nil }
        let data = out.fileHandleForReading.readDataToEndOfFile()
        let text = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
        // Sanity: must look like CDR3:start-end at minimum.
        guard let text, text.contains("CDR3:") else { return nil }
        return text
    }

    private static func pythonExecutable() -> URL? {
        let candidates = [
            "/usr/bin/python3",
            AppPaths.support.appendingPathComponent("venvs/NanoHunter_boltz/bin/python3").path,
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
        ]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) }
            .map { URL(fileURLWithPath: $0) }
    }
}
