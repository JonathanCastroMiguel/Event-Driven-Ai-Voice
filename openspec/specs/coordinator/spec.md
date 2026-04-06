### Requirement: Turn lifecycle orchestration
On receiving `audio_committed` (translated from `input_audio_buffer.committed`), the Coordinator SHALL create a new `agent_generation_id`, set it as `active_agent_generation_id`, construct the router prompt via `RouterPromptBuilder`, and emit `realtime_voice_start` with the router prompt. The Coordinator SHALL NOT wait for `transcript_final` to begin routing. Transcription events SHALL be processed asynchronously for conversation buffer logging and persistence only.

#### Scenario: Turn triggered by audio committed
- **WHEN** the Bridge emits an `audio_committed` event after server VAD detects end of speech
- **THEN** the Coordinator SHALL create an `agent_generation_id`, build the router prompt with conversation history, and emit `realtime_voice_start` with the router prompt as instructions

#### Scenario: Transcript received after routing started
- **WHEN** `transcript_final` arrives after `audio_committed` has already triggered routing
- **THEN** the Coordinator SHALL append the transcript text to the conversation buffer and persist it, but SHALL NOT trigger any additional routing

#### Scenario: Rapid successive turns
- **WHEN** a new `audio_committed` arrives while a previous generation is still active
- **THEN** the Coordinator SHALL cancel the previous `agent_generation_id` and `voice_generation_id` before starting the new turn

#### Scenario: First turn of call (no history)
- **WHEN** `audio_committed` arrives and the conversation buffer is empty
- **THEN** the Coordinator SHALL build the router prompt with an empty input array (no conversation history)

