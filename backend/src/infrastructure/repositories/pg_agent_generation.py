from __future__ import annotations

from uuid import UUID

import asyncpg

from src.domain.models.entities import AgentGeneration
from src.voice_runtime.types import AgentGenerationOutcome, AgentState


class PgAgentGenerationRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def insert(self, generation: AgentGeneration) -> None:
        await self._pool.execute(
            """
            INSERT INTO agent_generations
                (agent_generation_id, call_id, turn_id, created_at, started_at,
                 ended_at, state, route_a_label, route_a_confidence, policy_key,
                 specialist, final_outcome, cancel_reason, error)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            """,
            generation.agent_generation_id,
            generation.call_id,
            generation.turn_id,
            generation.created_at,
            generation.started_at,
            generation.ended_at,
            generation.state.value,
            generation.route_a_label,
            generation.route_a_confidence,
            generation.policy_key,
            generation.specialist,
            generation.final_outcome.value if generation.final_outcome else None,
            generation.cancel_reason,
            generation.error,
        )

    async def update(self, generation: AgentGeneration) -> None:
        await self._pool.execute(
            """
            UPDATE agent_generations SET
                started_at = $1, ended_at = $2, state = $3,
                route_a_label = $4, route_a_confidence = $5, policy_key = $6,
                specialist = $7, final_outcome = $8, cancel_reason = $9, error = $10
            WHERE agent_generation_id = $11
            """,
            generation.started_at,
            generation.ended_at,
            generation.state.value,
            generation.route_a_label,
            generation.route_a_confidence,
            generation.policy_key,
            generation.specialist,
            generation.final_outcome.value if generation.final_outcome else None,
            generation.cancel_reason,
            generation.error,
            generation.agent_generation_id,
        )

    async def get_by_id(self, agent_generation_id: UUID) -> AgentGeneration | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM agent_generations WHERE agent_generation_id = $1",
            agent_generation_id,
        )
        if row is None:
            return None
        return _row_to_agent_generation(row)

    async def list_by_turn(self, turn_id: UUID) -> list[AgentGeneration]:
        rows = await self._pool.fetch(
            "SELECT * FROM agent_generations WHERE turn_id = $1 ORDER BY created_at",
            turn_id,
        )
        return [_row_to_agent_generation(r) for r in rows]


def _row_to_agent_generation(row: asyncpg.Record) -> AgentGeneration:
    outcome = row["final_outcome"]
    return AgentGeneration(
        agent_generation_id=row["agent_generation_id"],
        call_id=row["call_id"],
        turn_id=row["turn_id"],
        created_at=row["created_at"],
        state=AgentState(row["state"]),
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        route_a_label=row["route_a_label"],
        route_a_confidence=row["route_a_confidence"],
        policy_key=row["policy_key"],
        specialist=row["specialist"],
        final_outcome=AgentGenerationOutcome(outcome) if outcome else None,
        cancel_reason=row["cancel_reason"],
        error=row["error"],
    )
