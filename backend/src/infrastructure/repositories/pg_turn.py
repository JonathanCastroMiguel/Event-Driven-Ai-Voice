from __future__ import annotations

from uuid import UUID

import asyncpg

from src.domain.models.entities import Turn
from src.voice_runtime.types import TurnState


class PgTurnRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def insert(self, turn: Turn) -> None:
        await self._pool.execute(
            """
            INSERT INTO turns
                (turn_id, call_id, seq, started_at, finalized_at, text_final,
                 language, state, cancel_reason, asr_confidence)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            turn.turn_id,
            turn.call_id,
            turn.seq,
            turn.started_at,
            turn.finalized_at,
            turn.text_final,
            turn.language,
            turn.state.value,
            turn.cancel_reason,
            turn.asr_confidence,
        )

    async def update(self, turn: Turn) -> None:
        await self._pool.execute(
            """
            UPDATE turns SET
                finalized_at = $1, text_final = $2, language = $3,
                state = $4, cancel_reason = $5, asr_confidence = $6
            WHERE turn_id = $7
            """,
            turn.finalized_at,
            turn.text_final,
            turn.language,
            turn.state.value,
            turn.cancel_reason,
            turn.asr_confidence,
            turn.turn_id,
        )

    async def get_by_id(self, turn_id: UUID) -> Turn | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM turns WHERE turn_id = $1", turn_id
        )
        if row is None:
            return None
        return _row_to_turn(row)

    async def list_by_call(self, call_id: UUID) -> list[Turn]:
        rows = await self._pool.fetch(
            "SELECT * FROM turns WHERE call_id = $1 ORDER BY seq", call_id
        )
        return [_row_to_turn(r) for r in rows]


def _row_to_turn(row: asyncpg.Record) -> Turn:
    return Turn(
        turn_id=row["turn_id"],
        call_id=row["call_id"],
        seq=row["seq"],
        started_at=row["started_at"],
        state=TurnState(row["state"]),
        finalized_at=row["finalized_at"],
        text_final=row["text_final"],
        language=row["language"],
        cancel_reason=row["cancel_reason"],
        asr_confidence=row["asr_confidence"],
    )
