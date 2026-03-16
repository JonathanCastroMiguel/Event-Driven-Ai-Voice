## MODIFIED Requirements

### Requirement: Model router response handling
The Coordinator SHALL handle two response modes from the Realtime model: (a) direct voice response (handled by the Bridge's two-step flow — the Coordinator receives `voice_generation_completed` as normal) and (b) function call routing (model calls `route_to_specialist()` with a specialist department). On receiving `model_router_action` from the Bridge, the Coordinator SHALL dispatch specialist tool execution via `ToolExecutor`, passing both the summary and conversation history. The tool result SHALL contain a complete `response.create` payload that the Coordinator forwards to the voice agent without modification.

#### Scenario: Direct voice response completes
- **WHEN** the Bridge emits `voice_generation_completed` (from the two-step direct flow)
- **THEN** the Coordinator SHALL clear `active_voice_generation_id`, finalize the agent generation as completed, and append the turn to the conversation buffer

#### Scenario: Function call triggers specialist tool with history
- **WHEN** the Bridge emits `model_router_action` with `department="retention"` and `summary="cancellation request"`
- **THEN** the Coordinator SHALL dispatch tool execution for `specialist_retention` with `args={"summary": "cancellation request", "history": <conversation_history>}`

#### Scenario: Specialist tool result forwarded as voice start
- **WHEN** the specialist tool returns a `response.create` payload
- **THEN** the Coordinator SHALL emit `RealtimeVoiceStart` with the tool result payload as the `prompt` field and `response_source="specialist"`
- **AND** the Coordinator SHALL NOT modify the payload content

#### Scenario: Specialist tool failure
- **WHEN** the specialist tool returns `ok=False`
- **THEN** the Coordinator SHALL construct a fallback `response.create` with a generic apology message and emit it as `RealtimeVoiceStart`
