"""Unit tests for WebRTC signaling endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import httpx
import orjson
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.routes.calls import (
    CallSessionEntry,
    _get_policies,
    _sessions,
    set_shared_dependencies,
)
from src.routing.policies import PoliciesRegistry
from src.voice_runtime.agent_fsm import AgentFSM
from src.voice_runtime.coordinator import Coordinator
from src.voice_runtime.realtime_event_bridge import OpenAIRealtimeEventBridge
from src.voice_runtime.tool_executor import ToolExecutor
from src.voice_runtime.turn_manager import TurnManager
from src.voice_runtime.types import PolicyKey


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

    def test_session_has_runtime_actors(self, client: TestClient) -> None:
        resp = client.post("/api/v1/calls")
        call_id = UUID(resp.json()["call_id"])
        entry = _sessions[call_id]
        assert isinstance(entry.coordinator, Coordinator)
        assert isinstance(entry.turn_manager, TurnManager)
        assert isinstance(entry.agent_fsm, AgentFSM)
        assert isinstance(entry.tool_executor, ToolExecutor)
        assert isinstance(entry.bridge, OpenAIRealtimeEventBridge)

    @patch("src.api.routes.calls.settings")
    def test_max_concurrent_calls(self, mock_settings, client: TestClient) -> None:
        mock_settings.max_concurrent_calls = 2

        client.post("/api/v1/calls")
        client.post("/api/v1/calls")
        resp = client.post("/api/v1/calls")
        assert resp.status_code == 503
        assert resp.json()["detail"] == "max_calls_exceeded"


# ---------------------------------------------------------------------------
# POST /api/v1/calls/{call_id}/offer — two-step SDP proxy
# ---------------------------------------------------------------------------


def _mock_two_step_sdp(
    session_status: int = 200,
    sdp_status: int = 200,
) -> MagicMock:
    """Create an httpx.AsyncClient mock for the two-step SDP flow."""
    session_response = httpx.Response(
        status_code=session_status,
        json={
            "id": "sess_test123",
            "client_secret": {"value": "ek_test_ephemeral_key"},
        },
    )
    sdp_response = httpx.Response(
        status_code=sdp_status,
        text="v=0\r\no=- 0 0 IN IP4 0.0.0.0\r\n",
    )

    mock_client = AsyncMock()

    async def _post(url: str, **kwargs: object) -> httpx.Response:
        if "/v1/realtime/sessions" in url:
            return session_response
        if "/v1/realtime" in url:
            return sdp_response
        msg = f"Unexpected URL: {url}"
        raise ValueError(msg)

    mock_client.post = _post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


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

    @patch("src.api.routes.calls.httpx.AsyncClient")
    def test_successful_two_step_sdp_exchange(
        self, mock_async_client_cls: MagicMock, client: TestClient
    ) -> None:
        mock_async_client_cls.return_value = _mock_two_step_sdp()

        create_resp = client.post("/api/v1/calls")
        call_id = create_resp.json()["call_id"]

        resp = client.post(
            f"/api/v1/calls/{call_id}/offer",
            json={"sdp": "v=0\r\n", "type": "offer"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "answer"
        assert "v=0" in data["sdp"]

    @patch("src.api.routes.calls.httpx.AsyncClient")
    def test_session_creation_failure_returns_502(
        self, mock_async_client_cls: MagicMock, client: TestClient
    ) -> None:
        mock_async_client_cls.return_value = _mock_two_step_sdp(session_status=500)

        create_resp = client.post("/api/v1/calls")
        call_id = create_resp.json()["call_id"]

        resp = client.post(
            f"/api/v1/calls/{call_id}/offer",
            json={"sdp": "v=0\r\n", "type": "offer"},
        )
        assert resp.status_code == 502
        assert "session creation error" in resp.json()["detail"]

    @patch("src.api.routes.calls.httpx.AsyncClient")
    def test_sdp_exchange_failure_returns_502(
        self, mock_async_client_cls: MagicMock, client: TestClient
    ) -> None:
        mock_async_client_cls.return_value = _mock_two_step_sdp(sdp_status=500)

        create_resp = client.post("/api/v1/calls")
        call_id = create_resp.json()["call_id"]

        resp = client.post(
            f"/api/v1/calls/{call_id}/offer",
            json={"sdp": "v=0\r\n", "type": "offer"},
        )
        assert resp.status_code == 502
        assert "Realtime API error" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# WS /api/v1/calls/{call_id}/events — event forwarding
# ---------------------------------------------------------------------------


class TestEventsWebSocket:
    def test_ws_unknown_call_rejected(self, client: TestClient) -> None:
        fake_id = str(uuid4())
        with pytest.raises(Exception):
            with client.websocket_connect(f"/api/v1/calls/{fake_id}/events"):
                pass

    def test_ws_connect_sends_session_update(self, client: TestClient) -> None:
        create_resp = client.post("/api/v1/calls")
        call_id = create_resp.json()["call_id"]

        entry = _sessions[UUID(call_id)]
        sent_messages: list[str] = []
        original_send_to_frontend = entry.bridge.send_to_frontend

        async def capture_send(data: dict) -> None:
            sent_messages.append(orjson.dumps(data).decode())

        entry.bridge.send_to_frontend = capture_send  # type: ignore[assignment]

        with client.websocket_connect(f"/api/v1/calls/{call_id}/events"):
            pass

        assert len(sent_messages) >= 1
        session_update = orjson.loads(sent_messages[0])
        assert session_update["type"] == "session.update"
        assert session_update["session"]["turn_detection"]["create_response"] is False
        assert session_update["session"]["input_audio_transcription"]["model"] == "whisper-1"

    def test_ws_forwards_event_to_bridge(self, client: TestClient) -> None:
        create_resp = client.post("/api/v1/calls")
        call_id = create_resp.json()["call_id"]

        entry = _sessions[UUID(call_id)]
        received_events: list[dict] = []
        original_handle = entry.bridge.handle_frontend_event

        async def capture_event(data: dict) -> None:
            received_events.append(data)

        entry.bridge.handle_frontend_event = capture_event  # type: ignore[assignment]
        # Bypass session.update by mocking send_to_frontend
        entry.bridge.send_to_frontend = AsyncMock()  # type: ignore[assignment]

        with client.websocket_connect(f"/api/v1/calls/{call_id}/events") as ws:
            ws.send_text(orjson.dumps({"type": "input_audio_buffer.speech_started"}).decode())

        assert len(received_events) == 1
        assert received_events[0]["type"] == "input_audio_buffer.speech_started"

    def test_ws_disconnect_clears_frontend_ws(self, client: TestClient) -> None:
        create_resp = client.post("/api/v1/calls")
        call_id = create_resp.json()["call_id"]

        entry = _sessions[UUID(call_id)]
        # Bypass session.update
        entry.bridge.send_to_frontend = AsyncMock()  # type: ignore[assignment]

        with client.websocket_connect(f"/api/v1/calls/{call_id}/events"):
            assert entry.bridge._frontend_ws is not None

        assert entry.bridge._frontend_ws is None


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
# Policies fallback
# ---------------------------------------------------------------------------


class TestPoliciesFallback:
    @patch("src.api.routes.calls._shared_policies", None)
    def test_fallback_stubs_returned_when_not_initialized(self) -> None:
        policies = _get_policies()
        assert isinstance(policies, PoliciesRegistry)
        assert policies.base_system == "You are a helpful voice assistant."

    @patch("src.api.routes.calls._shared_policies", None)
    def test_fallback_stubs_cover_all_policy_keys(self) -> None:
        policies = _get_policies()
        for key in PolicyKey:
            instructions = policies.get_instructions(key)
            assert len(instructions) > 0

    def test_shared_policies_used_when_set(self) -> None:
        custom = PoliciesRegistry(
            base_system="Custom system.",
            policies={k.value: f"Custom {k.value}" for k in PolicyKey},
        )
        set_shared_dependencies(MagicMock(), custom)
        try:
            policies = _get_policies()
            assert policies.base_system == "Custom system."
        finally:
            # Restore to None to not affect other tests
            import src.api.routes.calls as calls_module
            calls_module._shared_policies = None
            calls_module._shared_router_prompt_builder = None


# ---------------------------------------------------------------------------
# Actor wiring
# ---------------------------------------------------------------------------


class TestActorWiring:
    def test_bridge_wired_to_coordinator(self, client: TestClient) -> None:
        resp = client.post("/api/v1/calls")
        call_id = UUID(resp.json()["call_id"])
        entry = _sessions[call_id]
        assert entry.bridge._callback is not None

    def test_coordinator_has_output_callback(self, client: TestClient) -> None:
        resp = client.post("/api/v1/calls")
        call_id = UUID(resp.json()["call_id"])
        entry = _sessions[call_id]
        assert entry.coordinator._output_callback is not None


# ---------------------------------------------------------------------------
# CallSessionEntry
# ---------------------------------------------------------------------------


class TestCallSessionEntry:
    def test_initial_state(self) -> None:
        call_id = uuid4()
        tm = TurnManager(call_id=call_id)
        fsm = AgentFSM(call_id=call_id)
        te = ToolExecutor()
        policies = PoliciesRegistry(base_system="test", policies={"greeting": "hi"})
        coord = Coordinator(
            call_id=call_id,
            turn_manager=tm,
            agent_fsm=fsm,
            tool_executor=te,
            router_prompt_builder=None,
            policies=policies,
        )
        bridge = OpenAIRealtimeEventBridge(call_id=call_id)
        entry = CallSessionEntry(
            call_id=call_id,
            coordinator=coord,
            turn_manager=tm,
            agent_fsm=fsm,
            tool_executor=te,
            bridge=bridge,
        )
        assert entry.call_id == call_id
        assert entry.coordinator is coord
        assert entry.bridge is bridge
