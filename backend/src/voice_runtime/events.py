from __future__ import annotations

from uuid import UUID

import msgspec

from src.voice_runtime.types import EventSource


class EventEnvelope(msgspec.Struct, frozen=True):
    """Canonical wrapper for all events in the voice runtime."""

    event_id: UUID
    call_id: UUID
    ts: int  # ms epoch or monotonic
    type: str
    payload: dict[str, object]
    source: EventSource
    correlation_id: UUID | None = None  # usually agent_generation_id
    causation_id: UUID | None = None  # event_id of the originating event


# ---------------------------------------------------------------------------
# 1. Realtime -> Coordinator (INPUT)
# ---------------------------------------------------------------------------


class SpeechStarted(msgspec.Struct, frozen=True):
    call_id: UUID
    ts: int
    provider_event_id: str | None = None


class SpeechStopped(msgspec.Struct, frozen=True):
    call_id: UUID
    ts: int
    provider_event_id: str | None = None


class TranscriptPartial(msgspec.Struct, frozen=True):
    call_id: UUID
    text: str
    ts: int
    provider_event_id: str | None = None


class TranscriptFinal(msgspec.Struct, frozen=True):
    call_id: UUID
    text: str
    ts: int
    provider_event_id: str | None = None


class VoiceGenerationCompleted(msgspec.Struct, frozen=True):
    call_id: UUID
    voice_generation_id: UUID
    ts: int


class VoiceGenerationError(msgspec.Struct, frozen=True):
    call_id: UUID
    voice_generation_id: UUID
    error: str
    ts: int


# ---------------------------------------------------------------------------
# 2. TurnManager -> Coordinator
# ---------------------------------------------------------------------------


class HumanTurnStarted(msgspec.Struct, frozen=True):
    call_id: UUID
    turn_id: UUID
    ts: int


class HumanTurnFinalized(msgspec.Struct, frozen=True):
    call_id: UUID
    turn_id: UUID
    text: str
    ts: int


class HumanTurnCancelled(msgspec.Struct, frozen=True):
    call_id: UUID
    turn_id: UUID
    reason: str
    ts: int


# ---------------------------------------------------------------------------
# 3. Coordinator -> Agent FSM
# ---------------------------------------------------------------------------


class HandleTurn(msgspec.Struct, frozen=True):
    call_id: UUID
    turn_id: UUID
    text: str
    agent_generation_id: UUID
    ts: int


class CancelAgentGeneration(msgspec.Struct, frozen=True):
    call_id: UUID
    agent_generation_id: UUID
    reason: str
    ts: int


class VoiceDone(msgspec.Struct, frozen=True):
    call_id: UUID
    agent_generation_id: UUID
    voice_generation_id: UUID
    status: str  # "completed" | "cancelled" | "error"
    ts: int


# ---------------------------------------------------------------------------
# 4. Agent FSM -> Coordinator
# ---------------------------------------------------------------------------


class AgentStateChanged(msgspec.Struct, frozen=True):
    call_id: UUID
    agent_generation_id: UUID
    state: str  # AgentState value
    ts: int


class RequestGuidedResponse(msgspec.Struct, frozen=True):
    call_id: UUID
    agent_generation_id: UUID
    policy_key: str  # PolicyKey value
    user_text: str
    ts: int


class RequestAgentAction(msgspec.Struct, frozen=True):
    call_id: UUID
    agent_generation_id: UUID
    specialist: str  # RouteBLabel value
    user_text: str
    ts: int


class RequestToolCall(msgspec.Struct, frozen=True):
    call_id: UUID
    agent_generation_id: UUID
    tool_name: str
    args: dict[str, object]
    ts: int
    tool_request_id: UUID | None = None


# ---------------------------------------------------------------------------
# 5. Coordinator <-> Tool Execution
# ---------------------------------------------------------------------------


class RunTool(msgspec.Struct, frozen=True):
    call_id: UUID
    agent_generation_id: UUID
    tool_request_id: UUID
    tool_name: str
    args: dict[str, object]
    timeout_ms: int
    ts: int


class CancelTool(msgspec.Struct, frozen=True):
    call_id: UUID
    agent_generation_id: UUID
    tool_request_id: UUID
    reason: str
    ts: int


class ToolResult(msgspec.Struct, frozen=True):
    call_id: UUID
    agent_generation_id: UUID
    tool_request_id: UUID
    ok: bool
    payload: dict[str, object] | str
    ts: int


# ---------------------------------------------------------------------------
# 6. Coordinator -> Realtime (Speech Output)
# ---------------------------------------------------------------------------


class RealtimeVoiceStart(msgspec.Struct, frozen=True):
    call_id: UUID
    agent_generation_id: UUID
    voice_generation_id: UUID
    prompt: str | list[dict[str, str]]
    ts: int


class RealtimeVoiceCancel(msgspec.Struct, frozen=True):
    call_id: UUID
    voice_generation_id: UUID
    reason: str
    ts: int


# ---------------------------------------------------------------------------
# Event type name mapping
# ---------------------------------------------------------------------------

EVENT_TYPE_MAP: dict[str, type[msgspec.Struct]] = {
    "speech_started": SpeechStarted,
    "speech_stopped": SpeechStopped,
    "transcript_partial": TranscriptPartial,
    "transcript_final": TranscriptFinal,
    "voice_generation_completed": VoiceGenerationCompleted,
    "voice_generation_error": VoiceGenerationError,
    "human_turn_started": HumanTurnStarted,
    "human_turn_finalized": HumanTurnFinalized,
    "human_turn_cancelled": HumanTurnCancelled,
    "handle_turn": HandleTurn,
    "cancel_agent_generation": CancelAgentGeneration,
    "voice_done": VoiceDone,
    "agent_state_changed": AgentStateChanged,
    "request_guided_response": RequestGuidedResponse,
    "request_agent_action": RequestAgentAction,
    "request_tool_call": RequestToolCall,
    "run_tool": RunTool,
    "cancel_tool": CancelTool,
    "tool_result": ToolResult,
    "realtime_voice_start": RealtimeVoiceStart,
    "realtime_voice_cancel": RealtimeVoiceCancel,
}
