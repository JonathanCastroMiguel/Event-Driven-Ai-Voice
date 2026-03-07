from uuid import uuid4

from src.domain.models import (
    AgentGeneration,
    CallSessionContext,
    ToolExecution,
    Turn,
    VoiceGeneration,
)
from src.voice_runtime.types import (
    AgentState,
    CallStatus,
    ToolState,
    TurnState,
    VoiceKind,
    VoiceState,
)


class TestCallSessionContext:
    def test_create_with_required_fields(self) -> None:
        session = CallSessionContext(
            call_id=uuid4(),
            started_at=1000,
            status=CallStatus.ACTIVE,
        )
        assert session.status == CallStatus.ACTIVE
        assert session.provider_call_id is None
        assert session.ended_at is None
        assert session.locale_hint is None
        assert session.customer_context is None

    def test_create_with_all_fields(self) -> None:
        call_id = uuid4()
        session = CallSessionContext(
            call_id=call_id,
            started_at=1000,
            status=CallStatus.ENDED,
            provider_call_id="prov_123",
            ended_at=2000,
            locale_hint="es",
            customer_context={"tier": "premium"},
        )
        assert session.call_id == call_id
        assert session.ended_at == 2000
        assert session.locale_hint == "es"

    def test_is_frozen(self) -> None:
        session = CallSessionContext(
            call_id=uuid4(), started_at=1000, status=CallStatus.ACTIVE
        )
        try:
            session.status = CallStatus.ENDED  # type: ignore[misc]
            raise AssertionError("Should not allow mutation")
        except AttributeError:
            pass


class TestTurn:
    def test_create_with_required_fields(self) -> None:
        turn = Turn(
            turn_id=uuid4(),
            call_id=uuid4(),
            seq=1,
            started_at=1000,
            state=TurnState.OPEN,
        )
        assert turn.seq == 1
        assert turn.state == TurnState.OPEN
        assert turn.text_final is None
        assert turn.asr_confidence is None

    def test_finalized_turn(self) -> None:
        turn = Turn(
            turn_id=uuid4(),
            call_id=uuid4(),
            seq=2,
            started_at=1000,
            state=TurnState.FINALIZED,
            finalized_at=1500,
            text_final="necesito ayuda",
            language="es",
            asr_confidence=0.95,
        )
        assert turn.text_final == "necesito ayuda"
        assert turn.language == "es"

    def test_is_frozen(self) -> None:
        turn = Turn(
            turn_id=uuid4(), call_id=uuid4(), seq=1, started_at=1000, state=TurnState.OPEN
        )
        try:
            turn.seq = 2  # type: ignore[misc]
            raise AssertionError("Should not allow mutation")
        except AttributeError:
            pass


class TestAgentGeneration:
    def test_create_with_required_fields(self) -> None:
        gen = AgentGeneration(
            agent_generation_id=uuid4(),
            call_id=uuid4(),
            turn_id=uuid4(),
            created_at=1000,
            state=AgentState.ROUTING,
        )
        assert gen.state == AgentState.ROUTING
        assert gen.route_a_label is None
        assert gen.final_outcome is None

    def test_with_routing_result(self) -> None:
        gen = AgentGeneration(
            agent_generation_id=uuid4(),
            call_id=uuid4(),
            turn_id=uuid4(),
            created_at=1000,
            state=AgentState.DONE,
            started_at=1000,
            ended_at=1050,
            route_a_label="simple",
            route_a_confidence=0.92,
            policy_key="greeting",
        )
        assert gen.route_a_confidence == 0.92

    def test_is_frozen(self) -> None:
        gen = AgentGeneration(
            agent_generation_id=uuid4(),
            call_id=uuid4(),
            turn_id=uuid4(),
            created_at=1000,
            state=AgentState.ROUTING,
        )
        try:
            gen.state = AgentState.DONE  # type: ignore[misc]
            raise AssertionError("Should not allow mutation")
        except AttributeError:
            pass


class TestVoiceGeneration:
    def test_create_with_required_fields(self) -> None:
        vg = VoiceGeneration(
            voice_generation_id=uuid4(),
            call_id=uuid4(),
            agent_generation_id=uuid4(),
            turn_id=uuid4(),
            kind=VoiceKind.RESPONSE,
            state=VoiceState.STARTING,
        )
        assert vg.kind == VoiceKind.RESPONSE
        assert vg.state == VoiceState.STARTING
        assert vg.provider_voice_generation_id is None

    def test_completed_voice(self) -> None:
        vg = VoiceGeneration(
            voice_generation_id=uuid4(),
            call_id=uuid4(),
            agent_generation_id=uuid4(),
            turn_id=uuid4(),
            kind=VoiceKind.FILLER,
            state=VoiceState.COMPLETED,
            started_at=1000,
            ended_at=1200,
        )
        assert vg.ended_at == 1200

    def test_is_frozen(self) -> None:
        vg = VoiceGeneration(
            voice_generation_id=uuid4(),
            call_id=uuid4(),
            agent_generation_id=uuid4(),
            turn_id=uuid4(),
            kind=VoiceKind.RESPONSE,
            state=VoiceState.STARTING,
        )
        try:
            vg.state = VoiceState.COMPLETED  # type: ignore[misc]
            raise AssertionError("Should not allow mutation")
        except AttributeError:
            pass


class TestToolExecution:
    def test_create_with_required_fields(self) -> None:
        te = ToolExecution(
            tool_request_id=uuid4(),
            call_id=uuid4(),
            agent_generation_id=uuid4(),
            turn_id=uuid4(),
            tool_name="lookup_account",
            args_hash="abc123",
            state=ToolState.RUNNING,
        )
        assert te.tool_name == "lookup_account"
        assert te.state == ToolState.RUNNING
        assert te.args_json is None
        assert te.result_json is None

    def test_succeeded_tool(self) -> None:
        te = ToolExecution(
            tool_request_id=uuid4(),
            call_id=uuid4(),
            agent_generation_id=uuid4(),
            turn_id=uuid4(),
            tool_name="lookup_account",
            args_hash="abc123",
            state=ToolState.SUCCEEDED,
            args_json={"account_id": "A-001"},
            started_at=1000,
            ended_at=1100,
            result_json={"balance": 150.0},
        )
        assert te.result_json == {"balance": 150.0}

    def test_is_frozen(self) -> None:
        te = ToolExecution(
            tool_request_id=uuid4(),
            call_id=uuid4(),
            agent_generation_id=uuid4(),
            turn_id=uuid4(),
            tool_name="lookup_account",
            args_hash="abc123",
            state=ToolState.RUNNING,
        )
        try:
            te.state = ToolState.SUCCEEDED  # type: ignore[misc]
            raise AssertionError("Should not allow mutation")
        except AttributeError:
            pass
