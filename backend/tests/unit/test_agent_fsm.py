from uuid import uuid4

import pytest

from src.voice_runtime.agent_fsm import AgentFSM
from src.voice_runtime.events import RequestAgentAction, RequestGuidedResponse
from src.voice_runtime.types import AgentState, PolicyKey, RouteALabel, RouteBLabel


# ---------------------------------------------------------------------------
# FSM State Transitions (8.3)
# ---------------------------------------------------------------------------


class TestFSMTransitions:
    def test_idle_to_thinking(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm._current_generation_id = uuid4()
        change = fsm.transition("handle_turn", ts=1000)
        assert fsm.state == AgentState.THINKING
        assert change is not None
        assert change.state == "thinking"

    def test_thinking_to_done(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm._current_generation_id = uuid4()
        fsm.transition("handle_turn", ts=1000)
        change = fsm.transition("classification_done", ts=1050)
        assert fsm.state == AgentState.DONE

    def test_thinking_to_cancelled(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm._current_generation_id = uuid4()
        fsm.transition("handle_turn", ts=1000)
        change = fsm.transition("cancel", ts=1050)
        assert fsm.state == AgentState.CANCELLED

    def test_waiting_tools_to_cancelled(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm._current_generation_id = uuid4()
        fsm.transition("handle_turn", ts=1000)
        fsm.transition("needs_tools", ts=1050)
        change = fsm.transition("cancel", ts=1100)
        assert fsm.state == AgentState.CANCELLED

    def test_invalid_transition_raises(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm._current_generation_id = uuid4()
        fsm.transition("handle_turn", ts=1000)
        fsm.transition("classification_done", ts=1050)
        # DONE -> handle_turn is invalid
        with pytest.raises(ValueError, match="Invalid transition"):
            fsm.transition("handle_turn", ts=2000)

    def test_cancel_from_idle_raises(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        # cancel() should return None since we're in IDLE (not active)
        result = fsm.cancel(ts=1000)
        assert result is None

    def test_cancel_method_from_thinking(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm._current_generation_id = uuid4()
        fsm.transition("handle_turn", ts=1000)
        change = fsm.cancel(ts=1050)
        assert fsm.state == AgentState.CANCELLED
        assert change is not None

    def test_cancel_from_done_returns_none(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm._current_generation_id = uuid4()
        fsm.transition("handle_turn", ts=1000)
        fsm.transition("classification_done", ts=1050)
        result = fsm.cancel(ts=2000)
        assert result is None

    def test_reset(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        fsm._current_generation_id = uuid4()
        fsm.transition("handle_turn", ts=1000)
        fsm.transition("classification_done", ts=1050)
        fsm.reset()
        assert fsm.state == AgentState.IDLE
        assert fsm.current_generation_id is None


# ---------------------------------------------------------------------------
# Agent FSM Routing Integration (8.4)
# ---------------------------------------------------------------------------


class TestAgentFSMRouting:
    def test_simple_emits_greeting(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        gen_id = uuid4()
        output = fsm.handle_turn(
            agent_generation_id=gen_id,
            route_a_label=RouteALabel.SIMPLE,
            route_a_confidence=0.92,
            route_b_label=None,
            user_text="hola",
            ts=1000,
        )
        assert len(output.guided_responses) == 1
        assert output.guided_responses[0].policy_key == PolicyKey.GREETING.value
        assert fsm.state == AgentState.DONE

    def test_disallowed_emits_guardrail(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        output = fsm.handle_turn(
            agent_generation_id=uuid4(),
            route_a_label=RouteALabel.DISALLOWED,
            route_a_confidence=1.0,
            route_b_label=None,
            user_text="idiota",
            ts=1000,
        )
        assert len(output.guided_responses) == 1
        assert output.guided_responses[0].policy_key == PolicyKey.GUARDRAIL_DISALLOWED.value

    def test_out_of_scope_emits_guardrail(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        output = fsm.handle_turn(
            agent_generation_id=uuid4(),
            route_a_label=RouteALabel.OUT_OF_SCOPE,
            route_a_confidence=0.85,
            route_b_label=None,
            user_text="qué tiempo hace",
            ts=1000,
        )
        assert output.guided_responses[0].policy_key == PolicyKey.GUARDRAIL_OUT_OF_SCOPE.value

    def test_domain_billing_emits_agent_action(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        output = fsm.handle_turn(
            agent_generation_id=uuid4(),
            route_a_label=RouteALabel.DOMAIN,
            route_a_confidence=0.85,
            route_b_label=RouteBLabel.BILLING,
            user_text="mi factura está mal",
            ts=1000,
        )
        assert len(output.agent_actions) == 1
        assert output.agent_actions[0].specialist == "billing"
        assert len(output.guided_responses) == 0

    def test_domain_support_emits_agent_action(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        output = fsm.handle_turn(
            agent_generation_id=uuid4(),
            route_a_label=RouteALabel.DOMAIN,
            route_a_confidence=0.82,
            route_b_label=RouteBLabel.SUPPORT,
            user_text="mi internet no funciona",
            ts=1000,
        )
        assert output.agent_actions[0].specialist == "support"

    def test_ambiguous_domain_emits_clarify(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        output = fsm.handle_turn(
            agent_generation_id=uuid4(),
            route_a_label=RouteALabel.DOMAIN,
            route_a_confidence=0.72,
            route_b_label=None,  # ambiguous
            user_text="tengo un problema",
            ts=1000,
        )
        assert len(output.guided_responses) == 1
        assert output.guided_responses[0].policy_key == PolicyKey.CLARIFY_DEPARTMENT.value
        assert len(output.agent_actions) == 0

    def test_handle_turn_produces_state_changes(self) -> None:
        fsm = AgentFSM(call_id=uuid4())
        output = fsm.handle_turn(
            agent_generation_id=uuid4(),
            route_a_label=RouteALabel.SIMPLE,
            route_a_confidence=0.92,
            route_b_label=None,
            user_text="hola",
            ts=1000,
        )
        # Should have THINKING + DONE state changes
        assert len(output.state_changes) == 2
        assert output.state_changes[0].state == "thinking"
        assert output.state_changes[1].state == "done"

    def test_each_specialist_routed(self) -> None:
        for specialist in RouteBLabel:
            fsm = AgentFSM(call_id=uuid4())
            output = fsm.handle_turn(
                agent_generation_id=uuid4(),
                route_a_label=RouteALabel.DOMAIN,
                route_a_confidence=0.85,
                route_b_label=specialist,
                user_text="test",
                ts=1000,
            )
            assert output.agent_actions[0].specialist == specialist.value
