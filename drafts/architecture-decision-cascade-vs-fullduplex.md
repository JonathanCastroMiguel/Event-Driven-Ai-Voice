# Architecture Decision — Cascade vs Full-Duplex for On-Premise Voice AI

> **Status**: shareable internal note. Not a final spec.
> **Audience**: engineers and architects evaluating on-premise voice AI
> options for production at scale.
> **Companion document**: [`option-b-full-duplex-hybrid.md`](./option-b-full-duplex-hybrid.md)
> (the future-path exploration this document references).

---

## 1. Executive summary

We are choosing a **half-cascade (modular pipeline) architecture** for the
on-premise voice AI runtime:

```
audio in → VAD → ASR (streaming) → LLM → TTS (streaming) → audio out
```

with the existing custom Python/Rust orchestration layer (Coordinator,
TurnManager FSM, AgentFSM) preserved on top.

We are **not** going to a full-duplex speech-to-speech (S2S) native
architecture (Moshi-class), despite its lower theoretical latency.

This document explains why.

The decision is not driven by "cascade is better than full-duplex". It is
driven by:

1. **Architectural philosophy** — business logic, routing and guardrails
   must remain outside the voice model. This is non-negotiable for a
   regulated commercial deployment.
2. **Language coverage** — no production-grade multilingual full-duplex
   S2S model supports Arabic (Gulf in particular) at our quality bar.
3. **Tool-calling reliability** — the open-source LLM ecosystem is
   still uneven for forced function calling, which we need for routing.
4. **Operational maturity** — the modular pipeline reuses
   well-understood components with predictable scaling properties.

Full-duplex is a real future path. We document it as **Option B** in a
separate file. When a multilingual S2S model becomes production-ready,
we revisit.

---

## 2. Context

### 2.1 What we have today (cloud reference)

The cloud version of this runtime uses **OpenAI Realtime API**:

- Single multimodal model handles VAD + ASR + reasoning + TTS in one
  forward pass (speech-to-speech native).
- We constrain it to act as a **router** via `tool_choice="required"`
  on a single `route_to_specialist` function. The model emits a function
  call instead of speaking on the first response.create.
- For **direct** turns (smalltalk, simple questions, guardrails), a
  follow-up `response.create` is dispatched and the model freely
  generates the spoken reply under the same system prompt.
- For **specialist** turns (billing, sales, support, retention), a
  separate text model (`gpt-4o`) produces the answer; the Realtime
  model is told `"Say exactly: …"` and acts as a high-quality TTS.
- A Python/Rust **Coordinator** with two finite-state machines
  (TurnManagerFSM, AgentFSM) drives turn lifecycle, routing dispatch,
  cancellation, and barge-in. The voice model never owns business
  logic.

The system works in production. The architecture has been validated.
Our job for on-premise is to preserve this design with different
components.

### 2.2 What we are building (on-premise target)

- Deployment in the UAE (Abu Dhabi / Dubai) for call-center automation
  in the petrol-retail sector. Use cases: fuel reservation/prepayment,
  upselling, customer support.
- Hardware: 8 × H200 GPUs (active-active cluster).
- Concurrency target: 2000 peak concurrent voice sessions.
- Languages: Arabic (Gulf dialect) and English, with code-switching
  the norm rather than the exception.
- Latency target: 200–300 ms from end-of-user-speech to first agent
  audio for direct turns (matching ElevenLabs / OpenAI tier).
- Compliance: data residency in UAE; no audio leaves the cluster.
- Open-source publication of the runtime (this repository) is a goal.

### 2.3 The four architectural pillars we must preserve

These are not negotiable. They are why the cloud version works.

1. **Business logic lives outside the voice layer**. Routing,
   guardrails, tool execution, content of substantive answers — all
   driven by code we own, not by inference.
2. **"Who decides what to say" is separable from "who says it"**. In
   the specialist path the text model decides content, the voice layer
   speaks it. In the direct path the voice layer decides surface form
   but under our injected system prompt.
3. **Turn-taking and barge-in are owned by the orchestrator**. The
   Coordinator drives cancellation, the FSMs are the source of truth
   for "is the user speaking?" / "is the agent speaking?". Server-side
   VAD is a signal, not a decision-maker.
