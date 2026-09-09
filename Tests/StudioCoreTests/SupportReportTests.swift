import XCTest
@testable import StudioCore

final class SupportReportTests: XCTestCase {
    func testArbitraryScientificAndSecretContentIsNotExported() {
        let sensitive = "ACDEFGHIKLMNPQRST /Users/person/secret-project token=very-secret C[C@@H](O)C"
        let report = SupportReport.make(version: "test", system: "test OS", memoryBytes: 0,
                                        message: "Could not write " + sensitive,
                                        log: ["PBFAIL|" + sensitive, "Authorization: Bearer secret"])
        XCTAssertTrue(report.contains("Storage or saved settings"))
        XCTAssertTrue(report.contains("PBFAIL"))
        for term in ["ACDEFG", "/Users/", "very-secret", "C[C@@H]", "Bearer"] {
            XCTAssertFalse(report.contains(term))
        }
    }
}
