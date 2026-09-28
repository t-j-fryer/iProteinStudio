import Foundation
import Darwin
import IOKit

/// Whole-machine observations, never attributed to the selected job. Missing
/// counters remain nil; they must not look like idle hardware or normal pressure.
public struct SystemResourceSnapshot: Sendable {
    public let date: Date
    public let uptime: TimeInterval
    public let totalBytes: UInt64
    public let usedBytes: UInt64?
    public let compressedBytes: UInt64?
    public let swapBytes: UInt64?
    public let swapOutBytes: UInt64?
    public let pressure: String?
    public let gpuPercent: Double?
    public let cpuTicks: [UInt64]?
    public let thermal: String

    public static func usedMemory(internalPages: UInt64, purgeablePages: UInt64,
                                  wiredPages: UInt64, compressedPages: UInt64,
                                  pageSize: UInt64, totalBytes: UInt64) -> UInt64 {
        // Exclude reclaimable file cache and purgeable pages. Compressor pages
        // are physical storage, not the larger logical uncompressed size.
        let nonpurgeable = internalPages > purgeablePages ? internalPages - purgeablePages : 0
        return min(totalBytes, (nonpurgeable + wiredPages + compressedPages) * pageSize)
    }

    public static func pressureName(_ value: Int32) -> String? {
        switch value { case 1: return "Normal"; case 2: return "Warning"; case 4: return "Critical"; default: return nil }
    }

    public static func gpuUtilization(_ statistics: [String: Any]) -> Double? {
        guard let number = statistics["Device Utilization %"] as? NSNumber else { return nil }
        let value = number.doubleValue
        return value.isFinite && (0...100).contains(value) ? value : nil
    }

    public static func cpuUtilization(previous: [UInt64]?, current: [UInt64]?) -> Double? {
        guard let previous, let current, previous.count == 4, current.count == 4,
              zip(current, previous).allSatisfy({ $0 >= $1 }) else { return nil }
        let delta = zip(current, previous).map { $0 - $1 }
        let total = delta.reduce(0, +)
        guard total > 0 else { return nil }
        return 100 * Double(total - delta[Int(CPU_STATE_IDLE)]) / Double(total)
    }

    public static func swapOutRate(previousBytes: UInt64?, currentBytes: UInt64?, seconds: Double) -> Double? {
        guard let previousBytes, let currentBytes, currentBytes >= previousBytes,
              seconds.isFinite, seconds > 0 else { return nil }
        return Double(currentBytes - previousBytes) / seconds
    }

    public static func capture() -> SystemResourceSnapshot {
        let host = mach_host_self()
        defer { mach_port_deallocate(mach_task_self_, host) }
        let total = ProcessInfo.processInfo.physicalMemory
        var vm = vm_statistics64()
        var count = mach_msg_type_number_t(MemoryLayout<vm_statistics64_data_t>.stride / MemoryLayout<integer_t>.stride)
        let vmOK = withUnsafeMutablePointer(to: &vm) { ptr in
            ptr.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                host_statistics64(host, HOST_VM_INFO64, $0, &count) == KERN_SUCCESS
            }
        }
        var page: vm_size_t = 0
        let pageOK = host_page_size(host, &page) == KERN_SUCCESS
        let memoryOK = vmOK && pageOK
        var swap = xsw_usage()
        var size = MemoryLayout<xsw_usage>.size
        let swapOK = sysctlbyname("vm.swapusage", &swap, &size, nil, 0) == 0
        var pressureValue: Int32 = 0
        size = MemoryLayout<Int32>.size
        let pressureOK = sysctlbyname("kern.memorystatus_vm_pressure_level", &pressureValue, &size, nil, 0) == 0
        var cpu = host_cpu_load_info()
        count = mach_msg_type_number_t(MemoryLayout<host_cpu_load_info_data_t>.stride / MemoryLayout<integer_t>.stride)
        let cpuOK = withUnsafeMutablePointer(to: &cpu) { ptr in
            ptr.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                host_statistics(host, HOST_CPU_LOAD_INFO, $0, &count) == KERN_SUCCESS
            }
        }
        let ticks = cpu.cpu_ticks
        let thermal: String
        switch ProcessInfo.processInfo.thermalState {
        case .nominal: thermal = "Normal"
        case .fair: thermal = "Warm"
        case .serious: thermal = "Serious"
        case .critical: thermal = "Critical"
        @unknown default: thermal = "Unavailable"
        }
        return SystemResourceSnapshot(
            date: Date(), uptime: ProcessInfo.processInfo.systemUptime, totalBytes: total,
            usedBytes: memoryOK ? usedMemory(internalPages: UInt64(vm.internal_page_count),
                purgeablePages: UInt64(vm.purgeable_count), wiredPages: UInt64(vm.wire_count),
                compressedPages: UInt64(vm.compressor_page_count), pageSize: UInt64(page), totalBytes: total) : nil,
            compressedBytes: memoryOK ? UInt64(vm.compressor_page_count) * UInt64(page) : nil,
            swapBytes: swapOK ? swap.xsu_used : nil,
            swapOutBytes: memoryOK ? vm.swapouts * UInt64(page) : nil,
            pressure: pressureOK ? pressureName(pressureValue) : nil,
            gpuPercent: readGPU(),
            cpuTicks: cpuOK ? [UInt64(ticks.0), UInt64(ticks.1), UInt64(ticks.2), UInt64(ticks.3)] : nil,
            thermal: thermal)
    }

    private static func readGPU() -> Double? {
        // Driver-provided diagnostics, not a stable Metal API. Availability is
        // optional. Never substitute the app's own Metal allocations for GPU load.
        var iterator: io_iterator_t = 0
        guard IOServiceGetMatchingServices(kIOMainPortDefault, IOServiceMatching("IOAccelerator"), &iterator) == KERN_SUCCESS else { return nil }
        defer { IOObjectRelease(iterator) }
        var readings: [Double?] = []
        while true {
            let service = IOIteratorNext(iterator)
            guard service != 0 else { break }
            defer { IOObjectRelease(service) }
            let value = IORegistryEntryCreateCFProperty(service, "PerformanceStatistics" as CFString, kCFAllocatorDefault, 0)?.takeRetainedValue()
            readings.append((value as? [String: Any]).flatMap(gpuUtilization))
        }
        // Apple Silicon exposes one integrated device. Avoid inventing an
        // aggregate percentage on machines with multiple accelerators.
        return readings.count == 1 ? readings[0] : nil
    }
}
