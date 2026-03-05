from __future__ import annotations

from uuid import UUID

import asyncpg
import orjson

from src.domain.models.entities import ToolExecution
from src.voice_runtime.types import ToolState


class PgToolExecutionRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def insert(self, tool: ToolExecution) -> None:
        await self._pool.execute(
            """
            INSERT INTO tool_executions
                (tool_request_id, call_id, agent_generation_id, turn_id,
                 tool_name, args_hash, args_json, state,
                 started_at, ended_at, result_json, error)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11::jsonb, $12)
            """,
            tool.tool_request_id,
            tool.call_id,
            tool.agent_generation_id,
            tool.turn_id,
            tool.tool_name,
            tool.args_hash,
            _json_or_none(tool.args_json),
            tool.state.value,
            tool.started_at,
            tool.ended_at,
            _json_or_none(tool.result_json),
            tool.error,
        )

    async def update(self, tool: ToolExecution) -> None:
        await self._pool.execute(
            """
            UPDATE tool_executions SET
                state = $1, started_at = $2, ended_at = $3,
                result_json = $4::jsonb, error = $5
            WHERE tool_request_id = $6
            """,
            tool.state.value,
            tool.started_at,
            tool.ended_at,
            _json_or_none(tool.result_json),
            tool.error,
            tool.tool_request_id,
        )

    async def get_by_id(self, tool_request_id: UUID) -> ToolExecution | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM tool_executions WHERE tool_request_id = $1",
            tool_request_id,
        )
        if row is None:
            return None
        return _row_to_tool_execution(row)

    async def list_by_agent_generation(
        self, agent_generation_id: UUID
    ) -> list[ToolExecution]:
        rows = await self._pool.fetch(
            "SELECT * FROM tool_executions WHERE agent_generation_id = $1 ORDER BY started_at",
            agent_generation_id,
        )
        return [_row_to_tool_execution(r) for r in rows]


def _json_or_none(value: dict[str, object] | None) -> str | None:
    if value is None:
        return None
    return orjson.dumps(value).decode()


def _row_to_tool_execution(row: asyncpg.Record) -> ToolExecution:
    args = row["args_json"]
    result = row["result_json"]
    return ToolExecution(
        tool_request_id=row["tool_request_id"],
        call_id=row["call_id"],
        agent_generation_id=row["agent_generation_id"],
        turn_id=row["turn_id"],
        tool_name=row["tool_name"],
        args_hash=row["args_hash"],
        state=ToolState(row["state"]),
        args_json=orjson.loads(args) if args is not None else None,
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        result_json=orjson.loads(result) if result is not None else None,
        error=row["error"],
    )
