from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import structlog

from src.voice_runtime.events import (
    AgentStateChanged,
    RequestAgentAction,
    RequestGuidedResponse,
)
from src.voice_runtime.types import AgentState, PolicyKey, RouteALabel, RouteBLabel

logger = structlog.get_logger()

# Valid state transitions: from_state -> {event -> to_state}
TRANSITIONS: dict[AgentState, dict[str, AgentState]] = {
    AgentState.IDLE: {
        "handle_turn": AgentState.THINKING,
    },
    AgentState.THINKING: {
        "classification_done": AgentState.DONE,
        "needs_tools": AgentState.WAITING_TOOLS,
        "cancel": AgentState.CANCELLED,
        "error": AgentState.ERROR,
    },
    AgentState.WAITING_TOOLS: {
        "tools_done": AgentState.WAITING_VOICE,
        "cancel": AgentState.CANCELLED,
        "error": AgentState.ERROR,
    },
    AgentState.WAITING_VOICE: {
        "voice_done": AgentState.DONE,
        "cancel": AgentState.CANCELLED,
        "error": AgentState.ERROR,
    },
    AgentState.DONE: {},
    AgentState.CANCELLED: {},
    AgentState.ERROR: {},
}

# Route A label -> PolicyKey mapping for guided responses
ROUTE_A_POLICY_MAP: dict[RouteALabel, PolicyKey] = {
    RouteALabel.SIMPLE: PolicyKey.GREETING,
    RouteALabel.DISALLOWED: PolicyKey.GUARDRAIL_DISALLOWED,
    RouteALabel.OUT_OF_SCOPE: PolicyKey.GUARDRAIL_OUT_OF_SCOPE,
}


@dataclass
class AgentFSMOutput:
    state_changes: list[AgentStateChanged] = field(default_factory=list)
    guided_responses: list[RequestGuidedResponse] = field(default_factory=list)
    agent_actions: list[RequestAgentAction] = field(default_factory=list)


class AgentFSM:
    """Finite state machine for agent generation lifecycle.

    Classifies user intent via the routing engine and emits
    routing events to the Coordinator. Does NOT execute tools
    or call the Realtime API directly.
    """

    def __init__(self, call_id: UUID) -> None:
        self._call_id = call_id
        self._state = AgentState.IDLE
        self._current_generation_id: UUID | None = None

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def current_generation_id(self) -> UUID | None:
        return self._current_generation_id

    def transition(self, event: str, ts: int) -> AgentStateChanged | None:
        """Attempt a state transition. Returns state change event or raises on invalid."""
        allowed = TRANSITIONS.get(self._state, {})
        new_state = allowed.get(event)
        if new_state is None:
            msg = f"Invalid transition: {self._state.value} + {event}"
            raise ValueError(msg)

        old_state = self._state
        self._state = new_state
        logger.info(
            "agent_state_transition",
            from_state=old_state.value,
            to_state=new_state.value,
            trigger=event,
        )

        if self._current_generation_id is None:
            return None

        return AgentStateChanged(
            call_id=self._call_id,
            agent_generation_id=self._current_generation_id,
            state=new_state.value,
            ts=ts,
        )

    def handle_turn(
        self,
        agent_generation_id: UUID,
        route_a_label: RouteALabel,
        route_a_confidence: float,
        route_b_label: RouteBLabel | None,
        user_text: str,
        ts: int,
    ) -> AgentFSMOutput:
        """Process a turn classification result and emit appropriate events."""
        self._current_generation_id = agent_generation_id
        output = AgentFSMOutput()

        # Transition to THINKING
        state_change = self.transition("handle_turn", ts)
        if state_change:
            output.state_changes.append(state_change)

        # Route A: simple, disallowed, out_of_scope -> guided response
        if route_a_label in ROUTE_A_POLICY_MAP:
            policy_key = ROUTE_A_POLICY_MAP[route_a_label]
            output.guided_responses.append(
                RequestGuidedResponse(
                    call_id=self._call_id,
                    agent_generation_id=agent_generation_id,
                    policy_key=policy_key.value,
                    user_text=user_text,
                    ts=ts,
                )
            )
            done_change = self.transition("classification_done", ts)
            if done_change:
                output.state_changes.append(done_change)
            return output

        # Route A: domain -> Route B
        if route_a_label == RouteALabel.DOMAIN:
            if route_b_label is None:
                # Ambiguous -> clarify
                output.guided_responses.append(
                    RequestGuidedResponse(
                        call_id=self._call_id,
                        agent_generation_id=agent_generation_id,
                        policy_key=PolicyKey.CLARIFY_DEPARTMENT.value,
                        user_text=user_text,
                        ts=ts,
                    )
                )
            else:
                # Clear specialist
                output.agent_actions.append(
                    RequestAgentAction(
                        call_id=self._call_id,
                        agent_generation_id=agent_generation_id,
                        specialist=route_b_label.value,
                        user_text=user_text,
                        ts=ts,
                    )
                )
            done_change = self.transition("classification_done", ts)
            if done_change:
                output.state_changes.append(done_change)
            return output

        # Fallback (shouldn't happen with valid RouteALabel enum)
        done_change = self.transition("classification_done", ts)
        if done_change:
            output.state_changes.append(done_change)
        return output

    def cancel(self, ts: int) -> AgentStateChanged | None:
        """Cancel the current generation if in an active state."""
        if self._state in (AgentState.IDLE, AgentState.DONE, AgentState.CANCELLED, AgentState.ERROR):
            return None
        return self.transition("cancel", ts)

    def reset(self) -> None:
        """Reset FSM to idle for next generation."""
        self._state = AgentState.IDLE
        self._current_generation_id = None
