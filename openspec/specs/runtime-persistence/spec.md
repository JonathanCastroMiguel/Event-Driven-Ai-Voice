## ADDED Requirements

### Requirement: CallSessionContext persistence
The system SHALL persist call sessions in the `call_sessions` table with fields: `call_id` (UUID PK), `provider_call_id` (text), `started_at` (bigint), `ended_at` (bigint | null), `status` (text: active/ended), `locale_hint` (text | null), `customer_context` (jsonb | null). A sequential turn counter `seq_turn` SHALL be maintained in memory.

#### Scenario: Call session created
- **WHEN** a new call begins
- **THEN** a row SHALL be inserted into `call_sessions` with `status="active"` and `started_at` set to current timestamp

#### Scenario: Call session ended
- **WHEN** a call ends
- **THEN** the row SHALL be updated with `status="ended"` and `ended_at` set

### Requirement: Turn persistence
The system SHALL persist turns in the `turns` table with fields: `turn_id` (UUID PK), `call_id` (UUID FK), `seq` (int), `started_at` (bigint), `finalized_at` (bigint | null), `text_final` (text | null), `language` (text | null), `state` (text: open/finalized/cancelled), `cancel_reason` (text | null), `asr_confidence` (float | null).

#### Scenario: Turn finalized persisted
- **WHEN** TurnManager emits `human_turn_finalized`
- **THEN** the turn row SHALL be updated with `state="finalized"`, `text_final`, `finalized_at`, and detected `language`

#### Scenario: Turn cancelled persisted
- **WHEN** TurnManager emits `human_turn_cancelled`
- **THEN** the turn row SHALL be updated with `state="cancelled"` and `cancel_reason`

### Requirement: AgentGeneration persistence
The system SHALL persist agent generations in the `agent_generations` table with fields: `agent_generation_id` (UUID PK), `call_id` (UUID FK), `turn_id` (UUID FK), `created_at` (bigint), `started_at` (bigint | null), `ended_at` (bigint | null), `state` (text: thinking/waiting_tools/waiting_voice/done/cancelled/error), `route_a_label` (text | null), `route_a_confidence` (float | null), `policy_key` (text | null), `specialist` (text | null), `final_outcome` (text | null: guided_response/tool_response/handoff/noop), `cancel_reason` (text | null), `error` (text | null).

#### Scenario: Generation with routing data persisted
- **WHEN** Agent FSM completes classification
- **THEN** `route_a_label`, `route_a_confidence`, and `specialist` (if applicable) SHALL be persisted

#### Scenario: Generation cancelled persisted
- **WHEN** a generation is cancelled due to barge-in
- **THEN** `state` SHALL be `cancelled`, `cancel_reason` SHALL describe the cause, and `ended_at` SHALL be set

### Requirement: VoiceGeneration persistence
The system SHALL persist voice generations in the `voice_generations` table with fields: `voice_generation_id` (UUID PK), `provider_voice_generation_id` (text | null), `call_id` (UUID FK), `agent_generation_id` (UUID FK), `turn_id` (UUID FK), `kind` (text: filler/response), `state` (text: starting/speaking/completed/cancelled/error), `started_at` (bigint | null), `ended_at` (bigint | null), `cancel_reason` (text | null), `error` (text | null).

#### Scenario: Filler and response both persisted
- **WHEN** a turn produces both a filler and a final response
- **THEN** two rows SHALL exist in `voice_generations` with the same `agent_generation_id` but different `voice_generation_id` values and `kind` values

### Requirement: ToolExecution persistence
The system SHALL persist tool executions in the `tool_executions` table with fields: `tool_request_id` (UUID PK), `call_id` (UUID FK), `agent_generation_id` (UUID FK), `turn_id` (UUID FK), `tool_name` (text), `args_hash` (text), `args_json` (jsonb | null), `state` (text: running/succeeded/failed/cancelled/timeout), `started_at` (bigint | null), `ended_at` (bigint | null), `result_json` (jsonb | null), `error` (text | null).

#### Scenario: Successful tool execution persisted
- **WHEN** a tool completes successfully
- **THEN** `state` SHALL be `succeeded`, `result_json` SHALL contain the result, and `ended_at` SHALL be set

### Requirement: Hot-path writes via asyncpg
All runtime persistence writes (turns, agent_generations, voice_generations, tool_executions) SHALL use asyncpg raw parameterized queries, not SQLAlchemy. Target write latency: < 1ms per row.

#### Scenario: Turn insert latency
- **WHEN** a turn row is inserted via asyncpg
- **THEN** the write SHALL complete in under 1ms (excluding network latency to PostgreSQL)

### Requirement: Repository interfaces as Protocol
Each entity SHALL have a repository interface defined as a Python `Protocol`. Implementations SHALL use asyncpg for hot-path operations.

#### Scenario: Repository injection
- **WHEN** the Coordinator is instantiated
- **THEN** it SHALL receive repository implementations via constructor injection, enabling test doubles

### Requirement: Database indexes
The following indexes SHALL be created: `turns(call_id, seq)`, `agent_generations(turn_id)`, `voice_generations(agent_generation_id)`, `tool_executions(agent_generation_id)`, `call_sessions(status)`.

#### Scenario: Active calls query performance
- **WHEN** querying `call_sessions WHERE status='active'`
- **THEN** the query SHALL use the `call_sessions(status)` index
