from fastapi.testclient import TestClient

from media_failure_tracker.media_failure_service import get_client, service


class RecordingInfraiClient:
    def __init__(self) -> None:
        self.payload = None

    def capture_error(self, payload):
        self.payload = payload
        return {"event_id": "evt_test_42"}


def test_delivery_failure_is_held_and_captured_with_a_stable_fingerprint():
    recorder = RecordingInfraiClient()
    service.dependency_overrides[get_client] = lambda: recorder
    try:
        response = TestClient(service).post(
            "/failures",
            json={
                "asset_id": "asset_17",
                "job_id": "job_91",
                "creator_id": "creator_4",
                "stage": "creator_delivery",
                "exception_type": "DeliveryReceiptMismatch",
                "exception_message": "creator receipt did not match the rendered asset",
            },
        )
    finally:
        service.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "asset_id": "asset_17",
        "job_id": "job_91",
        "action": "hold_creator_delivery",
        "capture_event_id": "evt_test_42",
    }
    assert recorder.payload["fingerprint"] == [
        "media-agent",
        "creator_delivery",
        "DeliveryReceiptMismatch",
    ]
    assert recorder.payload["context"]["decision"] == "hold_creator_delivery"

