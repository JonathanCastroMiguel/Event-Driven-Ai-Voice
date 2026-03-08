## MODIFIED Requirements

### Requirement: Agent FSM states and transitions
The Agent FSM SHALL implement the following states: `idle`, `routing`, `speaking`, `waiting_tools`, `done`, `cancelled`, `error`. Transitions SHALL be defined as a dict mapping and enforced — invalid transitions SHALL raise an error.

#### Scenario: Routing state on audio committed
- **WHEN** Agent FSM is in `idle` state and receives `start_routing`
- **THEN** it SHALL transition to `routing` and emit `agent_state_changed(state="routing")`

#### Scenario: Direct voice response from routing
- **WHEN** Agent FSM is in `routing` state and receives `voice_started` (model is speaking directly)
- **THEN** it SHALL transition to `speaking`

#### Scenario: Specialist action from routing
- **WHEN** Agent FSM is in `routing` state and receives `specialist_action`
- **THEN** it SHALL transition to `waiting_tools`

#### Scenario: Tool result received
- **WHEN** Agent FSM is in `waiting_tools` state and receives `tool_result`
- **THEN** it SHALL transition to `speaking` (specialist response being generated)

#### Scenario: Voice generation completed
- **WHEN** Agent FSM is in `speaking` state and receives `voice_completed`
- **THEN** it SHALL transition to `done`

#### Scenario: Cancellation from any active state
- **WHEN** Agent FSM receives `cancel` while in `routing`, `speaking`, or `waiting_tools`
- **THEN** it SHALL transition to `cancelled` and stop all processing for that generation

#### Scenario: Invalid state transition rejected
- **WHEN** Agent FSM is in `done` state and receives `start_routing`
- **THEN** it SHALL raise an error and log the invalid transition attempt

## REMOVED Requirements

### Requirement: Route A classification (intent level 1)
**Reason**: Replaced by model-as-router architecture. The Realtime voice model performs classification and response in a single inference via the router prompt. Embedding-based Route A classification is no longer needed on the hot path.
**Migration**: Classification is performed by the router prompt in `response.create`. The model decides whether to speak directly (simple/disallowed/out_of_scope) or return a JSON action (domain→specialist).

### Requirement: Route B classification (specialist routing)
**Reason**: Replaced by model-as-router. The model returns `{"action": "specialist", "department": "<name>"}` directly, eliminating the need for a second embedding classification pass.
**Migration**: Department routing is embedded in the router prompt. The model specifies the department in its JSON action response.

### Requirement: Short utterance handling
**Reason**: No longer needed. The model handles short utterances natively — no need for a separate registry to short-circuit embedding classification.
**Migration**: The router prompt handles greetings and short utterances as direct voice responses.

### Requirement: 3rd-party LLM fallback for ambiguous classification
**Reason**: No longer needed. The Realtime voice model is the classifier — there is no ambiguous embedding score to trigger a fallback.
**Migration**: The model's classification is final. If routing accuracy needs improvement, the router prompt is tuned.

### Requirement: Language detection
**Reason**: Removed from hot path. The Realtime voice model handles multilingual intent natively. Language detection is no longer needed before classification.
**Migration**: The router prompt instructs the model to respond in the same language as the user. No explicit language detection step required.

### Requirement: Classification pipeline order
**Reason**: The 6-step classification pipeline (language → lexicon → short utterances → Route A → Route B → LLM fallback) is replaced by a single model inference via the router prompt.
**Migration**: The entire pipeline is replaced by `response.create` with the router prompt. The model performs classification and response in one step.

### Requirement: Agent FSM does not execute tools or speak
**Reason**: Requirement text updated — the FSM still does not execute tools or speak directly, but it no longer emits routing events based on embedding classification. The FSM tracks lifecycle states only.
**Migration**: FSM emits state transitions (`routing`, `speaking`, `waiting_tools`, `done`) instead of `request_guided_response` and `request_agent_action`.