### Requirement: Model router response handling
The Coordinator SHALL handle two response modes from the Realtime model: (a) direct voice response (handled by the Bridge's two-step flow — the Coordinator receives `voice_generation_completed` as normal) and (b) function call routing (model calls `route_to_specialist()` with a specialist department). On receiving `model_router_action` from the Bridge, the Coordinator SHALL resolve the specialist tool name by calling `RouterPromptBuilder.get_department_tool(department)` instead of constructing it via `f"specialist_{department}"`. The Coordinator SHALL also resolve the filler message by calling `RouterPromptBuilder.get_department_filler(department)` instead of the hardcoded `"Un momento, por favor."`. If `get_department_filler` returns `None`, no filler SHALL be emitted. The Coordinator SHALL receive a reference to the `RouterPromptBuilder` (already available as a constructor dependency) and use its methods for both tool name and filler resolution.

When the specialist tool returns successfully, the Coordinator SHALL treat the tool result payload as a **literal text string** to be vocalized. The Coordinator SHALL wrap this text in a `response.create` dict with a directive instruction that forces the Realtime model to speak the text exactly as provided, without paraphrasing or adding content.

#### Scenario: Direct voice response completes
- **WHEN** the Bridge emits `voice_generation_completed` (from the two-step direct flow)
- **THEN** the Coordinator SHALL clear `active_voice_generation_id`, finalize the agent generation as completed, and append the turn to the conversation buffer

#### Scenario: Function call triggers specialist tool via config lookup
- **WHEN** the Bridge emits `model_router_action` with `department="retention"`
- **THEN** the Coordinator SHALL call `self._router_prompt_builder.get_department_tool("retention")` to get the tool name
- **AND** dispatch tool execution with the resolved tool name (e.g., `"specialist_retention"`)

#### Scenario: Direct department skips tool execution
- **WHEN** the Bridge emits `model_router_action` with `department="direct"`
- **THEN** `get_department_tool("direct")` SHALL return `None`
- **AND** the Coordinator SHALL follow the direct response flow without tool execution

#### Scenario: Filler selected from department config
- **WHEN** the Bridge emits `model_router_action` with `department="billing"` and billing has fillers configured
- **THEN** the Coordinator SHALL call `get_department_filler("billing")` and use the returned string as the `prompt` in `RealtimeVoiceStart`

#### Scenario: No filler when department has empty fillers
- **WHEN** the Bridge emits `model_router_action` with a department that has `fillers=[]`
- **THEN** `get_department_filler` SHALL return `None`
- **AND** the Coordinator SHALL skip filler emission (no `RealtimeVoiceStart`)

#### Scenario: Specialist tool result vocalized literally
- **WHEN** the specialist tool returns `ok=True` with a `str` payload (text model response)
- **THEN** the Coordinator SHALL wrap the text in a `response.create` dict with a directive instruction (e.g., "Say exactly the following to the customer: <text>") and emit it as `RealtimeVoiceStart` with `response_source="specialist"`
- **AND** the Coordinator SHALL NOT forward the raw text as a plain string prompt

#### Scenario: Specialist tool failure
- **WHEN** the specialist tool returns `ok=False`
- **THEN** the Coordinator SHALL construct a fallback `response.create` with a generic apology message and emit it as `RealtimeVoiceStart`

#### Scenario: Unknown department from model
- **WHEN** the Bridge emits `model_router_action` with a department not in the config
- **THEN** `get_department_tool` SHALL return `None`
- **AND** the Coordinator SHALL log a warning and follow the direct response fallback

### Requirement: Barge-in handling
On receiving `speech_started` while `active_voice_generation_id` is set, the Coordinator SHALL: (1) emit `realtime_voice_cancel(active_voice_generation_id)`, (2) emit `cancel_agent_generation(active_agent_generation_id)`, (3) add both IDs to their respective cancelled sets, (4) forward the event to TurnManager.

#### Scenario: Barge-in during direct voice response
- **WHEN** user starts speaking while the model is speaking a direct response (speech_started with active_voice_generation_id)
- **THEN** Coordinator SHALL cancel voice output and agent generation, ensuring no double response

#### Scenario: Barge-in during specialist tool execution
- **WHEN** user starts speaking while a specialist tool is running
- **THEN** Coordinator SHALL cancel the tool via `cancel_tool`, cancel the agent generation, and any late `tool_result` SHALL be ignored

#### Scenario: Late tool result after cancellation
- **WHEN** a `tool_result` arrives for a cancelled `agent_generation_id`
- **THEN** Coordinator SHALL check the `cancelled_agent_generations` set and discard the result silently

### Requirement: Prompt construction via router prompt
The Coordinator SHALL construct prompts for `realtime_voice_start` by using `RouterPromptBuilder` to combine: (1) router prompt template (static instructions), (2) conversation history from `ConversationBuffer.format_messages()` (dynamic input). The Coordinator SHALL NOT use `PoliciesRegistry` for per-turn prompt construction — policies are embedded in the router prompt template.

#### Scenario: Router prompt with conversation history
- **WHEN** the Coordinator handles `audio_committed` and the buffer contains 2 prior turns
- **THEN** the `response.create` payload SHALL have `instructions` set to the router prompt template and `input` containing the 2 prior turns as message pairs

#### Scenario: Specialist response prompt after tool result
- **WHEN** a tool result is received for a specialist action
- **THEN** the Coordinator SHALL construct a specialist response prompt with the tool result and emit `realtime_voice_start`

### Requirement: Async transcript logging
The Coordinator SHALL process `transcript_final` events for logging purposes only. On receiving `transcript_final`, the Coordinator SHALL: (1) update the current turn's `text_final` in persistence, (2) append to conversation buffer if a turn is active, (3) emit debug event with transcript text. It SHALL NOT trigger routing or FSM transitions.

#### Scenario: Transcript logged for active turn
- **WHEN** `transcript_final` arrives with text "quiero cambiar mi plan" and a turn is active
- **THEN** the Coordinator SHALL persist the text, append to buffer, and emit a debug event, but SHALL NOT trigger any routing

#### Scenario: Transcript arrives with no active turn
- **WHEN** `transcript_final` arrives but no turn is currently active
- **THEN** the Coordinator SHALL log the transcript at debug level and discard it

### Requirement: Pipeline timing instrumentation

The Coordinator SHALL log ms-level timing at every event handler boundary, enabling production latency debugging.

Required timing points:
- `speech_started`: record `turn_speech_started_ms`
- `audio_committed`: log `speech_to_committed_ms` (delta from speech_started)
- `model_router_dispatched`: log `dispatch_elapsed_ms` (time to build and send prompt), `speech_to_dispatch_ms` (total from speech start)
- `transcript_final`: log `transcript_elapsed_ms` (delta from audio_committed)
- `model_router_action`: log `routing_elapsed_ms` (delta from dispatch)
- `voice_generation_completed`: log `voice_elapsed_ms` (delta from dispatch), `total_turn_ms` (full turn duration)

#### Scenario: Timing logged for complete turn
- **WHEN** a full voice turn completes (speech_started → voice_generation_completed)
- **THEN** structured logs SHALL include `total_turn_ms` and per-stage deltas

### Requirement: FSM state transition logging

The Coordinator SHALL log every FSM state transition with the format `fsm_<event_name>` including from/to states.

#### Scenario: Routing transition logged
- **WHEN** the FSM transitions from idle to routing after audio_committed
- **THEN** a structured log SHALL be emitted with `fsm_transition` from `idle` to `routing`

### Requirement: Fallback prompt uses instructions-based history

When the router prompt is not available and the Coordinator falls back to a default prompt, conversation history SHALL be embedded in the `instructions` field (not `response.input`), consistent with the RouterPromptBuilder behavior.

#### Scenario: Fallback with history
- **WHEN** the Coordinator uses the fallback prompt path with existing conversation history
- **THEN** the `response.create` payload SHALL contain history in `instructions` and MUST NOT contain a `response.input` field

### Requirement: Client debug event integration

The Coordinator SHALL receive `client_debug_event` messages forwarded from the WebSocket handler and integrate them into the debug pipeline.

#### Scenario: Audio playback start from frontend
- **WHEN** a `client_debug_event` with `stage="audio_playback_start"` arrives
- **THEN** the Coordinator SHALL call `_send_debug("audio_playback_start")` with proper `delta_ms`/`total_ms` relative to `_debug_turn_start_ms`

#### Scenario: Audio playback end from frontend
- **WHEN** a `client_debug_event` with `stage="audio_playback_end"` arrives
- **THEN** the Coordinator SHALL call `_send_debug("audio_playback_end")` and set `_debug_audio_playback_end_received = True`

#### Scenario: Fallback generation_finish when frontend event missing
- **WHEN** `_on_voice_completed` fires and `_debug_audio_playback_end_received` is False (barge-in, disconnect)
- **THEN** the Coordinator SHALL emit `_send_debug("generation_finish")` as a fallback

### Requirement: Bridge timing data in debug events

The Coordinator SHALL read timing metrics from EventEnvelope payloads and forward them in debug events.

#### Scenario: Model processing with bridge timing
- **WHEN** `response_created` payload includes `send_to_created_ms` and `response_source`
- **THEN** the Coordinator SHALL emit `_send_debug("model_processing", send_to_created_ms=...)` for router responses, or `_send_debug("specialist_processing")` for specialist responses

#### Scenario: Generation finish with bridge timing
- **WHEN** `voice_generation_completed` payload includes `created_to_done_ms`
- **THEN** the Coordinator SHALL pass `created_to_done_ms` as an extra field in the debug event

### Requirement: Direct route result at response.done

On `voice_generation_completed` for router responses with no prior `model_router_action`, the Coordinator SHALL emit `_send_debug("route_result", label="direct", route_type="direct")`. The Coordinator SHALL NOT emit `generation_start` from the backend — this now comes from the frontend as `audio_playback_start`.

#### Scenario: Direct route result emitted
- **WHEN** `voice_generation_completed` arrives with `response_source="router"` and no function call was received
- **THEN** the Coordinator SHALL emit `route_result(direct)` and set `_debug_route_result_emitted = True`

### Requirement: Specialist prompt as dict with embedded history

The Coordinator SHALL build specialist prompts as a `response.create` dict with the text model's literal response wrapped in a directive instruction. The directive SHALL instruct the Realtime model to vocalize the provided text exactly, in the customer's language, without adding, removing, or paraphrasing any content.

#### Scenario: Specialist responds in customer's language
- **WHEN** the customer spoke Spanish and the text model generated a Spanish triage response
- **THEN** the specialist `response.create` payload SHALL contain a directive instruction wrapping the text model's response, ensuring the Realtime model speaks it verbatim
