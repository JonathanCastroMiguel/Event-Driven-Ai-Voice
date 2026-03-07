"""Unit tests for WebRTC signaling endpoints."""

from __future__ import annotations

from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.routes.calls import CallSessionEntry, _sessions


@pytest.fixture(autouse=True)
def clear_sessions():
    """Clear the in-memory session registry between tests."""
    _sessions.clear()
    yield
    _sessions.clear()


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /api/v1/calls — create call session
# ---------------------------------------------------------------------------


class TestCreateCall:
    def test_creates_session(self, client: TestClient) -> None:
        resp = client.post("/api/v1/calls")
        assert resp.status_code == 201
        data = resp.json()
        assert "call_id" in data
        assert data["status"] == "created"
        UUID(data["call_id"])

    def test_returns_unique_ids(self, client: TestClient) -> None:
        r1 = client.post("/api/v1/calls").json()
        r2 = client.post("/api/v1/calls").json()
        assert r1["call_id"] != r2["call_id"]

    def test_session_stored_in_registry(self, client: TestClient) -> None:
        resp = client.post("/api/v1/calls")
        call_id = UUID(resp.json()["call_id"])
        assert call_id in _sessions
        assert _sessions[call_id].call_id == call_id

    @patch("src.api.routes.calls.settings")
    def test_max_concurrent_calls(self, mock_settings, client: TestClient) -> None:
        mock_settings.max_concurrent_calls = 2

        client.post("/api/v1/calls")
        client.post("/api/v1/calls")
        resp = client.post("/api/v1/calls")
        assert resp.status_code == 503
        assert resp.json()["detail"] == "max_calls_exceeded"


# ---------------------------------------------------------------------------
# POST /api/v1/calls/{call_id}/offer — SDP proxy
# ---------------------------------------------------------------------------


class TestHandleOffer:
    def test_offer_without_session_returns_404(self, client: TestClient) -> None:
        fake_id = str(uuid4())
        resp = client.post(
            f"/api/v1/calls/{fake_id}/offer",
            json={"sdp": "v=0\r\n", "type": "offer"},
        )
        assert resp.status_code == 404

    def test_offer_requires_valid_body(self, client: TestClient) -> None:
        create_resp = client.post("/api/v1/calls")
        call_id = create_resp.json()["call_id"]

        resp = client.post(f"/api/v1/calls/{call_id}/offer", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/v1/calls/{call_id} — end call
# ---------------------------------------------------------------------------


class TestDeleteCall:
    def test_delete_without_session_returns_404(self, client: TestClient) -> None:
        fake_id = str(uuid4())
        resp = client.delete(f"/api/v1/calls/{fake_id}")
        assert resp.status_code == 404

    def test_delete_removes_session(self, client: TestClient) -> None:
        create_resp = client.post("/api/v1/calls")
        call_id = create_resp.json()["call_id"]

        resp = client.delete(f"/api/v1/calls/{call_id}")
        assert resp.status_code == 204
        assert UUID(call_id) not in _sessions

    def test_delete_idempotent_fails_second_time(self, client: TestClient) -> None:
        create_resp = client.post("/api/v1/calls")
        call_id = create_resp.json()["call_id"]

        client.delete(f"/api/v1/calls/{call_id}")
        resp = client.delete(f"/api/v1/calls/{call_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# CallSessionEntry
# ---------------------------------------------------------------------------


class TestCallSessionEntry:
    def test_initial_state(self) -> None:
        call_id = uuid4()
        entry = CallSessionEntry(call_id)
        assert entry.call_id == call_id