4. **Auditability**. Every routing decision, every tool call, every
   transition is observable and reproducible.

---

## 3. The three architectural options on the table

### 3.1 Strict cascade (modular pipeline) — recommended

```
Mobile app (WebRTC)
   ↓
LiveKit on-prem (signaling, TURN/ICE, media)
   ↓ audio
Voice agent (custom Python/Rust)
   ├─ VAD          (Silero / Riva)
   ├─ ASR streaming (Whisper Large v3 Turbo + faster-whisper; or Riva)
   ├─ Router LLM   (small fast LLM, e.g. Qwen3-1.7B with grammar-constrained output)
   ├─ LLM (fast)   (Qwen3-32B for direct + smalltalk + simple questions)
   ├─ LLM (premium)(Qwen3-235B-A22B for complex reasoning / tools / backend)
   ├─ TTS streaming(Riva TTS Arabic, Fish-Speech, or fine-tuned VITS)
   └─ Coordinator + TurnManagerFSM + AgentFSM (existing code, portable)
```

**Pros**:
- The four pillars from §2.3 map cleanly. The Coordinator stays.
- Production-grade open-source components exist for every box
  (Whisper, Riva, vLLM/TensorRT-LLM, Qwen3 family, LiveKit).
- Independent scaling per stage. Each module can be benchmarked,
  profiled, replaced.
- Auditable: text crosses every internal boundary. Logging is trivial.
- Predictable failure modes; failure of one stage degrades cleanly.

**Cons**:
- Latency floor is higher than full-duplex (~400–600 ms realistic for
  direct turns on H200 with all optimizations).
- More moving parts to operate.
- Prosody is lost at ASR (voice → text). The downstream stack works
  on text only. Tone of voice, emotion, urgency — gone.

### 3.2 Full-duplex S2S native (Moshi-class)

A single multimodal transformer that receives audio tokens and emits
audio tokens in a continuous streaming loop. Examples: Moshi
(Kyutai, Apache 2.0, English-only), GLM-4-Voice (Zhipu, en/zh),
Step-Audio (Stepfun, en/zh), Sesame CSM (English).

**Pros**:
- Latency floor ~200–300 ms in production (the OpenAI Realtime
  benchmark).
- Prosody preserved end-to-end. The model "hears" tone and can
  respond in kind.
- Native barge-in: model can interrupt itself when it hears speech in
  the same forward pass.
- Natural backchannels ("mhm", "okay", "got it") emerge from the
  model.

**Cons (blockers for our case)**:
- **No production-grade multilingual model exists**. Moshi is English;
  GLM-4-Voice and Step-Audio are English+Chinese. None ship Arabic
  Gulf at our bar. This alone disqualifies it for the UAE deployment
  today.
- **The model owns business logic by design**. It reasons while it
  listens. Constraining it to "shut up and only repeat what we tell
  you" wastes the model and breaks the value proposition.
- **Turn-taking moves into the model**. Our TurnManagerFSM /
  Coordinator-driven barge-in would be either redundant or fighting
  the model. The four pillars from §2.3 erode.

### 3.3 Option B — hybrid (full-duplex used surgically)

Detailed in [`option-b-full-duplex-hybrid.md`](./option-b-full-duplex-hybrid.md).

Briefly: an S2S native model handles the conversational surface
(smalltalk, fillers, backchannels, turn-taking, prosody) but
substantive content for transactional turns is generated by an
external LLM and injected into the S2S model as a structured "content
note" (must include amount X, must mention date Y). The S2S phrases
it freely but cannot invent the substantive content.

**This is the future path**. It depends on:
1. A multilingual full-duplex S2S model reaching production grade.
2. A clean mechanism to inject context into the S2S model
   mid-conversation.
3. A verification layer that confirms the spoken output respects
   hard constraints (audit transcript vs content note).

None of these are available today.

---

## 4. Pillar audit — which pillars survive in each option

