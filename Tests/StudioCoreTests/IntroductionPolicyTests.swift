import XCTest
@testable import StudioCore

final class IntroductionPolicyTests: XCTestCase {
    func testOnlyFreshUndismissedSetupReceivesAutomaticIntroduction() {
        for mask in 0..<32 {
            let shouldShow = IntroductionPolicy.shouldPresent(
                hasSeen: mask & 1 != 0, installed: mask & 2 != 0,
                hasSavedWork: mask & 4 != 0, installationBusy: mask & 8 != 0,
                recoveryNeeded: mask & 16 != 0)
            XCTAssertEqual(shouldShow, mask == 0, "Routing combination \(mask)")
        }
    }
}
