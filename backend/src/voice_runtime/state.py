from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class CoordinatorRuntimeState:
    """In-memory runtime state for one active call."""

    call_id: UUID
    active_turn_id: UUID | None = None
    active_agent_generation_id: UUID | None = None
    active_voice_generation_id: UUID | None = None
    active_tool_request_id: UUID | None = None
    cancelled_agent_generations: set[UUID] = field(default_factory=set)
    cancelled_voice_generations: set[UUID] = field(default_factory=set)
    turn_seq: int = 0
    turn_speech_started_ms: int = 0  # timestamp when speech_started for current turn
    turn_audio_committed_ms: int = 0  # timestamp when audio_committed fired

    def is_generation_cancelled(self, agent_generation_id: UUID) -> bool:
        return agent_generation_id in self.cancelled_agent_generations

    def is_voice_cancelled(self, voice_generation_id: UUID) -> bool:
        return voice_generation_id in self.cancelled_voice_generations

    def cancel_active_generation(self) -> UUID | None:
        """Cancel the active generation and return its ID, or None."""
        gen_id = self.active_agent_generation_id
        if gen_id is not None:
            self.cancelled_agent_generations.add(gen_id)
            self.active_agent_generation_id = None
        return gen_id

    def cancel_active_voice(self) -> UUID | None:
        """Cancel the active voice and return its ID, or None."""
        voice_id = self.active_voice_generation_id
        if voice_id is not None:
            self.cancelled_voice_generations.add(voice_id)
            self.active_voice_generation_id = None
        return voice_id
