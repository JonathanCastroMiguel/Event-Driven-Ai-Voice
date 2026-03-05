## ADDED Requirements

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
