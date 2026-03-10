# Voice AI Runtime — Architecture Diagrams

Visual reference for the event-driven voice runtime. See `architecture.md` for detailed documentation.

---

## 1. System Topology

```
                          ┌──────────────────────────────────────────┐
                          │              OpenAI Realtime API          │
                          │  (gpt-4o-realtime-preview)               │
                          │                                          │
                          │  ┌──────────┐  ┌───────────────────────┐ │
                          │  │ STT/TTS  │  │ Function Call Engine   │ │
                          │  │ (Whisper) │  │ route_to_specialist() │ │
                          │  └──────────┘  └───────────────────────┘ │
                          │                                          │
                          │  Server VAD (silence_duration_ms=300)    │
                          │  Output Audio Buffer (FIFO queue)        │
                          └───────────┬──────────────────────────────┘
                                      │
                          WebRTC (Opus audio + DataChannel "oai-events")
                                      │
                          ┌───────────┴──────────────────────────────┐
                          │               Browser (Frontend)          │
                          │                                          │
                          │  Microphone ──→ RTCPeerConnection ──→ OpenAI
                          │                    │                     │
                          │  Speaker   ←── Audio Track ←──── OpenAI  │
                          │                    │                     │
                          │  DataChannel ←──→ oai-events ←──→ OpenAI │
                          │       │                                  │
                          │  Transcription Panel   Debug Panel       │
                          └───────┬──────────────────────────────────┘
                                  │
                     WebSocket (WS /calls/{call_id}/events)
                      + HTTP (SDP signaling, session mgmt)
                                  │
┌─────────────────────────────────┴──────────────────────────────────────────┐
│                              Backend (FastAPI)                              │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    SDP Proxy & Session Lifecycle                      │  │
│  │                    (calls.py)                                        │  │
│  │                                                                      │  │
│  │  POST /calls ──→ Create actor stack                                  │  │
│  │  POST /calls/{id}/offer ──→ SDP exchange (ephemeral key)            │  │
│  │  WS /calls/{id}/events ──→ Event forwarding + session.update        │  │
│  │  DELETE /calls/{id} ──→ Teardown                                    │  │
│  └──────────────────────────┬───────────────────────────────────────────┘  │
│                             │                                              │
│  ┌──────────────────────────┴───────────────────────────────────────────┐  │
│  │                    RealtimeEventBridge                                │  │
│  │                    (realtime_event_bridge.py)                        │  │
│  │                                                                      │  │
│  │  OpenAI events ──→ EventEnvelopes (input translation)               │  │
│  │  Coordinator cmds ──→ response.create / response.cancel (output)    │  │
│  │  Function call detection (route_to_specialist)                      │  │
│  │  Transcript accumulation (filler text + agent response)            │  │
│  │  Response source tracking (router vs specialist)                    │  │
│  │  Timing metrics (send_to_created_ms, created_to_done_ms)           │  │
│  └──────────────────────────┬───────────────────────────────────────────┘  │
│                             │                                              │
│  ┌──────────────────────────┴───────────────────────────────────────────┐  │
│  │                        Coordinator                                   │  │
│  │                        (coordinator.py)                              │  │
│  │                                                                      │  │
│  │  Central orchestrator — one instance per active call                 │  │
│  │  handle_event(envelope) → dispatch to handler methods               │  │
│  │  Idempotency (Redis TTLSet)                                         │  │
│  │  Barge-in handling + cancellation                                   │  │
│  │  Debug event emission (_send_debug / _emit_debug)                   │  │
│  │                                                                      │  │
│  │  ┌─────────────┐ ┌───────────┐ ┌──────────────┐ ┌───────────────┐  │  │
│  │  │ TurnManager │ │ Agent FSM │ │ ToolExecutor │ │ RouterPrompt  │  │  │
│  │  │             │ │           │ │              │ │ Builder       │  │  │
│  │  │ Speech turn │ │ State:    │ │ Whitelist    │ │               │  │  │
│  │  │ detection   │ │ IDLE      │ │ Redis cache  │ │ Prompt +      │  │  │
│  │  │ via server  │ │ ROUTING   │ │ Timeout      │ │ history +     │  │  │
│  │  │ VAD audio   │ │ SPEAKING  │ │ Cancel       │ │ tools         │  │  │
│  │  │ committed   │ │ WAIT_TOOL │ │              │ │               │  │  │
│  │  │             │ │ DONE      │ │ Tools:       │ │ response      │  │  │
│  │  │ Seq counter │ │ CANCELLED │ │  specialist  │ │ .create       │  │  │
│  │  │ Barge-in    │ │ ERROR     │ │  (billing,   │ │ payload       │  │  │
│  │  │ detection   │ │           │ │   support,   │ │               │  │  │
│  │  │             │ │           │ │   sales,     │ │               │  │  │
│  │  │             │ │           │ │   retention) │ │               │  │  │
│  │  └─────────────┘ └───────────┘ └──────────────┘ └───────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌────────────────────┐  ┌─────────────────┐  ┌────────────────────────┐  │
│  │ Router Registry    │  │ Policies        │  │ Embedding Pipeline     │  │
│  │ (YAML config)      │  │ Registry        │  │ (ANALYTICS ONLY)       │  │
│  │                    │  │                 │  │                        │  │
│  │ router_prompt.yaml │  │ base_system     │  │ sentence-transformers  │  │
│  │ thresholds.yaml    │  │ policy keys     │  │ hnswlib centroids      │  │
│  │ policies.yaml      │  │ instructions    │  │ lexicon checks         │  │
│  │ route_a/ route_b/  │  │                 │  │ LLM fallback           │  │
│  └────────────────────┘  └─────────────────┘  └────────────────────────┘  │
│                                                                            │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                        Infrastructure                              │    │
│  │                                                                    │    │
│  │  PostgreSQL 16          Redis 7             Observability          │    │
│  │  ┌────────────────┐    ┌──────────────┐    ┌──────────────────┐   │    │
│  │  │ call_sessions  │    │ TTLSet       │    │ OpenTelemetry    │   │    │
│  │  │ turns          │    │ (idempotency)│    │ Prometheus       │   │    │
│  │  │ agent_gens     │    │ TTLMap       │    │ Grafana          │   │    │
│  │  │ voice_gens     │    │ (tool cache) │    │ Sentry           │   │    │
│  │  │ tool_execs     │    │ Sessions     │    │ structlog        │   │    │
│  │  └────────────────┘    └──────────────┘    └──────────────────┘   │    │
│  └────────────────────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Actor Relationships

```
                    ┌─────────────────────────────┐
                    │     RealtimeEventBridge      │
                    │                             │
                    │  OpenAI events → envelopes  │
                    │  Commands → response.create │
                    │  Function call → routing    │
                    └──────────┬──────────────────┘
                               │
                    on_event() │ send_voice_start()
                               │ send_voice_cancel()
                               │ send_to_frontend()
                               │
                    ┌──────────┴──────────────────┐
                    │        Coordinator           │
                    │    (1 per active call)        │
                    │                              │
                    │  handle_event(envelope)      │
                    │  CoordinatorRuntimeState     │
                    │  ConversationBuffer          │
                    │  Debug emission              │
                    └──┬──────┬──────┬──────┬─────┘
                       │      │      │      │
          ┌────────────┘      │      │      └────────────────┐
          │                   │      │                       │
          ▼                   ▼      ▼                       ▼
