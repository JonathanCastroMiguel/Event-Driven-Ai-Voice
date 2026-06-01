# Draft — Option B: Full-Duplex Hybrid Architecture

> **Status**: exploratory draft. Not a decision, not a spec.
> **Context**: future migration path for the Voice AI runtime if/when a
> production-grade multilingual full-duplex S2S model becomes available
> (e.g., a future multilingual Moshi-style model).
> **Date**: 2026-05

---

## TL;DR

A hybrid architecture where a **full-duplex speech-to-speech (S2S) model**
handles natural conversational flow (turn-taking, barge-in, backchannels,
surface generation) while **business logic, routing, and content
generation for transactional cases stay outside the voice model**.

This is a **renegotiation** of the current strict philosophy
("everything that isn't audio production lives outside the model"), not a
preservation of it. The renegotiation is deliberate and bounded: critical
decisions stay external, low-risk surface decisions move into the model.

---

## 1. Why Option B and not strict philosophy on full-duplex

The strict philosophy of the current cloud architecture is:

> Business logic, routing, guardrails, tool execution, turn management,
> and even exact word generation (for substantive responses) live **outside**
> the voice model. The voice model is a constrained listener + speaker.

This philosophy maps **perfectly** to half-cascade (VAD → ASR → LLM → TTS
pipelines). It maps **poorly** to true full-duplex S2S because the value
proposition of full-duplex is precisely fusing reasoning, listening, and
speaking into one continuous forward pass. Constraining a full-duplex model
to "only speak what I tell you exactly" defeats its purpose — you're paying
for a 7B+ multimodal model to use 10% of its capability.

Option B accepts this and **redraws the line**:

- The S2S model handles **the conversational surface**: small talk, fillers,
  backchannels, turn-taking, barge-in, prosody, voice style.
- The backend handles **everything that matters for the business**:
  routing decisions, tool execution, guardrails, content of transactional
  responses, persistence, audit trail.

---

## 2. What the architecture looks like

### High-level diagram

```
┌───────────────────────────────────────────────────────────────────┐
│  Mobile App (WebRTC, native AEC/NS)                               │
└──────────────────────┬────────────────────────────────────────────┘
                       │ audio (full-duplex stream)
                       ▼
┌───────────────────────────────────────────────────────────────────┐
│  Voice Gateway (LiveKit on-prem)                                  │
│  - WebRTC media, signaling, TURN/ICE                              │
└──────────────────────┬────────────────────────────────────────────┘
                       │ audio frames (continuous, both directions)
                       ▼
┌───────────────────────────────────────────────────────────────────┐
│  Full-Duplex S2S Model (e.g., future multilingual Moshi)          │
│  ──────────────────────────────────────────────────────────────   │
│  Native: VAD, ASR, TTS, turn-taking, barge-in, backchannels       │
│  Generates smalltalk freely                                       │
│  Receives "content notes" from backend (see §4)                   │
│  Emits:                                                           │
│    • audio (continuous)                                           │
│    • ASR partials/finals (sideband stream to backend)             │
│    • optional: "request_help" signal (TBD, see §6)                │
└──────────────┬─────────────────────────────┬──────────────────────┘
               │ ASR stream                  │ audio output (to user)
               ▼                             │
┌───────────────────────────────────────────────────────────────────┐
│  Backend — Coordinator (custom Python / Rust)                     │
│  ──────────────────────────────────────────────────────────────   │
│  - Classifies transcripts (routing: direct vs specialist)         │
│  - Calls specialist LLM (Qwen3-32B / -235B) for substantive cases │
│  - Applies guardrails (compliance, PII, business rules)           │
│  - Executes tools, calls backend services                         │
│  - Persists conversation, audit trail                             │
│  - Pushes "content notes" back to the S2S model                   │
└───────────────────────────────────────────────────────────────────┘
```

### What stays from the current architecture

- **Coordinator** (Python/Rust) as the orchestration brain
- **Routing classifier** (text-based, on ASR partials) — same logic, same
  guardrails, same `route_to_specialist`-style dispatch
- **Specialist text models** (Qwen3-32B / Qwen3-235B) for substantive
  responses
- **Persistence layer** (Postgres + Redis), audit trail, idempotency
- **Backend agents** (MCP, business tools, integrations) unchanged

### What changes from the current architecture

- The **two-step routing pattern** (`tool_choice="required"`) disappears.
  No more dual `response.create` to extract a function call from a voice
  model.
- **TurnManager FSM** becomes mostly **observational** — the S2S model
  manages turns natively. The FSM logs what happened for audit but does
  not drive cancellation.