| Pillar | Cascade | Full-duplex (strict) | Option B (hybrid) |
|---|---|---|---|
| 1. Business logic outside the voice layer | ✅ Preserved | ⚠️ Routing decisions live in the model | ✅ Preserved (LLM still owns substantive content) |
| 2. "Who decides" ≠ "who says it" | ✅ Preserved (text crosses every boundary) | ❌ Fused: model owns both | ⚠️ Relaxed for smalltalk; preserved for transactions |
| 3. Turn-taking + barge-in owned by orchestrator | ✅ Preserved | ❌ Moves into the model (and that's the model's value) | ❌ Moves into the model |
| 4. Auditability | ✅ Text logs at every stage | ⚠️ Requires self-transcription of model output to audit | ⚠️ Same: requires audit layer comparing spoken output to content note |

**Conclusion**: cascade is the only option that preserves all four
pillars without compromise. Option B is acceptable if pillars 2 and 3
can be relaxed for low-risk surfaces (smalltalk only). Strict
full-duplex breaks the architecture.

---

## 5. Why cascade is the right choice **now**

### 5.1 Language coverage is decisive

No multilingual S2S production-grade model with **Arabic Gulf** support
exists today. The state of the open-source S2S space is dominated by
English (Moshi, Sesame) and Chinese (GLM-4-Voice, Step-Audio). For UAE
deployment this is a hard blocker.

Cascade does not have this problem. Whisper Large v3 Turbo handles
Arabic Gulf and code-switching adequately. Riva TTS Arabic exists.
Fish-Speech and fine-tuned VITS are viable for custom voice work.

### 5.2 Tool-calling reliability is still an open-source weak spot

Our architecture depends on the LLM producing a structured function
call (`route_to_specialist(department, summary)`) with high
reliability. In the cloud we pinned `gpt-oss-120b` for this because
the Llama family on Groq emitted `<function=...>` as text rather than
using the structured `tool_calls` field — observed in production.

Qwen3-32B is our current candidate for the on-premise router. Until
we validate `tool_choice="required"` (or equivalent constrained
output) behaviour at high concurrency, we will not commit.

If Qwen3 fails this benchmark, we will need a small dedicated router
model with grammar-constrained generation (outlines / lm-format-
enforcer / TensorRT-LLM XGrammar) — still cascade architecture, just
with one more box.

A full-duplex model is in an even worse position: tool calling in S2S
native models is essentially research-grade. There is no production
story for forced function calls in audio-token space.

### 5.3 Operational maturity

Cascade reuses building blocks the industry has been operating for
years:
- ASR streaming → faster-whisper / NVIDIA Riva
- TTS streaming → Riva / Fish-Speech / VITS
- LLM serving → vLLM / TensorRT-LLM + Triton
- WebRTC media → LiveKit
- VAD → Silero / Cobra
- Observability → OpenTelemetry / Prometheus / Grafana

Failure modes, scaling characteristics, capacity planning — well
understood. Engineers know how to debug a misbehaving ASR.

Full-duplex S2S is a research-frontier deployment. Operationally we
would be the first ones running Moshi-class in a regulated UAE
production environment at 2000 concurrent. The on-call story is not
there yet.

### 5.4 The custom orchestration layer is the IP, not the voice model

The work that gives our system its value is the Coordinator + FSM +
two-step routing pattern. That layer is:

- Tested.
- Auditable.
- Tech-agnostic — it cares about events, not about which model
  produced them.

It maps directly onto cascade. It would need partial redesign to
work with a full-duplex model.

Preserving the orchestration layer is itself a strong argument for
cascade.

### 5.5 Latency is achievable

The 200–300 ms target is aggressive on cascade. It is achievable
with disciplined engineering:

- Pipeline overlap (ASR partials drive router LLM prefill).
- Prefix caching on the LLM (system prompt + history reused across
  turns).
- Streaming TTS with sentence-level chunking from LLM token stream.
- Small dedicated router model on a dedicated GPU (~50 ms TTFT).
- Aggressive VAD endpointing tuning.
- FP8 quantization on H200.

Realistic targets: P50 ~ 350 ms, P95 ~ 600 ms, P99 ~ 900 ms.

Achieving sub-300 ms P50 will require the small router model in front
of the main LLM. It is doable.

Full-duplex would deliver lower P50 (~200 ms), but the language and
business-logic blockers above are decisive. The latency gap does not
compensate them.

