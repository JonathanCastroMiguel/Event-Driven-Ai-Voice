## MODIFIED Requirements

### Requirement: Prompt construction via policy keys
The Coordinator SHALL construct prompts for `realtime_voice_start` by combining: (1) base system instruction (constant), (2) policy-key-specific instruction block from `policies.yaml`, (3) conversation history from `ConversationBuffer.format_messages()`, (4) current user text. The `policy_key` MUST be a value from the closed `PolicyKey` enum. When the conversation buffer is empty (first turn), the prompt SHALL be identical to the previous single-turn format.

#### Scenario: Prompt for greeting policy (first turn, no history)
- **WHEN** Coordinator receives `request_guided_response(policy_key="greeting", user_text="hola")` and the conversation buffer is empty
- **THEN** the prompt sent to Realtime SHALL be `[{"role":"system","content":BASE_SYSTEM}, {"role":"system","content":GREETING_POLICY}, {"role":"user","content":"hola"}]`

#### Scenario: Prompt with conversation history (subsequent turn)
- **WHEN** Coordinator receives `request_guided_response(policy_key="greeting", user_text="¿cuánto debo?")` and the buffer contains one prior turn (user: "mi factura", specialist: "billing")
- **THEN** the prompt SHALL be `[{"role":"system","content":BASE_SYSTEM}, {"role":"system","content":GREETING_POLICY}, {"role":"user","content":"mi factura"}, {"role":"assistant","content":"[domain] Specialist: billing"}, {"role":"user","content":"¿cuánto debo?"}]`

#### Scenario: Invalid policy key rejected
- **WHEN** Agent FSM sends a `policy_key` not in the PolicyKey enum
- **THEN** Coordinator SHALL log an error and use a safe fallback policy (e.g., `clarify_department`)

### Requirement: Coordinator manages ConversationBuffer lifecycle
The Coordinator SHALL create a `ConversationBuffer` at initialization (alongside `CoordinatorRuntimeState`) and append turn entries after successful prompt construction and voice start emission.

#### Scenario: Buffer created on Coordinator init
- **WHEN** a Coordinator is instantiated for a new call
- **THEN** it SHALL create a `ConversationBuffer` with limits from `Settings.max_history_turns` and `Settings.max_history_chars`

#### Scenario: Turn appended to buffer after voice start
- **WHEN** the Coordinator emits a `RealtimeVoiceStart` for a guided response or specialist action
- **THEN** it SHALL append a `TurnEntry` to the conversation buffer with the current turn's user text, route_a_label, policy_key, and specialist

#### Scenario: Cancelled turn not appended
- **WHEN** a turn is cancelled due to barge-in or rapid successive turns before voice start
- **THEN** the Coordinator SHALL NOT append any entry to the conversation buffer

## ADDED Requirements

### Requirement: Configuration for conversation history limits
The Coordinator SHALL read `max_history_turns` (default: 10) and `max_history_chars` (default: 2000) from the application Settings and pass them to the ConversationBuffer.

#### Scenario: Custom history limits from environment
- **WHEN** `MAX_HISTORY_TURNS=5` and `MAX_HISTORY_CHARS=1000` are set in the environment
- **THEN** the ConversationBuffer SHALL use max_turns=5 and max_chars=1000

#### Scenario: Default history limits
- **WHEN** no history limit environment variables are set
- **THEN** the ConversationBuffer SHALL use max_turns=10 and max_chars=2000
