import Foundation

enum MacEnergyMode: Int, Equatable {
    case automatic = 0, low = 1, high = 2
    var label: String { switch self { case .automatic: return "Automatic"; case .low: return "Low Power"; case .high: return "High Power" } }
}

struct MacPowerSnapshot: Equatable {
    enum Source: String { case adapter = "Power adapter", battery = "Battery", unknown = "Unknown power source" }
    let source: Source
    let adapterMode: MacEnergyMode?
    let batteryMode: MacEnergyMode?
    let highPowerReported: Bool
    let hasBattery: Bool
    var activeMode: MacEnergyMode? { source == .adapter ? adapterMode : source == .battery ? batteryMode : nil }
    var summary: String { "\(activeMode?.label ?? "Mode not reported") · \(source.rawValue)" }
    var canEnableHigh: Bool { source == .adapter && highPowerReported && adapterMode != nil && adapterMode != .high }

    static func parse(custom: String, battery: String, capabilities: String) throws -> Self {
        var section: Source = .unknown
        var profiles: [Source: [String: Int]] = [:]
        for raw in custom.split(separator: "\n") {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.hasSuffix(":") {
                section = line == "AC Power:" ? .adapter : line == "Battery Power:" ? .battery : .unknown
                continue
            }
            let fields = line.split(whereSeparator: \.isWhitespace)
            if section != .unknown, fields.count == 2,
               ["powermode", "lowpowermode", "highpowermode"].contains(String(fields[0])), let n = Int(fields[1]) {
                let key = String(fields[0])
                if let old = profiles[section]?[key], old != n { throw PowerModeError.unreadable }
                profiles[section, default: [:]][key] = n
            }
        }
        func mode(_ source: Source) -> MacEnergyMode? {
            let values = profiles[source] ?? [:]
            if let n = values["powermode"] { return MacEnergyMode(rawValue: n) }
            if values["highpowermode"] == 1 { return .high }
            return values["lowpowermode"].flatMap(MacEnergyMode.init(rawValue:))
        }
        for values in profiles.values {
            if let modern = values["powermode"], let legacy = values["lowpowermode"], modern != legacy { throw PowerModeError.unreadable }
            if values["highpowermode"] == 1, let modern = values["powermode"], modern != 2 { throw PowerModeError.unreadable }
        }
        let adapter = mode(.adapter), onBattery = mode(.battery)
        guard adapter != nil || onBattery != nil else { throw PowerModeError.unreadable }
        let source: Source = battery.contains("Now drawing from 'AC Power'") ? .adapter : battery.contains("Now drawing from 'Battery Power'") ? .battery : .unknown
        let reportsHigh = adapter == .high || profiles[.adapter]?["powermode"] != nil ||
            capabilities.split(whereSeparator: \.isWhitespace).contains("highpowermode")
        return Self(source: source, adapterMode: adapter, batteryMode: onBattery, highPowerReported: reportsHigh, hasBattery: battery.contains("InternalBattery"))
    }

    func command(for mode: MacEnergyMode) throws -> PowerModeCommand {
        guard source == .adapter else { throw PowerModeError.connectAdapter }
        guard adapterMode != nil else { throw PowerModeError.unreadable }
        guard mode != .high || highPowerReported else { throw PowerModeError.notReported }
        return PowerModeCommand(mode: mode)
    }
}

struct PowerModeCommand: Equatable {
    let mode: MacEnergyMode
    // Only enum-controlled constants reach the privileged command. Never -a/-b.
    var shell: String { "/usr/bin/pmset -c powermode \(mode.rawValue)" }
    var appleScript: String {
        "do shell script \"\(shell)\" with administrator privileges with prompt \"iProteinStudio will set the power adapter to \(mode.label). This affects the whole Mac and stays set until you change it.\""
    }
}

enum PowerModeError: LocalizedError {
    case unreadable, connectAdapter, notReported, cancelled, authorizationFailed, notConfirmed
    var errorDescription: String? {
        switch self {
        case .unreadable: return "macOS power mode could not be read. Check Power Settings; Studio has not assumed a performance mode."
        case .connectAdapter: return "Connect the power adapter to use this shortcut. Battery settings are managed separately in Power Settings."
        case .notReported: return "This Mac does not report High Power support to Studio. Open Power Settings to check its available modes."
        case .cancelled: return "Power-mode change cancelled."
        case .authorizationFailed: return "macOS could not apply the power-mode change. Open Power Settings to review it."
        case .notConfirmed: return "macOS did not confirm the requested power-adapter mode. Check Power Settings."
        }
    }
}