---

## 6. Why full-duplex (strict) is not viable today

To be specific about what blocks us:

1. **Arabic Gulf**: no production-grade S2S model supports it.
2. **Tool calling in audio-token space**: not a solved problem in
   open source. Our routing pattern depends on it.
3. **Constraining the model**: forcing a full-duplex model to act
   as a pure TTS for substantive responses wastes the model and
   defeats its value proposition.
4. **Operational risk**: deploying a research-frontier S2S model in
   a regulated UAE production environment, at 2000 concurrent, is
   high risk on dimensions (audit trail, debugging, compliance) we
   are not staffed for.
5. **Architectural philosophy**: the four pillars from §2.3 cannot
   all be preserved with strict full-duplex.

Any one of these is a sufficient blocker. Together, the path is
clear.

---

## 7. Half-cascade — module selection and hardware sizing

This section translates the architectural decision into concrete
components for the UAE deployment target (2000 concurrent peak,
Arabic Gulf + English with code-switching, 8 × H200 cluster,
on-premise, open-source publication goal).

The numbers below are **engineering estimates** derived from public
benchmarks. They are a starting point for sizing and POC planning,
not committed values. Every module needs its own load test against
real traffic on our hardware before production commit.

### 7.1 VAD / endpointing

CPU-bound, no GPU needed.

