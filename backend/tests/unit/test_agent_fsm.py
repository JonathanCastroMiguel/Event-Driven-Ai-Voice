from uuid import uuid4

import pytest

from src.voice_runtime.agent_fsm import AgentFSM
from src.voice_runtime.types import AgentState


class TestFSMTransitions:
    """Test all valid state transitions in the simplified model-as-router FSM."""

    def test_idle_to_routing(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        gen_id = uuid4()
        change = fsm.start_routing(agent_generation_id=gen_id, ts=1000)
        assert fsm.state == AgentState.ROUTING
        assert change is not None
        assert change.state == "routing"

    def test_routing_to_speaking_direct_voice(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm.start_routing(agent_generation_id=uuid4(), ts=1000)
        change = fsm.voice_started(ts=1050)
        assert fsm.state == AgentState.SPEAKING
        assert change is not None
        assert change.state == "speaking"

    def test_routing_to_waiting_tools_specialist(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm.start_routing(agent_generation_id=uuid4(), ts=1000)
        change = fsm.specialist_action(ts=1050)
        assert fsm.state == AgentState.WAITING_TOOLS
        assert change is not None
        assert change.state == "waiting_tools"

    def test_waiting_tools_to_speaking(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm.start_routing(agent_generation_id=uuid4(), ts=1000)
        fsm.specialist_action(ts=1050)
        change = fsm.tool_result(ts=1100)
        assert fsm.state == AgentState.SPEAKING
        assert change is not None
        assert change.state == "speaking"

    def test_speaking_to_done(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm.start_routing(agent_generation_id=uuid4(), ts=1000)
        fsm.voice_started(ts=1050)
        change = fsm.voice_completed(ts=1100)
        assert fsm.state == AgentState.DONE
        assert change is not None
        assert change.state == "done"

    def test_full_direct_voice_path(self) -> None:
        """idle → routing → speaking → done."""
        fsm = AgentFSM(call_id=uuid4())
        gen_id = uuid4()
        fsm.start_routing(agent_generation_id=gen_id, ts=1000)
        fsm.voice_started(ts=1050)
        fsm.voice_completed(ts=1200)
        assert fsm.state == AgentState.DONE
        assert fsm.current_generation_id == gen_id

    def test_full_specialist_path(self) -> None:
        """idle → routing → waiting_tools → speaking → done."""
        fsm = AgentFSM(call_id=uuid4())
        gen_id = uuid4()
        fsm.start_routing(agent_generation_id=gen_id, ts=1000)
        fsm.specialist_action(ts=1050)
        fsm.tool_result(ts=1200)
        fsm.voice_completed(ts=1400)
        assert fsm.state == AgentState.DONE


class TestFSMCancellation:
    """Test cancel from all active states."""

    def test_cancel_from_routing(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm.start_routing(agent_generation_id=uuid4(), ts=1000)
        change = fsm.cancel(ts=1050)
        assert fsm.state == AgentState.CANCELLED
        assert change is not None

    def test_cancel_from_waiting_tools(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm.start_routing(agent_generation_id=uuid4(), ts=1000)
        fsm.specialist_action(ts=1050)
        change = fsm.cancel(ts=1100)
        assert fsm.state == AgentState.CANCELLED
        assert change is not None

    def test_cancel_from_speaking(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm.start_routing(agent_generation_id=uuid4(), ts=1000)
        fsm.voice_started(ts=1050)
        change = fsm.cancel(ts=1100)
        assert fsm.state == AgentState.CANCELLED
        assert change is not None

    def test_cancel_from_idle_returns_none(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        result = fsm.cancel(ts=1000)
        assert result is None
        assert fsm.state == AgentState.IDLE

    def test_cancel_from_done_returns_none(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm.start_routing(agent_generation_id=uuid4(), ts=1000)
        fsm.voice_started(ts=1050)
        fsm.voice_completed(ts=1100)
        result = fsm.cancel(ts=1200)
        assert result is None
        assert fsm.state == AgentState.DONE

    def test_cancel_from_cancelled_returns_none(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm.start_routing(agent_generation_id=uuid4(), ts=1000)
        fsm.cancel(ts=1050)
        result = fsm.cancel(ts=1100)
        assert result is None


class TestFSMInvalidTransitions:
    """Test that invalid transitions are rejected."""

    def test_voice_started_from_idle_raises(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        with pytest.raises(ValueError, match="Invalid transition"):
            fsm.voice_started(ts=1000)

    def test_tool_result_from_routing_raises(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm.start_routing(agent_generation_id=uuid4(), ts=1000)
        with pytest.raises(ValueError, match="Invalid transition"):
            fsm.tool_result(ts=1050)

    def test_voice_completed_from_routing_raises(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm.start_routing(agent_generation_id=uuid4(), ts=1000)
        with pytest.raises(ValueError, match="Invalid transition"):
            fsm.voice_completed(ts=1050)

    def test_start_routing_from_done_raises(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm.start_routing(agent_generation_id=uuid4(), ts=1000)
        fsm.voice_started(ts=1050)
        fsm.voice_completed(ts=1100)
        with pytest.raises(ValueError, match="Invalid transition"):
            fsm.start_routing(agent_generation_id=uuid4(), ts=2000)

    def test_specialist_action_from_speaking_raises(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm.start_routing(agent_generation_id=uuid4(), ts=1000)
        fsm.voice_started(ts=1050)
        with pytest.raises(ValueError, match="Invalid transition"):
            fsm.specialist_action(ts=1100)


class TestFSMReset:
    def test_reset_to_idle(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm.start_routing(agent_generation_id=uuid4(), ts=1000)
        fsm.voice_started(ts=1050)
        fsm.voice_completed(ts=1100)
        fsm.reset()
        assert fsm.state == AgentState.IDLE
        assert fsm.current_generation_id is None

    def test_reset_then_new_generation(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        gen1 = uuid4()
        fsm.start_routing(agent_generation_id=gen1, ts=1000)
        fsm.voice_started(ts=1050)
        fsm.voice_completed(ts=1100)
        fsm.reset()

        gen2 = uuid4()
        fsm.start_routing(agent_generation_id=gen2, ts=2000)
        assert fsm.state == AgentState.ROUTING
        assert fsm.current_generation_id == gen2
