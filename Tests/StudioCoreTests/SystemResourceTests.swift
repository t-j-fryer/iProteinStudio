import XCTest
@testable import StudioCore

final class SystemResourceTests: XCTestCase {
    func testMemoryExcludesPurgeableWithoutUnderflowAndIncludesCompressorOnce() {
        XCTAssertEqual(SystemResourceSnapshot.usedMemory(internalPages: 100, purgeablePages: 20,
            wiredPages: 30, compressedPages: 10, pageSize: 4096, totalBytes: 1_000_000), 120 * 4096)
        XCTAssertEqual(SystemResourceSnapshot.usedMemory(internalPages: 10, purgeablePages: 20,
            wiredPages: 30, compressedPages: 10, pageSize: 4096, totalBytes: 1_000_000), 40 * 4096)
        XCTAssertEqual(SystemResourceSnapshot.usedMemory(internalPages: 100, purgeablePages: 0,
            wiredPages: 30, compressedPages: 10, pageSize: 4096, totalBytes: 1000), 1000)
    }
    func testMissingOrInvalidGPUMustNotLookIdle() {
        XCTAssertNil(SystemResourceSnapshot.gpuUtilization([:]))
        XCTAssertNil(SystemResourceSnapshot.gpuUtilization(["Device Utilization %": 101]))
        XCTAssertNil(SystemResourceSnapshot.gpuUtilization(["Device Utilization %": Double.nan]))
        XCTAssertEqual(SystemResourceSnapshot.gpuUtilization(["Device Utilization %": 0]), 0)
        XCTAssertEqual(SystemResourceSnapshot.gpuUtilization(["Device Utilization %": 37]), 37)
        XCTAssertNil(SystemResourceSnapshot.pressureName(0))
        XCTAssertEqual(SystemResourceSnapshot.pressureName(4), "Critical")
    }
    func testCPUDeltaAndCounterReset() {
        XCTAssertNil(SystemResourceSnapshot.cpuUtilization(previous: nil, current: [1, 1, 1, 1]))
        XCTAssertEqual(SystemResourceSnapshot.cpuUtilization(previous: [10, 10, 10, 10], current: [20, 20, 80, 20]), 30)
        XCTAssertNil(SystemResourceSnapshot.cpuUtilization(previous: [10, 10, 10, 10], current: [0, 20, 80, 20]))
        XCTAssertNil(SystemResourceSnapshot.cpuUtilization(previous: [10, 10, 10, 10], current: [10, 10, 10, 10]))
    }
    func testSwapRateUsesTrafficNotAllocatedSwap() {
        XCTAssertEqual(SystemResourceSnapshot.swapOutRate(previousBytes: 1000, currentBytes: 3000, seconds: 2), 1000)
        XCTAssertEqual(SystemResourceSnapshot.swapOutRate(previousBytes: 3000, currentBytes: 3000, seconds: 2), 0)
        XCTAssertNil(SystemResourceSnapshot.swapOutRate(previousBytes: 3000, currentBytes: 1000, seconds: 2))
        XCTAssertNil(SystemResourceSnapshot.swapOutRate(previousBytes: nil, currentBytes: 1000, seconds: 2))
        XCTAssertNil(SystemResourceSnapshot.swapOutRate(previousBytes: 1, currentBytes: 2, seconds: 0))
    }
    func testLiveCaptureReturnsPlausibleOrExplicitlyUnavailableValues() {
        let s = SystemResourceSnapshot.capture()
        XCTAssertGreaterThan(s.totalBytes, 0)
        if let used = s.usedBytes { XCTAssertLessThanOrEqual(used, s.totalBytes) }
        if let gpu = s.gpuPercent { XCTAssertTrue((0...100).contains(gpu)) }
        XCTAssertLessThan(abs(s.date.timeIntervalSinceNow), 10)
        print("Resource capture: total=\(s.totalBytes), used=\(String(describing: s.usedBytes)), pressure=\(s.pressure ?? "unavailable"), swap=\(String(describing: s.swapBytes)), GPU=\(String(describing: s.gpuPercent))")
    }
}
