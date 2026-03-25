from __future__ import annotations

from uuid import UUID

import asyncpg

from src.domain.models.entities import CallSessionContext
from src.voice_runtime.types import CallStatus


class PgCallRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def insert(self, session: CallSessionContext) -> None:
        await self._pool.execute(
            """
            INSERT INTO call_sessions
                (call_id, provider_call_id, started_at, ended_at, status, locale_hint, customer_context, client_type)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
            """,
            session.call_id,
            session.provider_call_id,
            session.started_at,
            session.ended_at,
            session.status.value,
            session.locale_hint,
            _json_or_none(session.customer_context),
            session.client_type,
        )

    async def update_status(
        self, call_id: UUID, status: str, ended_at: int | None = None
    ) -> None:
        await self._pool.execute(
            "UPDATE call_sessions SET status = $1, ended_at = $2 WHERE call_id = $3",
            status,
            ended_at,
            call_id,
        )

    async def get_by_id(self, call_id: UUID) -> CallSessionContext | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM call_sessions WHERE call_id = $1", call_id
        )
        if row is None:
            return None
        return _row_to_call_session(row)


def _json_or_none(value: dict[str, object] | None) -> str | None:
    if value is None:
        return None
    import orjson

    return orjson.dumps(value).decode()


def _row_to_call_session(row: asyncpg.Record) -> CallSessionContext:
    import orjson

    ctx = row["customer_context"]
    return CallSessionContext(
        call_id=row["call_id"],
        started_at=row["started_at"],
        status=CallStatus(row["status"]),
        client_type=row.get("client_type", "browser_webrtc"),  # Default for backward compatibility
        provider_call_id=row["provider_call_id"],
        ended_at=row["ended_at"],
        locale_hint=row["locale_hint"],
        customer_context=orjson.loads(ctx) if ctx is not None else None,
    )
