from __future__ import annotations

from uuid import UUID

import msgspec

from src.voice_runtime.types import (
    AgentGenerationOutcome,
    AgentState,
    CallStatus,
    ToolState,
    TurnState,
    VoiceKind,
    VoiceState,
)


class CallSessionContext(msgspec.Struct, frozen=True):
    call_id: UUID
    started_at: int
    status: CallStatus
    provider_call_id: str | None = None
    ended_at: int | None = None
    locale_hint: str | None = None
    customer_context: dict[str, object] | None = None


class Turn(msgspec.Struct, frozen=True):
    turn_id: UUID
    call_id: UUID
    seq: int
    started_at: int
    state: TurnState
    finalized_at: int | None = None
    text_final: str | None = None
    language: str | None = None
    cancel_reason: str | None = None
    asr_confidence: float | None = None


class AgentGeneration(msgspec.Struct, frozen=True):
    agent_generation_id: UUID
    call_id: UUID
    turn_id: UUID
    created_at: int
    state: AgentState
    started_at: int | None = None
    ended_at: int | None = None
    route_a_label: str | None = None
    route_a_confidence: float | None = None
    policy_key: str | None = None
    specialist: str | None = None
    final_outcome: AgentGenerationOutcome | None = None
    cancel_reason: str | None = None
    error: str | None = None


class VoiceGeneration(msgspec.Struct, frozen=True):
    voice_generation_id: UUID
    call_id: UUID
    agent_generation_id: UUID
    turn_id: UUID
    kind: VoiceKind
    state: VoiceState
    provider_voice_generation_id: str | None = None
    started_at: int | None = None
    ended_at: int | None = None
    cancel_reason: str | None = None
    error: str | None = None


class ToolExecution(msgspec.Struct, frozen=True):
    tool_request_id: UUID
    call_id: UUID
    agent_generation_id: UUID
    turn_id: UUID
    tool_name: str
    args_hash: str
    state: ToolState
    args_json: dict[str, object] | None = None
    started_at: int | None = None
    ended_at: int | None = None
    result_json: dict[str, object] | None = None
    error: str | None = None
