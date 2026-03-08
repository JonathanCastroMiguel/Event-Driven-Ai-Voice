## Why

The current voice runtime architecture routes user intent through a multi-stage embedding pipeline (Route A → Route B → optional LLM fallback) that adds 200-800ms of latency per turn. Real-world testing revealed fundamental issues: (1) embedding-based routing struggles with conversational phrases (e.g., "Hola, ¿qué tal?" classified as `out_of_scope` instead of `simple`/`greeting`), (2) the Whisper transcription gate adds ~200-500ms before routing can even begin, and (3) the full pipeline (transcription → language detection → lexicon check → embeddings → optional LLM fallback → FSM decision → prompt construction → response.create) creates compounding latency that makes the system noticeably slower than direct Realtime API interaction.

The solution is a **model-as-router** architecture: use the Realtime voice model itself to classify intent AND respond in a single inference. After the server VAD commits the audio buffer (`input_audio_buffer.committed`), the Coordinator sends a single `response.create` with a router prompt. The model either speaks the response directly (simple cases like greetings, guardrails) or returns a structured JSON action (specialist cases requiring tool execution). This eliminates the embedding routing pipeline, language detection, and FSM decision layer from the hot path entirely.

## What Changes

- **Replace embedding-based routing with model-as-router**: Instead of Route A/B embedding classification, the Realtime model receives a router prompt that instructs it to either respond directly (for simple, disallowed, out-of-scope intents) or return a JSON action specifying which specialist to invoke.
- **Eliminate Whisper transcription as a routing gate**: Transcription (`input_audio_transcription.completed`) becomes an async side-channel for logging and conversation buffer — it no longer blocks the routing pipeline. The model classifies from audio directly.
- **Simplify turn closing**: Replace the triple condition (speech_stopped + silence buffer + transcript threshold) with server VAD's `input_audio_buffer.committed` event as the single turn-closing signal. Configure `silence_duration_ms` on the server VAD for tunable silence detection.
- **Two response modes from the model**: (a) Direct voice response — model speaks the answer (greeting, guardrail, simple question). (b) JSON action — model returns `{"action": "specialist", "department": "billing", "summary": "..."}` which the Coordinator intercepts to run tools and construct a specialist response.
- **Simplify Agent FSM**: Remove embedding classification states. FSM transitions become: `idle → routing (waiting for model response) → [direct_response | tool_execution] → done`. The FSM no longer runs the 6-step classification pipeline.
- **Remove language detection from hot path**: The model handles multilingual intent natively — no need for fasttext/langid before classification.
- **Remove RoutingContextBuilder from hot path**: The model receives conversation history directly in the prompt — no need for separate enriched text construction for embeddings.
- **Keep existing infrastructure**: Coordinator (simplified orchestration), TurnManager (turn lifecycle), Bridge (event translation), barge-in handling, conversation buffer, persistence, debug events — all retained with modifications.

## Capabilities

### New Capabilities
- `model-router`: Router prompt engineering and response parsing for the Realtime model. Defines the router system prompt that instructs the model when to speak directly vs. return JSON actions. Includes response format specification, action schema, and prompt templates for different conversation states.

### Modified Capabilities
- `coordinator`: Coordinator no longer waits for `transcript_final` to start routing. Instead, it reacts to `input_audio_buffer.committed` by sending `response.create` with the router prompt. Handles two response modes (direct voice vs. JSON action). Removes embedding classification dispatch. Simplifies prompt construction.
- `agent-fsm`: **BREAKING** — Remove embedding-based Route A/B classification pipeline (language detection → lexicon → short utterances → embeddings → LLM fallback). FSM states simplified to handle model routing responses instead. The 6-step classification pipeline is replaced by model response parsing.
- `turn-manager`: Turn finalization trigger changes from `transcript_final` to `input_audio_buffer.committed`. Transcription events become informational only (for logging/buffer), not turn-closing signals.
- `realtime-event-bridge`: Bridge must translate new event type `input_audio_buffer.committed` into a Coordinator event. Must handle model responses that contain JSON actions (intercept before voice output). Session configuration updated for server VAD with `silence_duration_ms`.
- `routing-context`: **BREAKING** — RoutingContextBuilder no longer produces enriched text for embedding classification. Simplified to format conversation history for the router prompt only. Embedding-specific enrichment (short text threshold, context window for centroids) removed.

## Impact

- **Backend code**: Major refactor of `coordinator.py` (routing flow), `agent_fsm.py` (classification removal), `turn_manager.py` (turn trigger change), `realtime_event_bridge.py` (new events + response interception). Router registry embedding files (`centroids/`, `thresholds.yaml`, lexicon files) become unused for hot-path routing but may be retained for analytics.
- **API**: No external API changes. `POST /calls`, WebSocket event forwarding, SDP exchange remain identical.
- **Dependencies**: `sentence-transformers`, `onnxruntime`, `hnswlib` no longer needed on hot path (may be retained for offline analytics). `langid`/`fasttext` removed from hot path.
- **Latency**: Expected reduction from 200-800ms (embedding pipeline) to near-zero additional latency (single model inference that also produces the response).
- **Frontend**: No changes required — frontend continues forwarding data channel events via WebSocket.
- **Tests**: Significant test updates required. Embedding classification tests become obsolete. New tests needed for router prompt parsing, JSON action handling, and committed-event-based turn flow.
- **Configuration**: New config for `silence_duration_ms` (server VAD tuning). Router prompt templates added to `policies.yaml` or new config file.
