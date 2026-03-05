from __future__ import annotations

from uuid import uuid4

import asyncpg
import pytest

from src.domain.models.entities import (
    AgentGeneration,
    CallSessionContext,
    ToolExecution,
    Turn,
    VoiceGeneration,
)
from src.infrastructure.repositories import (
    PgAgentGenerationRepository,
    PgCallRepository,
    PgToolExecutionRepository,
    PgTurnRepository,
    PgVoiceGenerationRepository,
)
from src.voice_runtime.types import (
    AgentGenerationOutcome,
    AgentState,
    CallStatus,
    ToolState,
    TurnState,
    VoiceKind,
    VoiceState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_call(call_id=None):
    return CallSessionContext(
        call_id=call_id or uuid4(),
        started_at=1000,
        status=CallStatus.ACTIVE,
        provider_call_id="prov_1",
        locale_hint="es",
        customer_context={"tier": "premium"},
    )


def _make_turn(call_id, seq=1, turn_id=None):
    return Turn(
        turn_id=turn_id or uuid4(),
        call_id=call_id,
        seq=seq,
        started_at=1000,
        state=TurnState.OPEN,
    )


def _make_generation(call_id, turn_id, gen_id=None):
    return AgentGeneration(
        agent_generation_id=gen_id or uuid4(),
        call_id=call_id,
        turn_id=turn_id,
        created_at=1000,
        state=AgentState.THINKING,
    )


# ---------------------------------------------------------------------------
# CallRepository
# ---------------------------------------------------------------------------


class TestPgCallRepository:
    async def test_insert_and_get(self, pg_pool: asyncpg.Pool) -> None:
        repo = PgCallRepository(pg_pool)
        session = _make_call()
        await repo.insert(session)

        result = await repo.get_by_id(session.call_id)
        assert result is not None
        assert result.call_id == session.call_id
        assert result.status == CallStatus.ACTIVE
        assert result.customer_context == {"tier": "premium"}

    async def test_update_status(self, pg_pool: asyncpg.Pool) -> None:
        repo = PgCallRepository(pg_pool)
        session = _make_call()
        await repo.insert(session)

        await repo.update_status(session.call_id, "ended", ended_at=2000)

        result = await repo.get_by_id(session.call_id)
        assert result is not None
        assert result.status == CallStatus.ENDED
        assert result.ended_at == 2000

    async def test_get_nonexistent_returns_none(self, pg_pool: asyncpg.Pool) -> None:
        repo = PgCallRepository(pg_pool)
        assert await repo.get_by_id(uuid4()) is None


# ---------------------------------------------------------------------------
# TurnRepository
# ---------------------------------------------------------------------------


class TestPgTurnRepository:
    async def test_insert_and_get(self, pg_pool: asyncpg.Pool) -> None:
        call_repo = PgCallRepository(pg_pool)
        session = _make_call()
        await call_repo.insert(session)

        repo = PgTurnRepository(pg_pool)
        turn = _make_turn(session.call_id)
        await repo.insert(turn)

        result = await repo.get_by_id(turn.turn_id)
        assert result is not None
        assert result.state == TurnState.OPEN

    async def test_update(self, pg_pool: asyncpg.Pool) -> None:
        call_repo = PgCallRepository(pg_pool)
        session = _make_call()
        await call_repo.insert(session)

        repo = PgTurnRepository(pg_pool)
        turn = _make_turn(session.call_id)
        await repo.insert(turn)

        updated = Turn(
            turn_id=turn.turn_id,
            call_id=turn.call_id,
            seq=turn.seq,
            started_at=turn.started_at,
            state=TurnState.FINALIZED,
            finalized_at=1500,
            text_final="hola",
            language="es",
            asr_confidence=0.95,
        )
        await repo.update(updated)

        result = await repo.get_by_id(turn.turn_id)
        assert result is not None
        assert result.state == TurnState.FINALIZED
        assert result.text_final == "hola"

    async def test_list_by_call_ordered(self, pg_pool: asyncpg.Pool) -> None:
        call_repo = PgCallRepository(pg_pool)
        session = _make_call()
        await call_repo.insert(session)

        repo = PgTurnRepository(pg_pool)
        t1 = _make_turn(session.call_id, seq=1)
        t2 = _make_turn(session.call_id, seq=2)
        await repo.insert(t1)
        await repo.insert(t2)

        turns = await repo.list_by_call(session.call_id)
        assert len(turns) == 2
        assert turns[0].seq == 1
        assert turns[1].seq == 2


# ---------------------------------------------------------------------------
# AgentGenerationRepository
# ---------------------------------------------------------------------------


class TestPgAgentGenerationRepository:
    async def test_insert_and_get(self, pg_pool: asyncpg.Pool) -> None:
        call_repo = PgCallRepository(pg_pool)
        session = _make_call()
        await call_repo.insert(session)
        turn_repo = PgTurnRepository(pg_pool)
        turn = _make_turn(session.call_id)
        await turn_repo.insert(turn)

        repo = PgAgentGenerationRepository(pg_pool)
        gen = _make_generation(session.call_id, turn.turn_id)
        await repo.insert(gen)

        result = await repo.get_by_id(gen.agent_generation_id)
        assert result is not None
        assert result.state == AgentState.THINKING

    async def test_update_with_outcome(self, pg_pool: asyncpg.Pool) -> None:
        call_repo = PgCallRepository(pg_pool)
        session = _make_call()
        await call_repo.insert(session)
        turn_repo = PgTurnRepository(pg_pool)
        turn = _make_turn(session.call_id)
        await turn_repo.insert(turn)

        repo = PgAgentGenerationRepository(pg_pool)
        gen = _make_generation(session.call_id, turn.turn_id)
        await repo.insert(gen)

        updated = AgentGeneration(
            agent_generation_id=gen.agent_generation_id,
            call_id=gen.call_id,
            turn_id=gen.turn_id,
            created_at=gen.created_at,
            state=AgentState.DONE,
            started_at=1000,
            ended_at=1050,
            route_a_label="simple",
            route_a_confidence=0.92,
            policy_key="greeting",
            final_outcome=AgentGenerationOutcome.GUIDED_RESPONSE,
        )
        await repo.update(updated)

        result = await repo.get_by_id(gen.agent_generation_id)
        assert result is not None
        assert result.state == AgentState.DONE
        assert result.final_outcome == AgentGenerationOutcome.GUIDED_RESPONSE

    async def test_list_by_turn(self, pg_pool: asyncpg.Pool) -> None:
        call_repo = PgCallRepository(pg_pool)
        session = _make_call()
        await call_repo.insert(session)
        turn_repo = PgTurnRepository(pg_pool)
        turn = _make_turn(session.call_id)
        await turn_repo.insert(turn)

        repo = PgAgentGenerationRepository(pg_pool)
        g1 = _make_generation(session.call_id, turn.turn_id)
        g2 = _make_generation(session.call_id, turn.turn_id)
        await repo.insert(g1)
        await repo.insert(g2)

        gens = await repo.list_by_turn(turn.turn_id)
        assert len(gens) == 2


# ---------------------------------------------------------------------------
# VoiceGenerationRepository
# ---------------------------------------------------------------------------


class TestPgVoiceGenerationRepository:
    async def _setup(self, pg_pool: asyncpg.Pool):
        session = _make_call()
        await PgCallRepository(pg_pool).insert(session)
        turn = _make_turn(session.call_id)
        await PgTurnRepository(pg_pool).insert(turn)
        gen = _make_generation(session.call_id, turn.turn_id)
        await PgAgentGenerationRepository(pg_pool).insert(gen)
        return session, turn, gen

    async def test_insert_and_get(self, pg_pool: asyncpg.Pool) -> None:
        session, turn, gen = await self._setup(pg_pool)
        repo = PgVoiceGenerationRepository(pg_pool)

        vg = VoiceGeneration(
            voice_generation_id=uuid4(),
            call_id=session.call_id,
            agent_generation_id=gen.agent_generation_id,
            turn_id=turn.turn_id,
            kind=VoiceKind.RESPONSE,
            state=VoiceState.STARTING,
        )
        await repo.insert(vg)

        result = await repo.get_by_id(vg.voice_generation_id)
        assert result is not None
        assert result.kind == VoiceKind.RESPONSE

    async def test_update(self, pg_pool: asyncpg.Pool) -> None:
        session, turn, gen = await self._setup(pg_pool)
        repo = PgVoiceGenerationRepository(pg_pool)

        vg = VoiceGeneration(
            voice_generation_id=uuid4(),
            call_id=session.call_id,
            agent_generation_id=gen.agent_generation_id,
            turn_id=turn.turn_id,
            kind=VoiceKind.FILLER,
            state=VoiceState.STARTING,
        )
        await repo.insert(vg)

        updated = VoiceGeneration(
            voice_generation_id=vg.voice_generation_id,
            call_id=vg.call_id,
            agent_generation_id=vg.agent_generation_id,
            turn_id=vg.turn_id,
            kind=vg.kind,
            state=VoiceState.COMPLETED,
            started_at=1000,
            ended_at=1200,
        )
        await repo.update(updated)

        result = await repo.get_by_id(vg.voice_generation_id)
        assert result is not None
        assert result.state == VoiceState.COMPLETED
        assert result.ended_at == 1200

    async def test_list_by_agent_generation(self, pg_pool: asyncpg.Pool) -> None:
        session, turn, gen = await self._setup(pg_pool)
        repo = PgVoiceGenerationRepository(pg_pool)

        for _ in range(2):
            vg = VoiceGeneration(
                voice_generation_id=uuid4(),
                call_id=session.call_id,
                agent_generation_id=gen.agent_generation_id,
                turn_id=turn.turn_id,
                kind=VoiceKind.RESPONSE,
                state=VoiceState.STARTING,
                started_at=1000,
            )
            await repo.insert(vg)

        voices = await repo.list_by_agent_generation(gen.agent_generation_id)
        assert len(voices) == 2


# ---------------------------------------------------------------------------
# ToolExecutionRepository
# ---------------------------------------------------------------------------


class TestPgToolExecutionRepository:
    async def _setup(self, pg_pool: asyncpg.Pool):
        session = _make_call()
        await PgCallRepository(pg_pool).insert(session)
        turn = _make_turn(session.call_id)
        await PgTurnRepository(pg_pool).insert(turn)
        gen = _make_generation(session.call_id, turn.turn_id)
        await PgAgentGenerationRepository(pg_pool).insert(gen)
        return session, turn, gen

    async def test_insert_and_get(self, pg_pool: asyncpg.Pool) -> None:
        session, turn, gen = await self._setup(pg_pool)
        repo = PgToolExecutionRepository(pg_pool)

        te = ToolExecution(
            tool_request_id=uuid4(),
            call_id=session.call_id,
            agent_generation_id=gen.agent_generation_id,
            turn_id=turn.turn_id,
            tool_name="lookup_account",
            args_hash="abc123",
            state=ToolState.RUNNING,
            args_json={"account_id": "A-001"},
            started_at=1000,
        )
        await repo.insert(te)

        result = await repo.get_by_id(te.tool_request_id)
        assert result is not None
        assert result.tool_name == "lookup_account"
        assert result.args_json == {"account_id": "A-001"}

    async def test_update(self, pg_pool: asyncpg.Pool) -> None:
        session, turn, gen = await self._setup(pg_pool)
        repo = PgToolExecutionRepository(pg_pool)

        te = ToolExecution(
            tool_request_id=uuid4(),
            call_id=session.call_id,
            agent_generation_id=gen.agent_generation_id,
            turn_id=turn.turn_id,
            tool_name="lookup_account",
            args_hash="abc123",
            state=ToolState.RUNNING,
            started_at=1000,
        )
        await repo.insert(te)

        updated = ToolExecution(
            tool_request_id=te.tool_request_id,
            call_id=te.call_id,
            agent_generation_id=te.agent_generation_id,
            turn_id=te.turn_id,
            tool_name=te.tool_name,
            args_hash=te.args_hash,
            state=ToolState.SUCCEEDED,
            started_at=1000,
            ended_at=1100,
            result_json={"balance": 150.0},
        )
        await repo.update(updated)

        result = await repo.get_by_id(te.tool_request_id)
        assert result is not None
        assert result.state == ToolState.SUCCEEDED
        assert result.result_json == {"balance": 150.0}

    async def test_list_by_agent_generation(self, pg_pool: asyncpg.Pool) -> None:
        session, turn, gen = await self._setup(pg_pool)
        repo = PgToolExecutionRepository(pg_pool)

        for i in range(2):
            te = ToolExecution(
                tool_request_id=uuid4(),
                call_id=session.call_id,
                agent_generation_id=gen.agent_generation_id,
                turn_id=turn.turn_id,
                tool_name=f"tool_{i}",
                args_hash=f"hash_{i}",
                state=ToolState.RUNNING,
                started_at=1000 + i,
            )
            await repo.insert(te)

        tools = await repo.list_by_agent_generation(gen.agent_generation_id)
        assert len(tools) == 2