- **AgentFSM** simplifies: routing/waiting_tools/speaking states still exist
  but the transitions are driven by backend events, not by parsing voice
  model events.
- **Filler dispatch** disappears — the S2S model emits natural fillers and
  backchannels on its own. The backend stops worrying about "what to play
  while waiting".
- **"Say exactly" pattern** softens to **"content notes"** (see §4):
  the backend supplies the *information* to convey, the S2S model decides
  the *exact words and prosody*.

---

## 3. The pillar audit (what is preserved, what is relaxed)

Tu filosofía actual tiene tres pilares. Veamos su estado en Option B:

| # | Pillar | Status in Option B |
|---|---|---|
| 1 | Business logic outside the voice model | ✅ **Preserved**. Routing, tools, guardrails, persistence, compliance — all backend |
| 2 | "Who decides what to say" ≠ "who says it" | ⚠️ **Relaxed for smalltalk** (S2S does both). Preserved in spirit for substantive cases (backend supplies content, S2S phrases it) |
| 3 | External orchestrator manages turns and barge-in | ❌ **Moved into the model**. S2S handles natively. Backend observes for audit, does not drive |

### The line we are willing to redraw

| Function | Where it lives in Option B | Justification |
|---|---|---|
| Routing (is this smalltalk or transactional?) | **Backend** | High-stakes: a wrong classification could lead to wrong actions (fuel reservation, billing) |
| Guardrails (policy, compliance, PII) | **Backend** | Must be auditable and deterministic, never probabilistic |
| Tool execution / backend calls | **Backend** | Deterministic side effects |
| Substantive content (what to say in a transactional turn) | **Backend** (specialist LLM) | Must reflect real data, follow templates, respect tone of voice |
| Smalltalk surface (exact greeting words) | **S2S model** | Low risk, high upside in naturalness |
| Backchannels and fillers | **S2S model** | Low risk; high naturalness gain |
| Turn-taking and barge-in mechanics | **S2S model (native)** | The S2S's main value; constraining it externally defeats the purpose |
| Prosody and voice style | **S2S model** | Naturally tied to its forward pass |

### What we explicitly do NOT do

- We do **not** let the S2S decide whether a question requires backend help.
  That routing is done by the backend classifier on ASR partials.
- We do **not** let the S2S generate substantive answers freely. For
  transactional turns, the backend supplies the content.
- We do **not** let the S2S override guardrails. Even if it could phrase
  something differently, content boundaries are enforced before content
  reaches the S2S.

---

## 4. How content is injected into the S2S model

This is the most interesting design decision and the riskiest.

### The "content note" pattern

When the backend determines that a turn is transactional and the specialist
LLM produces text:

1. Backend computes the **content note**: a short structured payload
   containing the information to convey, optional tone hints, and any hard
   constraints (e.g., "must include the exact amount: 47€").

2. The note is **streamed into the S2S model's context** (mechanism depends
   on the S2S model's API — could be a system token, a structured side
   channel, or an in-band marker).

3. The S2S model **integrates the note into its natural speech flow**,
   respecting the constraints but phrasing it in its own voice and timing.

### Example

```
User (audio): "How much is my pending invoice?"

Backend (on ASR partial: "How much is my pending invoice"):
  1. Routes to specialist (billing)
  2. Specialist LLM looks up invoice → "47€, due 2026-05-30"
  3. Content note pushed to S2S:
       {
         "intent": "report_invoice_amount",
         "must_include": ["47€", "May 30"],
         "tone": "professional, warm",
         "language": "match_user"
       }

S2S model (audio output, freely phrased):
  "Sure, you have 47€ pending — that's due on May 30. Anything else?"
```

The S2S could equally have said: "Let me check… your pending invoice is 47€,
due by the 30th of May." The exact phrasing varies, but the **hard
constraints** (the amount, the date) are preserved.

### Verification layer (recommended)

A post-generation check that **validates the audio transcript** of the S2S
output against the constraints in the content note. If the S2S fails to
include a required field, the backend can:

- Re-prompt the S2S with a stronger constraint
- Fall back to a deterministic TTS for that segment
- Log the failure and alert

This **closes the loop** on the surface relaxation: the S2S has freedom in
*how* but not in *what*.

---

## 5. The S2S model requirements

For Option B to work, the chosen S2S model must support, at minimum:

1. **True full-duplex streaming** (audio in + audio out continuous, not
   strict turn-taking)
2. **ASR partials/finals exposed as a sideband stream** so the backend can
   classify in parallel
3. **Multilingual production-grade** in target languages (for the UAE case:
   Arabic Gulf + English with code-switching)