| Option | Latency | Notes | License |
|---|---|---|---|
| **Silero VAD** ([github.com/snakers4/silero-vad](https://github.com/snakers4/silero-vad)) | <5 ms | ~2 MB model, multilingual, mature. Industry standard. | MIT |
| Picovoice Cobra ([picovoice.ai/platform/cobra](https://picovoice.ai/platform/cobra/)) | <10 ms | Better in road noise (drivers in cars on cellular). | Commercial |

**Selection**: Silero VAD as default. Benchmark Cobra against real
car-cabin recordings in the POC. If road-noise false-positive rate
is materially better on Cobra, switch.

### 7.2 ASR streaming

| Model | VRAM | Arabic Gulf | RTF on H200 | License | Notes |
|---|---|---|---|---|---|
| **Whisper Large v3 Turbo** ([huggingface.co/openai/whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo)) | ~3 GB | **Yes, decent** (MSA + dialectal) | ~0.05 | MIT | Default. Robust to code-switching. Served via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) or [whisper-streaming](https://github.com/ufal/whisper_streaming) |
| NVIDIA Canary 1B ([huggingface.co/nvidia/canary-1b-flash](https://huggingface.co/nvidia/canary-1b-flash)) | ~3 GB | Limited (4 EU languages) | ~0.04 | NVIDIA OSL | Disqualified for our case (no Arabic) |
| NVIDIA Parakeet TDT 1.1B ([huggingface.co/nvidia/parakeet-tdt-1.1b](https://huggingface.co/nvidia/parakeet-tdt-1.1b)) | ~3 GB | English only | ~0.02 | NVIDIA OSL | Tempting (2-3× faster) but **no Arabic**; would force language-dependent routing and break on code-switching |
| NVIDIA Riva (FastConformer) | Variable | Multilingual, Arabic available | Optimized for Triton | NVIDIA EULA | Enterprise-grade serving. Plan B if Whisper Turbo proves insufficient for accents |

**Selection**: Whisper Large v3 Turbo via faster-whisper as default.
The code-switching reality in Gulf Arabic is the deciding factor —
language-segregated ASR pipelines fail when a user says *"Habibi
yes, please bring me 50 dirhams of gasoil min al-tank al-asghar"*.

**Decision deferred to POC**: Riva multilingual as a candidate if
Whisper accent handling on UAE dialects falls below acceptance.

### 7.3 TTS streaming

This is the hardest box on the on-premise side. Arabic TTS in open
source is materially behind English.

| Model | Quality | Arabic | First-byte latency | License | Notes |
|---|---|---|---|---|---|
| **NVIDIA Riva** (FastPitch + HiFiGAN) | Good, slightly robotic | Yes | ~80 ms | NVIDIA EULA | Production-grade serving via Triton. Default baseline. |
| **Fish-Speech / OpenAudio** ([github.com/fishaudio/fish-speech](https://github.com/fishaudio/fish-speech)) | Very natural (LLM/codec arch) | Multilingual | ~150-300 ms | **Version-dependent** — verify per checkpoint | Strong candidate IF license clears legal review |
| Custom VITS / fine-tuned voice | High (with effort) | Yes (with dataset) | ~100 ms | Whatever we train | Plan C: 3-6 months of dataset + fine-tuning if neither above clears the MOS bar |
| XTTS-v2 (Coqui) | Good, voice cloning | Yes, variable | ~150-300 ms | **Coqui Public Model License (non-commercial)** | **Disqualified** for commercial deployment. Coqui dissolved Jan 2024 — no licensee to negotiate with. |
| F5-TTS, StyleTTS2, Kokoro, MeloTTS | Various | Limited / no Arabic | Various | Various | Disqualified for production Arabic. Kokoro 82M useful for English fillers only. |
| ElevenLabs cloud | Excellent | Excellent | ~200-400 ms | Commercial cloud | **Discarded** per project requirement (full on-prem). On-prem enterprise tier exists but unverified for our scale and pricing. |

**Selection**: Riva TTS Arabic as production baseline, Fish-Speech as
premium candidate gated on license audit, custom VITS prepared as
fall-back from day 1 of the POC.

**MOS benchmark in week 1 of POC** is mandatory: 5+ native UAE/Gulf
speakers blind-score 30 typical petrol-retail phrases across Riva,
Fish-Speech, and a cloud reference baseline. If all open-source
candidates score MOS < 3.5, we open conversations with a TTS
provider and budget time for fine-tuning.

### 7.4 LLM layer

The on-premise plan uses a two-tier (or three-tier) LLM stack:

| Tier | Model | VRAM (FP8) | Role | Notes |
|---|---|---|---|---|
| **Router** (optional, hot path) | Qwen3-1.7B or Llama 3.2 3B with grammar-constrained output | ~2-3 GB | Force structured function call for every turn (`route_to_specialist`) | Adds reliability + latency cushion. Needed if main LLM fails the tool-calling SLA in POC. |
| **Fast** | **Qwen3-32B** ([huggingface.co/Qwen](https://huggingface.co/Qwen)) | ~32 GB | Direct answers (smalltalk, simple questions, guardrails) | Sweet spot: fits 1 H200, leaves room for KV cache + batching. Best multilingual support including Arabic among open weights. |
| **Premium** | **Qwen3-235B-A22B** (MoE) | ~120 GB | Specialist reasoning, complex tool chains, backend orchestration | MoE → active params 22B → throughput closer to a 22B dense model with knowledge of a 235B. Cascade pattern: fast tries first, premium escalates. |

**Alternatives considered and parked**:

- **Llama 3.3 70B Instruct** — strong general model, but tool-calling
  reliability needs validation per our cloud experience with the
  Llama family.
- **Mistral Large 2** (123B) — excellent tool calling, but 125 GB FP8
  needs 2 H200 with NVLink and Arabic support is weaker than Qwen3.
- **Jais 70B** (G42 / Cerebras, [huggingface.co/inceptionai/jais-family-70b-chat](https://huggingface.co/inceptionai/jais-family-70b-chat))
  — UAE-built, explicitly trained on Gulf Arabic. Strong candidate if
  Qwen3 Arabic falls short, but tool-calling track record is
  unproven and vLLM/TensorRT-LLM ecosystem support is greener.

**Tool-calling validation week 2 of POC**: 200+ prompts against
Qwen3-32B with `tool_choice="required"` (or vLLM outlines /
TensorRT-LLM XGrammar). Pass criterion: ≥99% structured tool-call
emission, ≥99% department enum compliance, zero field
hallucination. If Qwen3 fails, fall back to the dedicated small
router model in front of it.

### 7.5 LLM serving infrastructure

| Stack | When | Why |
|---|---|---|
| **vLLM** ([github.com/vllm-project/vllm](https://github.com/vllm-project/vllm)) | POC fase 1 (validation) | Faster iteration, hot-reload, mature structured-output ecosystem (outlines, lm-format-enforcer). Lower throughput than TensorRT-LLM. |
| **TensorRT-LLM** ([github.com/NVIDIA/TensorRT-LLM](https://github.com/NVIDIA/TensorRT-LLM)) + Triton | POC fase 2 + production | NVIDIA enterprise support, ~20-30% better throughput on H200, native integration with Triton Inference Server. Engine builds slower (10-30 min per model+precision combo), structured-output ecosystem less mature. |

**Selection**: vLLM during POC validation (fast iteration of prompts,
constraints, and model swaps). Migrate to TensorRT-LLM for load
testing and beyond. Production runs on TensorRT-LLM + Triton.

### 7.6 Voice gateway (WebRTC)

Decisive simplification because input is **mobile-app-only** (not
PSTN/SIP):

| Platform | Type | License | Notes |
|---|---|---|---|
| **LiveKit** ([livekit.io](https://livekit.io/)) | WebRTC platform + Voice Agents framework | Apache 2.0 | **Recommended.** On-prem deployable. Native iOS/Android/RN/Flutter SDKs. Built-in TURN/ICE, network handover (4G↔WiFi), adaptive bitrate. Voice Agents SDK ([docs.livekit.io/agents](https://docs.livekit.io/agents/)) maps directly onto our orchestration pattern. |
| Janus Gateway | WebRTC | GPL | Mature, plugin-based. More integration work than LiveKit. |
| mediasoup | WebRTC SFU | ISC | Higher performance, more code glue required. |
| Pion (Go libs) | WebRTC primitives | Apache 2.0 | For building custom. |
| FreeSWITCH | SIP/PBX | MPL | Not needed for our mobile-only entry. Useful only if PSTN is added later. |

**Selection**: LiveKit on-prem. Eliminates the need to build SIP
signaling, codec bridging, AEC server-side, or PSTN integration —
mobile WebRTC handles them natively via OS-level AEC.

### 7.7 Hardware sizing (2 × 8 × H200 active-active, single cluster effective = 8 H200)

These are **engineering estimates**. Validation by load test in POC
fase 2 is mandatory before production commit.

| Component | GPUs | Reasoning |
|---|---|---|
| LLM premium (Qwen3-235B-A22B FP8) | 2 H200 (NVLink) | ~120 GB model + KV cache |
| LLM fast (Qwen3-32B FP8) | 2 H200 (replicated) | ~32 GB + large KV cache for batching, replicated for QPS peaks |
| Router LLM (Qwen3-1.7B FP8, optional) | shared with fast tier | Tiny, runs on the same GPUs |
| ASR (Whisper Turbo via faster-whisper) | 2 H200 | 1500-2000 streams concurrent with dynamic batching |
| TTS (Riva FastPitch+HiFiGAN) | 1 H200 | 1000+ streams concurrent (Triton-optimized) |
| VAD (Silero) | CPU (0 GPU) | <5 ms per chunk |
| Reserve / warmup / spike absorption | 1 H200 | Peak handling and model swap windows |

**This sizes the cluster at 100% in peak conditions.** Mitigations
for peak spikes:

- Pre-cache TTS responses for common phrases (fillers, "let me
  check", confirmations).
- Cascade-down pattern: Qwen3-32B handles the volume, only escalate
  to Qwen3-235B-A22B when the small model lacks confidence.
- Active-active across both 8-GPU clusters at the LB level provides
  failover and headroom.

### 7.8 Variant — audio-multimodal LLM (skipping discrete ASR)

A cascade variant worth flagging explicitly: models like **Qwen2-Audio**
([huggingface.co/Qwen/Qwen2-Audio-7B-Instruct](https://huggingface.co/Qwen/Qwen2-Audio-7B-Instruct),
Apache 2.0) and the newer **Qwen2.5-Omni** family take **raw audio as
input** and emit text directly. They are not speech-to-text models —
they are LLMs with native audio understanding. In a cascade, they can
collapse two stages into one:

```
Standard half-cascade:           VAD → ASR (Whisper) → LLM (Qwen3) → TTS
Audio-aware variant:             VAD → AudioLLM (Qwen2-Audio) → TTS
```

**What this preserves vs strict cascade**:
- **Prosody and emotion survive the routing decision**. The model
  "hears" tone, urgency, anger, hesitation. Routing and content can
  be informed by **how** the user spoke, not only **what** they said.
  In strict cascade, all of this dies at the ASR boundary.
- **Code-switching is handled natively** — the model sees the actual
  audio rather than depending on Whisper to correctly tokenize
  language switches mid-utterance.
- **Fewer modules to operate**: one less box on the hot path.

**Why we are not selecting this for v1**:
- **Latency profile is unclear**. Qwen2-Audio at 7B params processes
  audio in chunks; first-token latency on H200 needs benchmarking.
  Streaming Whisper Turbo + a small router LLM gives us a known
  latency floor. Audio-multimodal LLMs are harder to optimize for
  TTFT today.
- **Arabic Gulf coverage**. Qwen2-Audio handles multilingual but
  Gulf-dialect quality at our bar is unverified. Same MOS-grade
  benchmark needed.
- **Tool-calling reliability is less tested** than text-only Qwen3
  for structured `route_to_specialist` enforcement. The same risk
  concern from §5.2 applies, with less data.
- **TTS is still separate** in the cascade. Prosody continuity from
  input to output is lost at the TTS handoff (unless the TTS also
  receives audio context, which complicates the pipeline). So the
  prosody win is partial — felt in routing/content decisions, not
  in delivery.
- **Throughput per GPU at scale is unknown**. Whisper Turbo +
  Qwen3-32B on H200 has rough capacity estimates we can refine in
  the POC. Qwen2-Audio at 2000 concurrent is research territory.

**Where this sits in our roadmap**:
This is a **strong candidate for simplifying the half-cascade in v2**,
not for replacing it in v1. Recommendation:
1. POC v1 uses the canonical Whisper + Qwen3 stack (known properties).
2. Run a **parallel benchmark track**: Qwen2-Audio / Qwen2.5-Omni
   against the same Arabic Gulf test set used for the Whisper +
   Qwen3 baseline. Measure first-token latency, tool-calling
   reliability, throughput per H200.
3. If the audio-LLM matches or beats the cascade on latency,
   tool-calling, and Arabic quality, **collapse the two stages in
   v2** and drop the discrete ASR module.

Other audio-multimodal LLMs to track:
- **Phi-4-Multimodal-Instruct** (Microsoft, MIT) — includes audio.
- **Qwen2.5-Omni** (Alibaba) — newer, multimodal end-to-end.
- **GPT-4o native audio** (OpenAI, cloud) — quality reference but
  off-limits for on-premise.

### 7.9 Comparison summary — half-cascade vs alternatives

| Dimension | Cascade (selected) | Full-duplex strict | Option B hybrid (future) |
|---|---|---|---|
| First-audio latency P50 (achievable) | ~350 ms | ~200 ms | ~250 ms |
| Arabic Gulf support today | ✅ (Whisper + Riva/Fish-Speech) | ❌ (no production model) | ❌ (no production model) |
| Tool-calling reliability | ✅ (text LLM ecosystem) | ❌ (research-grade in audio-token space) | ✅ (delegated to text LLM) |
| Business-logic separation | ✅ Full | ❌ Fused into the model | ⚠️ Partial (preserved for transactional) |
| Turn-taking control | ✅ Coordinator-owned | ❌ Model-owned | ❌ Model-owned |
| Auditability | ✅ Text logs at every stage | ⚠️ Needs self-transcription audit | ⚠️ Needs constraint-verification audit |
| Operational maturity | ✅ All components widely deployed | ❌ Research-frontier | ❌ Research-frontier |
| Prosody preserved end-to-end | ❌ Lost at ASR | ✅ Native | ✅ Native (in S2S surface layer) |
| Echo cancellation | Browser/OS native AEC + grace gating | Native to model | Native to model |
| Open-source publication friendliness | ✅ Clean architecture | ✅ Single-component but research | ⚠️ Complex hybrid |

The fields where cascade loses (latency P50, prosody) are real but
the gaps are bounded:

- Latency: ~150 ms gap to full-duplex. Closable with disciplined
  optimization (small router, prefix caching, pipeline overlap).
- Prosody: real loss, but our use case (transactional petrol-retail)
  values **accuracy and compliance** over emotional resonance.

The fields where cascade wins (language coverage, tool-calling,
business-logic separation, auditability, operational maturity) are
all hard requirements for this deployment.

---

## 8. When we will revisit (Option B)

Trigger conditions to re-open the conversation:

- A multilingual full-duplex S2S model reaches production grade
  with credible Arabic Gulf support (MOS >= 4.0 from native
  speakers, blind A/B vs current cascade TTS).
- The model exposes a mechanism to inject context mid-conversation
  (system messages, tool results, structured side channel).
- The model supports — or can be wrapped to support — verification
  that hard constraints in the injected content (e.g. exact amounts)
  are honored in the spoken output.
- Independent operators (not just labs) report 6+ months of
  production deployment at scale.

When these conditions hold, we evaluate Option B. The orchestration
layer (Coordinator + FSMs) can be partially preserved: business
logic, routing, and substantive content generation stay; turn-taking
and barge-in delegate to the S2S model.

Until then: cascade.

---

## 9. Open risks we are choosing to accept

These are real and we are entering the project with them visible:

- **TTS Arabic Gulf quality**. Open-source TTS in Arabic is weaker
  than English. ElevenLabs is the quality benchmark and is cloud-only.
  Mitigation: run a MOS benchmark in week one of the POC (Riva vs
  Fish-Speech vs cloud baseline with native speakers). Have a custom
  VITS / fine-tune path budgeted as plan B (3–6 months of dataset
  work).
- **Qwen3 tool calling at scale**. Validate in week two of the POC
  with 200+ varied prompts and `tool_choice="required"` (or
  grammar-constrained equivalent). If it fails at >1% rate, deploy
  a small dedicated router model in front.
- **Latency P95 / P99**. P50 ~ 350 ms is achievable; P95 / P99 are
  the harder targets. Mitigation: aggressive pipeline overlap +
  small router LLM + benchmarking under load before commit.
- **Echo cancellation on mobile**. The native iOS / Android WebRTC
  AEC is robust in well-tuned environments. Drivers in cars on
  cellular are not always well-tuned. Mitigation: aggressive VAD
  threshold tuning, server-side echo loop detection.

---

## 10. Summary table for stakeholders

| Question | Answer |
|---|---|
| Architecture? | Half-cascade (modular pipeline) |
| Why not full-duplex? | No Arabic Gulf S2S production-grade; tool-calling research-frontier; pillars from §2.3 cannot all be preserved |
| Latency target? | P50 ~ 350 ms, P95 ~ 600 ms for direct turns |
| TTS in Arabic? | Riva or Fish-Speech, validated by MOS benchmark week 1 |
| LLM for reasoning? | Qwen3-32B (fast) + Qwen3-235B-A22B (premium), validated for tool calling week 2 |
| Router? | Voice model in cloud → small dedicated LLM with constrained output on-prem (likely needed for latency target) |
| Orchestration? | Existing custom Coordinator + TurnManagerFSM + AgentFSM, portable as-is |
| Mobile transport? | LiveKit on-prem WebRTC |
| Future migration to full-duplex? | Tracked as Option B (separate document); revisit when multilingual S2S production-grade emerges |
| Open risks? | Arabic TTS quality, tool-calling reliability, P99 latency, mobile echo in cars |

---

## 11. References

- `option-b-full-duplex-hybrid.md` — Option B (hybrid) exploratory design
- OpenAI Realtime API — cloud architecture this on-prem design mirrors
- Kyutai Moshi — [github.com/kyutai-labs/moshi](https://github.com/kyutai-labs/moshi)
- GLM-4-Voice — [github.com/THUDM/GLM-4-Voice](https://github.com/THUDM/GLM-4-Voice)
- NVIDIA Riva — [docs.nvidia.com/deeplearning/riva](https://docs.nvidia.com/deeplearning/riva/)
- LiveKit Agents — [docs.livekit.io/agents](https://docs.livekit.io/agents/)
- Qwen3 — [huggingface.co/Qwen](https://huggingface.co/Qwen)
- Whisper Large v3 Turbo — [huggingface.co/openai/whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo)
