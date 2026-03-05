from __future__ import annotations

from uuid import UUID

import asyncpg

from src.domain.models.entities import VoiceGeneration
from src.voice_runtime.types import VoiceKind, VoiceState


class PgVoiceGenerationRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def insert(self, voice: VoiceGeneration) -> None:
        await self._pool.execute(
            """
            INSERT INTO voice_generations
                (voice_generation_id, provider_voice_generation_id, call_id,
                 agent_generation_id, turn_id, kind, state,
                 started_at, ended_at, cancel_reason, error)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            voice.voice_generation_id,
            voice.provider_voice_generation_id,
            voice.call_id,
            voice.agent_generation_id,
            voice.turn_id,
            voice.kind.value,
            voice.state.value,
            voice.started_at,
            voice.ended_at,
            voice.cancel_reason,
            voice.error,
        )

    async def update(self, voice: VoiceGeneration) -> None:
        await self._pool.execute(
            """
            UPDATE voice_generations SET
                state = $1, started_at = $2, ended_at = $3,
                cancel_reason = $4, error = $5
            WHERE voice_generation_id = $6
            """,
            voice.state.value,
            voice.started_at,
            voice.ended_at,
            voice.cancel_reason,
            voice.error,
            voice.voice_generation_id,
        )

    async def get_by_id(self, voice_generation_id: UUID) -> VoiceGeneration | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM voice_generations WHERE voice_generation_id = $1",
            voice_generation_id,
        )
        if row is None:
            return None
        return _row_to_voice_generation(row)

    async def list_by_agent_generation(
        self, agent_generation_id: UUID
    ) -> list[VoiceGeneration]:
        rows = await self._pool.fetch(
            "SELECT * FROM voice_generations WHERE agent_generation_id = $1 ORDER BY started_at",
            agent_generation_id,
        )
        return [_row_to_voice_generation(r) for r in rows]


def _row_to_voice_generation(row: asyncpg.Record) -> VoiceGeneration:
    return VoiceGeneration(
        voice_generation_id=row["voice_generation_id"],
        call_id=row["call_id"],
        agent_generation_id=row["agent_generation_id"],
        turn_id=row["turn_id"],
        kind=VoiceKind(row["kind"]),
        state=VoiceState(row["state"]),
        provider_voice_generation_id=row["provider_voice_generation_id"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        cancel_reason=row["cancel_reason"],
        error=row["error"],
    )