┌─────────────────┐  ┌────────────┐  ┌──────────────┐  ┌──────────────────┐
│   TurnManager   │  │ Agent FSM  │  │ ToolExecutor │  │RouterPromptBuilder│
│                 │  │            │  │              │  │                  │
│ speech_started  │  │ IDLE       │  │ execute()    │  │ build_response   │
│ audio_committed │  │  ↓         │  │ cancel()     │  │   _create()      │
│ transcript_final│  │ ROUTING    │  │              │  │                  │
│                 │  │  ↓    ↓    │  │ Registered:  │  │ RouterPrompt     │
│ Outputs:        │  │ SPEAK WAIT │  │  specialist  │  │ Template (YAML)  │
│  HumanTurn      │  │  ↓    ↓   │  │              │  │ + history        │
│  Started        │  │ DONE SPEAK │  │ Redis cache  │  │ + tools          │
│  Finalized      │  │      ↓    │  │ Timeout      │  │ + tool_choice    │
│  Cancelled      │  │     DONE  │  │ Whitelist    │  │                  │
└─────────────────┘  └────────────┘  └──────────────┘  └──────────────────┘
```

---

## 3. Agent FSM State Machine

```
                          start_routing()
                 ┌─────┐ ──────────────→ ┌─────────┐
                 │ IDLE│                  │ ROUTING │
                 └─────┘                  └────┬────┘
                    ▲                          │
                    │ reset()      ┌───────────┼───────────┐
                    │              │           │           │
                    │    voice_started()  specialist_  cancel()/
                    │              │      action()    error()
                    │              ▼           ▼           ▼
                    │      ┌──────────┐ ┌────────────┐ ┌──────────┐
                    │      │ SPEAKING │ │WAITING_TOOLS│ │CANCELLED │
                    │      └────┬─────┘ └─────┬──────┘ └──────────┘
                    │           │             │
                    │  voice_completed() tool_result()
                    │           │             │
                    │           ▼             ▼
                    │      ┌──────┐    ┌──────────┐
                    └──────│ DONE │    │ SPEAKING │
                           └──────┘    └────┬─────┘
                                            │
                                   voice_completed()
                                            │
                                            ▼
                                       ┌──────┐
                                       │ DONE │
                                       └──────┘

 Direct response (~60-70%):  IDLE → ROUTING → SPEAKING → DONE
 Specialist routing:         IDLE → ROUTING → WAITING_TOOLS → SPEAKING → DONE
 Barge-in:                   Any active state → CANCELLED (via cancel())
