from __future__ import annotations

from uuid import UUID

import structlog

from src.voice_runtime.events import AgentStateChanged
from src.voice_runtime.types import AgentState

logger = structlog.get_logger()

# Valid state transitions: from_state -> {event -> to_state}
TRANSITIONS: dict[AgentState, dict[str, AgentState]] = {
    AgentState.IDLE: {
        "start_routing": AgentState.ROUTING,
    },
    AgentState.ROUTING: {
        "voice_started": AgentState.SPEAKING,
        "specialist_action": AgentState.WAITING_TOOLS,
        "cancel": AgentState.CANCELLED,
        "error": AgentState.ERROR,
    },
    AgentState.WAITING_TOOLS: {
        "tool_result": AgentState.SPEAKING,
        "cancel": AgentState.CANCELLED,
        "error": AgentState.ERROR,
    },
    AgentState.SPEAKING: {
        "voice_completed": AgentState.DONE,
        "cancel": AgentState.CANCELLED,
        "error": AgentState.ERROR,
    },
    AgentState.DONE: {},
    AgentState.CANCELLED: {},
    AgentState.ERROR: {},
}


class AgentFSM:
    """Finite state machine for agent generation lifecycle.

    Tracks the lifecycle of the model's response: routing → speaking (direct)
    or routing → waiting_tools → speaking (specialist). Does NOT perform
    classification or execute tools directly.
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

    def start_routing(self, agent_generation_id: UUID, ts: int) -> AgentStateChanged | None:
        """Begin routing for a new agent generation. idle → routing."""
        self._current_generation_id = agent_generation_id
        return self.transition("start_routing", ts)

    def voice_started(self, ts: int) -> AgentStateChanged | None:
        """Model started speaking directly. routing → speaking."""
        return self.transition("voice_started", ts)

    def specialist_action(self, ts: int) -> AgentStateChanged | None:
        """Model called route_to_specialist() function. routing → waiting_tools."""
        return self.transition("specialist_action", ts)

    def tool_result(self, ts: int) -> AgentStateChanged | None:
        """Specialist tool completed. waiting_tools → speaking."""
        return self.transition("tool_result", ts)

    def voice_completed(self, ts: int) -> AgentStateChanged | None:
        """Voice generation finished. speaking → done."""
        return self.transition("voice_completed", ts)

    def cancel(self, ts: int) -> AgentStateChanged | None:
        """Cancel the current generation if in an active state."""
        if self._state in (AgentState.IDLE, AgentState.DONE, AgentState.CANCELLED, AgentState.ERROR):
            return None
        return self.transition("cancel", ts)

    def reset(self) -> None:
        """Reset FSM to idle for next generation."""
        self._state = AgentState.IDLE
        self._current_generation_id = None
