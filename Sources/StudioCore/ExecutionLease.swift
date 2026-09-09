import Foundation
import Darwin

/// Uses the same flock files as the Python job broker. Keep the lease alive for
/// the entire protected operation; never remove or replace a lock file.
public final class ExecutionLease {
    private let descriptor: Int32
    public init(directory: URL, name: String = "execution.lock") throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        descriptor = Darwin.open(directory.appendingPathComponent(name).path, O_CREAT | O_RDWR, 0o600)
        guard descriptor >= 0 else { throw LeaseError.unavailable }
        guard flock(descriptor, LOCK_EX | LOCK_NB) == 0 else {
            Darwin.close(descriptor)
            throw LeaseError.busy
        }
    }
    deinit { flock(descriptor, LOCK_UN); Darwin.close(descriptor) }
    public enum LeaseError: LocalizedError {
        case busy, unavailable
        public var errorDescription: String? {
            switch self {
            case .busy: return "Studio is using these files. Wait for active work to finish before changing them."
            case .unavailable: return "Studio could not verify exclusive access to its managed files."
            }
        }
    }
}