4. **Some mechanism to inject context mid-conversation** (system messages,
   tool outputs, structured side channel, or in-band markers)
5. **Optional but valuable**: ability to constrain generation (grammar-style
   constraints, "must include" tokens, or a small alignment layer)

As of mid-2026, **no open-source S2S model meets all five**. Moshi (Kyutai)
meets 1 and 2 but is English-only. GLM-4-Voice and Step-Audio meet 1 and 4
but lack Arabic. The day a multilingual Moshi-class model appears, Option B
becomes viable.

---

## 6. Open questions (must be resolved before piloting)

### 6.1 Routing trigger

In our current cloud arch, routing is triggered by `audio_committed` (VAD
end-of-turn) → first `response.create` with `tool_choice="required"`.

In full-duplex, there is no clean end-of-turn signal. Two options:

- **A. Continuous routing on ASR partials**: backend runs the classifier on
  every partial transcript update. Re-classifies and possibly re-dispatches
  if the partial drifts. Higher cost, lower latency to dispatch.
- **B. Endpointing inferred from S2S state**: the S2S model signals "user
  paused" → backend classifies once. Closer to current pattern, depends on
  the model exposing such a signal.

Default recommendation: start with B if the model supports it, fall back to
A if not.

### 6.2 Cancellation when routing decides "this needs backend"

If the S2S is already generating a smalltalk-style filler audio when the
backend decides "actually this is transactional and needs a specialist
response", how do we **interrupt the S2S cleanly**?

- Send a "stop and listen" signal? (model must support)
- Inject the content note immediately and let the S2S transition naturally
  ("…actually, let me check that for you — yes, it's 47€…")?
- Accept some audible discontinuity?

This is design work that depends on the specific S2S model's behavior.

### 6.3 Audit trail

How do we reconstruct **what the agent actually said** for compliance
audits? In half-cascade, the LLM output is text and the TTS is
deterministic — easy to log. In Option B, the S2S generates audio that
varies in surface form. We need:

- ASR of the agent's own audio output (self-transcription)
- Logged with the content note that was injected
- Diff stored: what we asked vs what was said

This is non-trivial overhead but essential for regulated use cases.

### 6.4 Guardrail enforcement

Backend guardrails work on text before it reaches TTS. In Option B, if the
S2S has freedom to phrase, could it generate something off-policy by
extrapolating from the content note?

Mitigations:

- Content notes are minimal and constrained (information only, no
  inferences)
- Self-transcription + post-hoc guardrail check (best effort)
- Hard fallback to deterministic TTS for high-risk segments

---

## 7. Why this matters specifically for the UAE gas-station use case

The use case has both transactional and conversational components:

- **Transactional** (high stakes): fuel reservation, prepayment, invoice
  inquiry, upselling with specific products and prices, customer ID
  verification.
- **Conversational** (low stakes but high UX impact): greetings, ack,
  small talk while waiting at the pump, natural pauses, code-switching
  Arabic/English mid-sentence.

Half-cascade handles transactional perfectly but feels stiff in
conversational. A future Option B deployment would:

- Keep transactional rigour (no compromise on amounts, IDs, confirmations)
- Add conversational naturalness via the S2S surface layer
- Reduce perceived latency through native turn-taking (no end-of-turn
  silence wait)

The **business risk** is concentrated in transactional turns, and those
remain under backend control. The **business reward** is in conversational
turns, and those benefit from the S2S model's natural flow.

---

## 8. Migration path (not a plan, a sketch)

1. **Phase 0 (now)**: deploy half-cascade on-prem (current plan). Validate
   the business and the on-prem deployment.
2. **Phase 1 (when a multilingual S2S production-grade emerges)**: pilot
   Option B for **smalltalk-only sessions** (e.g., a "concierge" experience
   with no transactions). Validate naturalness, audit trail, cost.
3. **Phase 2**: extend Option B to **mixed sessions**. Backend retains full
   control over transactional turns; S2S handles conversational layer.
   Resolve open questions §6.
4. **Phase 3**: full production rollout. Half-cascade kept as fallback for
   languages or use cases where the S2S model is not strong enough.

---

## 9. Summary

Option B is a deliberate **renegotiation** of the strict separation
philosophy. It preserves the parts that matter for business and auditability
(routing, guardrails, tools, content of substantive answers) and relaxes the
parts where the cost of relaxation is low and the upside is high (surface
generation, turn-taking, fillers, prosody).

It is **not** a degradation of the current architecture. It is a different
architectural contract, suitable for a different generation of voice models.

**Current status**: parked until multilingual S2S production-grade arrives.
The current half-cascade on-prem design remains the production target for
the foreseeable future.
