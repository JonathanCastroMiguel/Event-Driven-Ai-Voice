## MODIFIED Requirements

### Requirement: Coordinator manages ConversationBuffer lifecycle
The Coordinator SHALL create a `ConversationBuffer` at initialization (alongside `CoordinatorRuntimeState`) and append turn entries after successful prompt construction and voice start emission. The Coordinator SHALL accept `max_history_turns`, `max_history_chars`, `routing_context_window`, `routing_short_text_chars`, and `llm_context_window` as constructor parameters with defaults from application Settings.

#### Scenario: Coordinator wired with output callback
- **WHEN** a Coordinator is instantiated for a new call
- **THEN** it SHALL support `set_output_callback()` to register a callback that dispatches `RealtimeVoiceStart`, `RealtimeVoiceCancel`, and `CancelAgentGeneration` events to external consumers (e.g., the Bridge)

#### Scenario: Output events dispatched via callback
- **WHEN** the Coordinator emits a `RealtimeVoiceStart` event and an output callback is registered
- **THEN** the callback SHALL be invoked with the event, and callback errors SHALL be caught and logged without crashing the Coordinator

#### Scenario: Buffer created on Coordinator init
- **WHEN** a Coordinator is instantiated for a new call
- **THEN** it SHALL create a `ConversationBuffer` with limits from constructor parameters
