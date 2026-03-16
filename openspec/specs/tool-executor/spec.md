### Requirement: Deterministic tool_request_id
The `tool_request_id` SHALL be deterministic, derived from `agent_generation_id` + `tool_name` + hash of `args`. This enables idempotent execution — the same request always produces the same ID.

#### Scenario: Same request produces same ID
- **WHEN** `run_tool` is called twice with the same `agent_generation_id`, `tool_name`, and `args`
- **THEN** both calls SHALL produce the same `tool_request_id`

### Requirement: Tool execution with timeout
The ToolExecutor SHALL execute tools with a configurable `timeout_ms`. If the tool does not complete within the timeout, it SHALL be marked as `timeout` and a `tool_result(ok=false)` SHALL be emitted.

#### Scenario: Tool completes within timeout
- **WHEN** a tool completes in 200ms with `timeout_ms=5000`
- **THEN** ToolExecutor SHALL emit `tool_result(ok=true, payload=result)`

#### Scenario: Tool exceeds timeout
- **WHEN** a tool does not complete within `timeout_ms`
- **THEN** ToolExecutor SHALL emit `tool_result(ok=false, payload={"error":"timeout"})` and mark state as `timeout`

### Requirement: Tool cancellation
The ToolExecutor SHALL support cancellation via `cancel_tool` event. A cancelled tool SHALL stop execution if possible and mark state as `cancelled`.

#### Scenario: Tool cancelled mid-execution
- **WHEN** `cancel_tool` is received while a tool is in `running` state
- **THEN** ToolExecutor SHALL attempt to cancel the underlying operation and emit `tool_result(ok=false, payload={"error":"cancelled"})`

### Requirement: Tool result caching via Redis
Tool results SHALL be cached in Redis by `tool_request_id` with a 300s TTL. Before executing, ToolExecutor SHALL check the cache and return the cached result if available.

#### Scenario: Cache hit
- **WHEN** `run_tool` is called with a `tool_request_id` that exists in cache
- **THEN** ToolExecutor SHALL return the cached result immediately without execution

#### Scenario: Cache miss
- **WHEN** `run_tool` is called with a new `tool_request_id`
- **THEN** ToolExecutor SHALL execute the tool, cache the result, and emit `tool_result`

### Requirement: Tool state tracking
Each tool execution SHALL track state as one of: `running`, `succeeded`, `failed`, `cancelled`, `timeout`. State transitions SHALL be persisted in the `tool_executions` table.

#### Scenario: Successful tool persisted
- **WHEN** a tool completes successfully
- **THEN** its state SHALL be `succeeded` with `result_json` populated and `ended_at` set

#### Scenario: Failed tool persisted
- **WHEN** a tool throws an error
- **THEN** its state SHALL be `failed` with `error` field populated

### Requirement: Tool whitelist validation
The ToolExecutor SHALL validate `tool_name` against a registered tool whitelist before execution. Unknown tools SHALL be rejected.

#### Scenario: Unknown tool rejected
- **WHEN** `run_tool` is called with a `tool_name` not in the whitelist
- **THEN** ToolExecutor SHALL emit `tool_result(ok=false, payload={"error":"unknown_tool"})` without execution

### Requirement: Mock specialist tools registration
The system SHALL register mock specialist tools for each routing department at startup. The registered tool names SHALL be: `specialist_sales`, `specialist_billing`, `specialist_support`, `specialist_retention`. Each tool SHALL be registered via `ToolExecutor.register_tool()`.

#### Scenario: All specialist tools registered
- **WHEN** the application starts and initializes the ToolExecutor
- **THEN** the tools `specialist_sales`, `specialist_billing`, `specialist_support`, and `specialist_retention` SHALL be registered

#### Scenario: Specialist tool called by Coordinator
- **WHEN** the Coordinator calls `tool_executor.execute(tool_name="specialist_retention", args={"summary": "...", "history": [...]})`
- **THEN** the ToolExecutor SHALL find the registered tool and execute it

### Requirement: Mock specialist tool interface
Each mock specialist tool SHALL accept `summary` (str) and `history` (list of message dicts) as arguments. It SHALL return a complete `response.create` payload dict containing specialist instructions, conversation history, language detection, and triage steps. The Coordinator forwards this payload directly to the voice agent.

Each specialist tool SHALL have its own dedicated prompt with department-specific triage examples. The prompts SHALL NOT share a single template function. Department names SHALL appear only in English in the prompt text; the model SHALL translate department names dynamically based on the conversation language.

The triage examples SHALL be non-prescriptive — they guide the model on the type of clarifying questions to ask, but the model SHALL adapt them to the actual customer request.

#### Scenario: Mock tool returns response.create payload
- **WHEN** `specialist_retention` is called with `summary="cancellation request"` and conversation history
- **THEN** it SHALL return a dict with `type="response.create"` and `response` containing `modalities: ["text", "audio"]`, `instructions` (specialist prompt with triage steps and history), and `temperature`

#### Scenario: Per-department prompt differentiation
- **WHEN** `specialist_sales` generates its instructions
- **THEN** the instructions SHALL include sales-specific triage examples (e.g., current plan, desired features, budget)
- **WHEN** `specialist_billing` generates its instructions
- **THEN** the instructions SHALL include billing-specific triage examples (e.g., invoice number, charge date, amount)
- **WHEN** `specialist_support` generates its instructions
- **THEN** the instructions SHALL include support-specific triage examples (e.g., device/service affected, error messages, when it started)
- **WHEN** `specialist_retention` generates its instructions
- **THEN** the instructions SHALL include retention-specific triage examples (e.g., reason for leaving, how long as customer, what would change their mind)

#### Scenario: No hardcoded non-English department labels
- **WHEN** any specialist tool generates its instructions
- **THEN** the instructions text SHALL NOT contain hardcoded translations like "ventas", "facturación", "soporte técnico", or "retención"
- **AND** the instructions SHALL instruct the model to translate the department name to match the customer's language

#### Scenario: Specialist instructions include triage steps
- **WHEN** a mock specialist tool generates its instructions
- **THEN** the instructions SHALL include: (1) department identity in English, (2) department-specific triage examples, (3) triage steps (acknowledge, ask clarifying questions, then transfer), (4) language instruction (respond and translate department names in the customer's language), (5) conversation history formatted as User/Assistant turns

#### Scenario: History embedded in instructions
- **WHEN** a mock specialist tool receives a non-empty history
- **THEN** the `instructions` field SHALL include a `Conversation history:` section with all turns formatted as `User: <text>` / `Assistant: <text>`

#### Scenario: Step-awareness from history
- **WHEN** the conversation history shows the assistant has already asked clarifying questions and the customer answered
- **THEN** the specialist instructions SHALL guide the model to proceed to the transfer step
- **WHEN** the conversation history shows no prior specialist interaction
- **THEN** the specialist instructions SHALL guide the model to acknowledge and ask clarifying questions