```

---

## 4. TurnManager State Machine

```
                  speech_started(ts)
         ┌────┐ ──────────────────→ ┌──────┐
         │NONE│                     │ OPEN │ ←─┐
         └────┘                     └──┬───┘   │
                                       │       │
                   ┌───────────────────┼───────┤
                   │                   │       │
          audio_committed(ts)  speech_started  timeout(ts)
                   │           (barge-in)      │
                   ▼                │          ▼
            ┌───────────┐    ┌──────────┐  ┌───────────┐
            │ FINALIZED │    │CANCELLED │  │ CANCELLED │
            └───────────┘    └──────────┘  │(no_trans) │
                                    │      └───────────┘
                             new OPEN turn
                             opened immediately

 Primary trigger: audio_committed (server VAD, 300ms silence)
 transcript_final: async logging only, no state change
```

---

## 5. Model-as-Router Flow

```
                              User speaks
                                  │
                                  ▼
                         ┌────────────────┐
                         │ Server VAD     │
                         │ (OpenAI)       │
                         │ 300ms silence  │
                         └───────┬────────┘
                                 │
                    input_audio_buffer.committed
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │ RouterPromptBuilder    │
                    │                        │
                    │ RouterPromptTemplate   │
                    │ + conversation history │
                    │ + route_to_specialist  │
                    │   tool definition      │
                    │ + tool_choice: "auto"  │
                    └───────────┬────────────┘
                                │
                         response.create
                                │
                                ▼
                    ┌────────────────────────┐
                    │ OpenAI Realtime Model  │
                    │                        │
                    │ Single inference:      │
                    │ classify + respond     │
                    └───────────┬────────────┘
                                │
                 ┌──────────────┴──────────────┐
                 │                             │
          Direct Response              Function Call Routing
          (~60-70% of turns)           (specialist needed)
                 │                             │
                 ▼                             ▼
        ┌────────────────┐        ┌──────────────────────────┐
        │ Model speaks   │        │ TWO simultaneous outputs │
        │ directly       │        │                          │
        │ (greeting,     │        │ output[0]: Audio filler  │
        │  clarification,│        │ "Un momento, déjame      │
        │  guardrail)    │        │  conectarte con..."      │
        │                │        │                          │
        │ response.done  │        │ output[1]: Function call │
        │  → voice_gen   │        │ route_to_specialist(     │
        │    _completed  │        │   dept="billing",        │
        └────────────────┘        │   summary="..."          │
                                  │ )                        │
                                  │ (NEVER vocalized)        │
                                  └────────────┬─────────────┘
                                               │
                                  response.function_call_
                                  arguments.done
                                               │
                                               ▼
                                  ┌────────────────────────┐
                                  │ parse_function_call    │
                                  │ _action()              │
                                  │ → model_router_action  │
                                  │   event                │
                                  └────────────┬───────────┘
                                               │
                                               ▼
                                  ┌────────────────────────┐
                                  │ ToolExecutor           │
                                  │ → specialist tool      │
                                  │ → tool_result          │
                                  └────────────┬───────────┘
                                               │
                                               ▼
                                  ┌────────────────────────┐
                                  │ Specialist prompt      │
                                  │ (response.create)      │
                                  │                        │
                                  │ instructions:          │
                                  │  base_system +         │
                                  │  dept context +        │
                                  │  tool result +         │
                                  │  language instruction + │
                                  │  conversation history  │
                                  └────────────┬───────────┘
                                               │
                                    FIFO audio queue:
                                    filler plays first,
                                    specialist plays after
                                               │
                                               ▼
                                  ┌────────────────────────┐
                                  │ Specialist speaks in   │
                                  │ customer's language    │
                                  │ → voice_generation     │
                                  │   _completed           │
                                  └────────────────────────┘
