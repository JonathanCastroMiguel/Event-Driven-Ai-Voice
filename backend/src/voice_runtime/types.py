from enum import Enum
from typing import NewType
from uuid import UUID

# Core identifiers
CallId = NewType("CallId", UUID)
TurnId = NewType("TurnId", UUID)
AgentGenerationId = NewType("AgentGenerationId", UUID)
VoiceGenerationId = NewType("VoiceGenerationId", UUID)
ToolRequestId = NewType("ToolRequestId", UUID)
EventId = NewType("EventId", UUID)


class PolicyKey(str, Enum):
    GREETING = "greeting"
    HANDOFF_OFFER = "handoff_offer"
    GUARDRAIL_DISALLOWED = "guardrail_disallowed"
    GUARDRAIL_OUT_OF_SCOPE = "guardrail_out_of_scope"
    CLARIFY_DEPARTMENT = "clarify_department"


class AgentState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    WAITING_TOOLS = "waiting_tools"
    WAITING_VOICE = "waiting_voice"
    DONE = "done"
    CANCELLED = "cancelled"
    ERROR = "error"


class RouteALabel(str, Enum):
    SIMPLE = "simple"
    DISALLOWED = "disallowed"
    OUT_OF_SCOPE = "out_of_scope"
    DOMAIN = "domain"


class RouteBLabel(str, Enum):
    SALES = "sales"
    BILLING = "billing"
    SUPPORT = "support"
    RETENTION = "retention"


class TurnState(str, Enum):
    OPEN = "open"
    FINALIZED = "finalized"
    CANCELLED = "cancelled"


class VoiceKind(str, Enum):
    FILLER = "filler"
    RESPONSE = "response"


class VoiceState(str, Enum):
    STARTING = "starting"
    SPEAKING = "speaking"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


class ToolState(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class CallStatus(str, Enum):
    ACTIVE = "active"
    ENDED = "ended"


class AgentGenerationOutcome(str, Enum):
    GUIDED_RESPONSE = "guided_response"
    TOOL_RESPONSE = "tool_response"
    HANDOFF = "handoff"
    NOOP = "noop"


class EventSource(str, Enum):
    REALTIME = "realtime"
    TURN_MANAGER = "turn_manager"
    AGENT = "agent"
    COORDINATOR = "coordinator"
    TOOL_EXEC = "tool_exec"
    TIMER = "timer"
