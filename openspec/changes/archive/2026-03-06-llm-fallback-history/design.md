## Context

The LLM fallback classifier fires when embedding-based routing is ambiguous (low confidence + tight margin). Currently, `RoutingContextBuilder.build()` produces a flat single-turn string for the LLM: `"language=es; previous_turn: {prev_text}"`. The LLM receives this as a `Context:` line in the classification prompt alongside the current user text.

The embedding enrichment layer (`enriched_text`) concatenates only the most recent turn for short texts — this is intentional since embeddings can't reason about conversation structure. The LLM, however, can natively reason about multi-turn flow, so it benefits from seeing 2-3 prior turns.

Current flow:
```
ConversationBuffer → RoutingContextBuilder.build() → RoutingContext.llm_context (1 turn, flat string)
→ Router.classify(llm_context=...) → _llm_classify_a/b(llm_context=...) → LLMFallbackClient.classify(context=...)
→ _build_classification_prompt(context=...) → "Context: language=es; previous_turn: ..."
```

## Goals / Non-Goals

**Goals:**
- Give the LLM fallback 2-3 prior turns of structured conversation history
- Keep embedding enrichment layer unchanged (1 turn, `routing_context_window=1`)
- Add a separate `llm_context_window` setting so the two layers are independently tunable
- Maintain backward compatibility: when buffer has 0-1 entries, output is equivalent

**Non-Goals:**
- Changing the embedding enrichment strategy (stays single-turn)
- Changing the `classify()` method signature (`llm_context` remains `str | None`)
- Adding conversation history to the system prompt of the LLM call (keep it in the user prompt `Context:` block)
- Modifying how specialists receive conversation context (separate concern)

## Decisions

### D1: Separate `llm_context_window` setting (default: 3)

**Decision:** Add `llm_context_window: int = 3` to Settings, independent of `routing_context_window` (stays 1).

**Rationale:** Embeddings and LLMs have fundamentally different context capabilities. Embeddings work best with short concatenated text (1 turn). LLMs can reason about conversation structure (2-3 turns). Coupling them to the same window would degrade one or the other.

**Alternative considered:** Reuse `routing_context_window` for both. Rejected because the optimal window sizes differ by design.

### D2: Structured turn format in `llm_context`

**Decision:** Format `llm_context` as a labeled multi-turn string:
```
language=es
turn[-3] user: tengo un problema con mi factura
turn[-3] route: billing
turn[-2] user: no me llega el recibo
turn[-2] route: billing
turn[-1] user: y ahora tampoco puedo pagar
turn[-1] route: billing
```

**Rationale:** The LLM needs to see the progression of conversation, not just raw text. Including the route label from each prior turn helps the LLM understand the conversation domain trajectory. The turn numbering (`[-3]`, `[-2]`, `[-1]`) makes recency explicit.

**Alternative considered:** Pass turns as separate messages in the LLM API call. Rejected because the LLM prompt is already structured as system + user, and injecting history as additional messages would require changing the API call structure. A structured `Context:` block in the user prompt is simpler and equally effective for classification.

### D3: `RoutingContextBuilder` produces both formats in one call

**Decision:** `build()` continues to return a single `RoutingContext` with both `enriched_text` (1 turn for embeddings) and `llm_context` (N turns for LLM). The builder accepts both `context_window` (for embedding enrichment) and `llm_context_window` (for LLM context).

**Rationale:** Keeps the interface simple — the Coordinator calls `build()` once and gets both outputs. No need for separate builder instances or calls.

### D4: `_build_classification_prompt()` unchanged in structure

**Decision:** The prompt function still receives `context: str` and inserts it as `"Context: {context}"`. The richer content comes from the caller, not from prompt restructuring.

**Rationale:** Minimal change. The `llm_context` string is already well-structured; the prompt function doesn't need to parse or reformat it.

## Risks / Trade-offs

- **[Prompt length]** → 3 prior turns add ~200-400 chars to the classification prompt. Well within the 100-token `max_tokens` budget for the response, and minimal impact on the ~4K input context of gpt-4o-mini. Mitigated by capping at `llm_context_window=3`.
- **[Latency]** → No additional latency. The context is built from the in-memory buffer, and the LLM call payload is negligibly larger.
- **[Route label leakage]** → Including prior route labels in the context could bias the LLM toward the same label. This is actually desirable for follow-up classification (conversation continuity). If it becomes an issue, the route label can be removed from the format with a config flag.
