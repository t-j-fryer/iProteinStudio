import XCTest
@testable import StudioCore

final class EngineProgressTests: XCTestCase {
    func testHeartbeatDoesNotClaimComputeProgress() throws {
        let event = try XCTUnwrap(EngineProgressEvent(line: "IPROTEINSTUDIO_PROGRESS|engine=protenix|event=heartbeat|stage=template_embedding|pid=12|utc=2026-09-25T10:09:37Z|call=1|elapsed_s=60|since_host_progress_s=60|compute_progress=unknown"))
        XCTAssertEqual(event.stageLabel, "Template Embedding")
        XCTAssertTrue(event.explanation.contains("unknown"))
        XCTAssertNotNil(event.date)
        XCTAssertEqual(event.sinceProgress, "60")
    }

    func testReturnAndMalformedRecords() throws {
        let event = try XCTUnwrap(EngineProgressEvent(line: "IPROTEINSTUDIO_PROGRESS|engine=boltz2|event=host_return|stage=prediction_batch|extra=a=b"))
        XCTAssertTrue(event.explanation.contains("GPU completion was not measured"))
        XCTAssertNil(event.date)
        XCTAssertNil(EngineProgressEvent(line: "arbitrary log output"))
        XCTAssertNil(EngineProgressEvent(line: "IPROTEINSTUDIO_PROGRESS|engine=boltz2|event=success|stage=x"))
        XCTAssertNil(EngineProgressEvent(line: "IPROTEINSTUDIO_PROGRESS|event=heartbeat"))
    }
}
