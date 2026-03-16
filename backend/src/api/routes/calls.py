"""WebRTC call signaling and event forwarding endpoints.

Proxies SDP offer/answer to OpenAI Realtime WebRTC API.
The browser connects directly to OpenAI for audio — no server-side audio relay.
Each call session instantiates a full runtime actor stack (Coordinator,
TurnManager, AgentFSM, ToolExecutor) connected via RealtimeEventBridge.

Events flow: Browser (WebRTC data channel) → WebSocket → Bridge → Coordinator.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import orjson
import structlog
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from src.config import settings
from src.routing.model_router import ROUTE_TOOL_DEFINITION, RouterPromptBuilder
from src.routing.policies import PoliciesRegistry
from src.voice_runtime.agent_fsm import AgentFSM
from src.voice_runtime.coordinator import Coordinator
from src.voice_runtime.events import (
    CancelAgentGeneration,
    RealtimeVoiceCancel,
    RealtimeVoiceStart,
)
from src.voice_runtime.realtime_event_bridge import OpenAIRealtimeEventBridge
from src.voice_runtime.specialist_tools import register_specialist_tools
from src.voice_runtime.tool_executor import ToolExecutor
from src.voice_runtime.turn_manager import TurnManager

logger = structlog.get_logger()

router = APIRouter(prefix="/calls", tags=["calls"])


# ---------------------------------------------------------------------------
# Shared singletons (set at app startup)
# ---------------------------------------------------------------------------

_shared_router_prompt_builder: RouterPromptBuilder | None = None
_shared_policies: PoliciesRegistry | None = None


def set_shared_dependencies(
    router_prompt_builder: RouterPromptBuilder,
    policies_instance: PoliciesRegistry,
) -> None:
    """Set shared RouterPromptBuilder and PoliciesRegistry singletons (called at app startup)."""
    global _shared_router_prompt_builder, _shared_policies  # noqa: PLW0603
    _shared_router_prompt_builder = router_prompt_builder
    _shared_policies = policies_instance


def _get_policies() -> PoliciesRegistry:
    """Get PoliciesRegistry, falling back to stubs if not initialized."""
    if _shared_policies is not None:
        return _shared_policies

    logger.warning("policies_not_initialized_using_stubs")
    return PoliciesRegistry(
        base_system="You are a helpful voice assistant.",
        policies={
            "greeting": "Greet the user warmly.",
            "handoff_offer": "Offer to transfer to a specialist.",
            "guardrail_disallowed": "Politely decline the request.",
            "guardrail_out_of_scope": "Explain this is outside your scope.",
            "clarify_department": "Ask which department they need.",
        },
    )


# ---------------------------------------------------------------------------
# In-memory session registry
# ---------------------------------------------------------------------------


class CallSessionEntry:
    """Tracks an active call session with its runtime actors."""

    def __init__(
        self,
        call_id: UUID,
        coordinator: Coordinator,
        turn_manager: TurnManager,
        agent_fsm: AgentFSM,
        tool_executor: ToolExecutor,
        bridge: OpenAIRealtimeEventBridge,
    ) -> None:
        self.call_id = call_id
        self.coordinator = coordinator
        self.turn_manager = turn_manager
        self.agent_fsm = agent_fsm
        self.tool_executor = tool_executor
        self.bridge = bridge


_sessions: dict[UUID, CallSessionEntry] = {}


def get_session(call_id: UUID) -> CallSessionEntry:
    entry = _sessions.get(call_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return entry


# ---------------------------------------------------------------------------
# POST /calls — create a new call session with runtime actors
# ---------------------------------------------------------------------------


class CreateCallResponse(BaseModel):
    call_id: str
    status: str


@router.post("", status_code=201, response_model=CreateCallResponse)
async def create_call() -> CreateCallResponse:
    """Create a new voice call session with runtime actors."""
    if len(_sessions) >= settings.max_concurrent_calls:
        raise HTTPException(status_code=503, detail="max_calls_exceeded")

    call_id = uuid4()

    # Instantiate runtime actors
    turn_manager = TurnManager(call_id=call_id)
    agent_fsm = AgentFSM(call_id=call_id)
    tool_executor = ToolExecutor()
    register_specialist_tools(tool_executor)
    policies = _get_policies()

    coordinator = Coordinator(
        call_id=call_id,
        turn_manager=turn_manager,
        agent_fsm=agent_fsm,
        tool_executor=tool_executor,
        router_prompt_builder=_shared_router_prompt_builder,
        policies=policies,
        max_history_turns=settings.max_history_turns,
        max_history_chars=settings.max_history_chars,
    )

    bridge = OpenAIRealtimeEventBridge(call_id=call_id)

    # Wire bridge events to coordinator (input: OpenAI → Coordinator)
    bridge.on_event(coordinator.handle_event)

    # Wire coordinator output to bridge (output: Coordinator → OpenAI)
    async def _on_coordinator_output(
        event: RealtimeVoiceStart | RealtimeVoiceCancel | CancelAgentGeneration,
    ) -> None:
        if isinstance(event, RealtimeVoiceStart):
            await bridge.send_voice_start(event)
        elif isinstance(event, RealtimeVoiceCancel):
            await bridge.send_voice_cancel(event)
        # CancelAgentGeneration is internal — no message to OpenAI

    coordinator.set_output_callback(_on_coordinator_output)

    # Wire debug events: Coordinator → Bridge → Frontend WebSocket
    async def _on_debug_event(event: dict[str, object]) -> None:
        await bridge.send_to_frontend(event)  # type: ignore[arg-type]

    coordinator.set_debug_callback(_on_debug_event)

    entry = CallSessionEntry(
        call_id=call_id,
        coordinator=coordinator,
        turn_manager=turn_manager,
        agent_fsm=agent_fsm,
        tool_executor=tool_executor,
        bridge=bridge,
    )
    _sessions[call_id] = entry

    logger.info("call_created", call_id=str(call_id))
    return CreateCallResponse(call_id=str(call_id), status="created")


# ---------------------------------------------------------------------------
# POST /calls/{call_id}/offer — proxy SDP to OpenAI Realtime WebRTC
# ---------------------------------------------------------------------------


class SDPRequest(BaseModel):
    sdp: str
    type: str


class SDPResponse(BaseModel):
    sdp: str
    type: str


@router.post("/{call_id}/offer", response_model=SDPResponse)
async def handle_offer(call_id: UUID, body: SDPRequest) -> SDPResponse:
    """Two-step SDP exchange with OpenAI Realtime WebRTC API.

    Step 1: POST /v1/realtime/sessions — create session with config
            (transcription, turn_detection) → ephemeral key.
    Step 2: POST /v1/realtime — SDP exchange using ephemeral key.

    The browser establishes a direct WebRTC connection with OpenAI for audio.
    Events are forwarded to the backend via a separate WebSocket (see events_ws).
    """
    get_session(call_id)

    model = settings.openai_realtime_model

    logger.info("proxying_sdp_to_openai", call_id=str(call_id), model=model)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Create session with configuration → ephemeral key
        session_resp = await client.post(
            "https://api.openai.com/v1/realtime/sessions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            content=orjson.dumps({
                "model": model,
                "modalities": ["audio", "text"],
                "input_audio_transcription": {
                    "model": "whisper-1",
                },
                "turn_detection": {
                    "type": "server_vad",
                    "create_response": False,
                },
            }),
        )

        if session_resp.status_code not in (200, 201):
            logger.error(
                "openai_session_create_error",
                status=session_resp.status_code,
                body=session_resp.text[:500],
                call_id=str(call_id),
            )
            raise HTTPException(
                status_code=502,
                detail=f"OpenAI session creation error: {session_resp.status_code}",
            )

        session_data = session_resp.json()
        ephemeral_key = session_data["client_secret"]["value"]
        logger.info(
            "openai_session_created",
            call_id=str(call_id),
            session_id=session_data.get("id"),
        )

        # Step 2: SDP exchange using ephemeral key
        sdp_resp = await client.post(
            f"https://api.openai.com/v1/realtime?model={model}",
            headers={
                "Authorization": f"Bearer {ephemeral_key}",
                "Content-Type": "application/sdp",
            },
            content=body.sdp,
        )

    if sdp_resp.status_code not in (200, 201):
        logger.error(
            "openai_sdp_proxy_error",
            status=sdp_resp.status_code,
            body=sdp_resp.text[:500],
            call_id=str(call_id),
        )
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI Realtime API error: {sdp_resp.status_code}",
        )

    answer_sdp = sdp_resp.text
    logger.info("sdp_exchange_complete", call_id=str(call_id))

    return SDPResponse(sdp=answer_sdp, type="answer")


# ---------------------------------------------------------------------------
# WS /calls/{call_id}/events — event forwarding from browser
# ---------------------------------------------------------------------------


@router.websocket("/{call_id}/events")
async def events_ws(websocket: WebSocket, call_id: UUID) -> None:
    """WebSocket for bidirectional event forwarding.

    Input:  Browser forwards OpenAI data channel events → Bridge → Coordinator
    Output: Coordinator commands → Bridge → Browser → OpenAI data channel
    """
    entry = _sessions.get(call_id)
    if entry is None:
        await websocket.close(code=4004, reason="Call not found")
        return

    await websocket.accept()
    entry.bridge.set_frontend_ws(websocket)
    logger.info("events_ws_connected", call_id=str(call_id))

    # One-time session.update to configure transcription and disable auto-response.
    # The /v1/realtime/sessions endpoint doesn't reliably apply these settings,
    # so we send session.update once at connection start. The frontend buffers
    # this until the data channel opens, so there's no timing issue.
    session_update = {
        "type": "session.update",
        "session": {
            "input_audio_transcription": {
                "model": "whisper-1",
            },
            "turn_detection": {
                "type": "server_vad",
                "create_response": False,
                "silence_duration_ms": settings.vad_silence_duration_ms,
            },
            "tools": [ROUTE_TOOL_DEFINITION],
            "tool_choice": "auto",
        },
    }
    await entry.bridge.send_to_frontend(session_update)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = orjson.loads(raw)
            except (orjson.JSONDecodeError, ValueError):
                logger.warning("events_ws_malformed", call_id=str(call_id))
                continue

            # Intercept debug control messages — don't forward to bridge
            msg_type = data.get("type", "")
            if msg_type == "debug_enable":
                entry.coordinator.set_debug_enabled(True)
                continue
            if msg_type == "debug_disable":
                entry.coordinator.set_debug_enabled(False)
                continue
            if msg_type == "client_debug_event":
                await entry.coordinator.handle_client_debug_event(
                    stage=str(data.get("stage", "")),
                    turn_id=str(data.get("turn_id", "")),
                    ts=int(data.get("ts", 0)),
                )
                continue

            await entry.bridge.handle_frontend_event(data)
    except WebSocketDisconnect:
        logger.info("events_ws_disconnected", call_id=str(call_id))
    except Exception:
        logger.exception("events_ws_error", call_id=str(call_id))
    finally:
        entry.bridge.set_frontend_ws(None)


# ---------------------------------------------------------------------------
# DELETE /calls/{call_id} — end a call, tear down actors
# ---------------------------------------------------------------------------


@router.delete("/{call_id}", status_code=204)
async def delete_call(call_id: UUID) -> None:
    """End a call, tear down runtime actors, close bridge."""
    get_session(call_id)
    session = _sessions.pop(call_id, None)

    if session is not None:
        try:
            await session.bridge.close()
        except Exception:
            logger.warning("bridge_close_error", call_id=str(call_id), exc_info=True)

    logger.info("call_ended", call_id=str(call_id))