```

---

## 6. Data Flow: Browser ↔ Backend ↔ OpenAI

```
 Browser                    Backend                     OpenAI
    │                          │                           │
    │──── POST /calls ────────→│                           │
    │←─── { call_id } ────────│  Create actor stack:      │
    │                          │  Coordinator, TurnMgr,   │
    │                          │  AgentFSM, ToolExec,     │
    │                          │  Bridge, RouterPrompt    │
    │                          │                           │
    │──── POST /calls/{id}/   │                           │
    │     offer (SDP) ────────→│── POST /v1/realtime/     │
    │                          │   sessions ──────────────→│
    │                          │←── ephemeral key ────────│
    │                          │── POST /v1/realtime      │
    │                          │   (SDP + key) ───────────→│
    │←─── SDP answer ─────────│←── SDP answer ───────────│
    │                          │                           │
    │◄═══ WebRTC established ═════════════════════════════►│
    │     (Opus audio + DataChannel "oai-events")          │
    │                          │                           │
    │──── WS /calls/{id}/     │                           │
    │     events ─────────────→│── session.update ────────→│
    │                          │   (whisper-1, VAD,        │
    │                          │    route_to_specialist    │
    │                          │    tool, tool_choice)     │
    │                          │                           │
    │                          │         === CALL ACTIVE ===
    │                          │                           │
    │  User speaks ═══════════════ Opus audio ════════════►│
    │                          │                           │
    │◄═══ speech_started ═════════════════════════════════│
    │──── speech_started ─────→│ Bridge → Coordinator     │
    │                          │  _on_speech_started()     │
    │                          │                           │
    │◄═══ audio_committed ════════════════════════════════│
    │──── audio_committed ────→│ Bridge → Coordinator     │
    │                          │  _on_audio_committed()    │
    │                          │  RouterPromptBuilder      │
    │◄──── response.create ───│── response.create ───────→│
    │      (via WS)            │   (via WS → DataChannel)  │
    │                          │                           │
    │◄═══ Audio response ═════════════════════════════════│
    │◄═══ DataChannel events ═════════════════════════════│
    │──── Forward events ─────→│ Bridge translates        │
    │     (via WS)             │  → EventEnvelopes        │
    │                          │  → Coordinator            │
    │                          │                           │
    │◄──── debug_event ───────│ (if debug enabled)        │
    │──── client_debug_event ─→│ audio_playback_start/end │
    │                          │                           │
    │──── DELETE /calls/{id} ─→│ Teardown                 │
    │                          │                           │

═══  WebRTC (direct browser ↔ OpenAI)
────  HTTP / WebSocket (browser ↔ backend)
```

---

## 7. Debug Pipeline

```
    Frontend                          Backend
       │                                │
       │  output_audio_buffer.started   │
       │──── client_debug_event ───────→│ Coordinator._send_debug(
       │     stage: audio_playback_     │   "audio_playback_start")
       │           start                │
       │                                │
       │  output_audio_buffer.stopped   │
       │──── client_debug_event ───────→│ Coordinator._send_debug(
       │     stage: audio_playback_     │   "audio_playback_end")
       │           end                  │
       │                                │
       │◄──── debug_event ─────────────│ stage: speech_start
       │◄──── debug_event ─────────────│ stage: speech_stop
       │◄──── debug_event ─────────────│ stage: audio_committed
       │◄──── debug_event ─────────────│ stage: prompt_sent
       │◄──── debug_event ─────────────│ stage: model_processing
       │                                │        (+ send_to_created_ms)
       │◄──── debug_event ─────────────│ stage: route_result
       │                                │        label: direct|delegate
       │                                │
       │  [If delegate route:]          │
       │◄──── debug_event ─────────────│ stage: fill_silence
       │◄──── debug_event ─────────────│ stage: specialist_sent
       │◄──── debug_event ─────────────│ stage: specialist_processing
       │                                │        (+ send_to_created_ms)
       │◄──── debug_event ─────────────│ stage: specialist_ready
       │◄──── debug_event ─────────────│ stage: generation_start
       │                                │
       │  [On barge-in / disconnect:]   │
       │◄──── debug_event ─────────────│ stage: barge_in
       │◄──── debug_event ─────────────│ stage: generation_finish
       │                                │        (fallback if no
       │                                │         audio_playback_end)
       │                                │
       │◄──── turn_update ─────────────│ (always-on)
       │◄──── fsm_state ──────────────│ (always-on)
       │◄──── transcript_final ────────│ (always-on)

 Direct response timeline:
   speech_start → speech_stop → audio_committed → prompt_sent
   → model_processing → route_result(direct)
   → audio_playback_start → audio_playback_end

 Specialist response timeline:
   speech_start → speech_stop → audio_committed → prompt_sent
   → model_processing → route_result(delegate) → fill_silence
   → specialist_sent → specialist_processing → specialist_ready
   → generation_start → audio_playback_start → audio_playback_end

 Barge-in: barge_in emitted, generation_finish as fallback
           if audio_playback_end never arrived
```
