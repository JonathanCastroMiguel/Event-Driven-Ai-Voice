## Context

The router classifies each turn in isolation — `Router.classify(text, language)` receives only the current utterance. This works well for self-contained phrases but fails on short follow-ups like "de este mes" after "tengo un problema con mi factura". The `ConversationBuffer` already stores completed turns for prompt construction, but routing decisions happen before history is consulted.

**Current call flow:**
1. `Coordinator._on_human_turn_finalized()` receives `text`
2. Calls `Router.classify(text, language)` — no history context
3. FSM produces routing event
4. Prompt construction injects `ConversationBuffer.format_messages()` — history available here, but too late for routing

**Key constraint:** The embedding engine is not an LLM. It produces a single vector per input string. It cannot reason about conversational continuity. Concatenation is the only way to give it richer signal.

## Goals / Non-Goals

**Goals:**
- Improve classification accuracy for short follow-up utterances by enriching the text before embedding classification
- Provide conversation context to the LLM fallback when triggered by ambiguous scores
- Keep the original `user_text` intact for prompt construction, buffer storage, and logging
- Make enrichment configurable (threshold, context window) and off by default for zero-risk rollout

**Non-Goals:**
- Changing embedding centroids or retraining models
- Modifying the classification pipeline order (lexicon -> short utterance -> Route A -> Route B -> LLM fallback)
- Providing context to short utterance or lexicon checks (these are exact-match and should only match the literal input)
- Supporting multi-turn context windows > 1 (future work)

## Decisions

### D1: New `routing/context.py` module as single entry point

**Decision:** Create a `RoutingContextBuilder` class that reads from `ConversationBuffer` and produces two outputs: (a) enriched text for embeddings and (b) context string for LLM fallback.

**Why:** Centralizes the enrichment logic in one place. The Coordinator calls `build()` once and passes both outputs downstream. No scattered conditionals across router, coordinator, and fallback.

**Alternative considered:** Passing the `ConversationBuffer` directly to `Router.classify()`. Rejected because it couples the router to conversation state, breaking its current stateless design.

### D2: Enrichment only for short text (Layer 1)

**Decision:** When `len(user_text) < routing_short_text_chars` (default: 20) AND the buffer is non-empty, prepend the previous turn's `user_text` to form the embedding input: `"{prev_text}. {current_text}"`.

**Why:**
- Short texts produce weak/ambiguous embeddings — the cosine similarity loses signal
- Long, self-contained utterances already embed well and don't need enrichment
- Concatenation creates a richer embedding that captures the semantic blend of both turns
- A period separator keeps the sentences grammatically sensible for the embedding model

**Alternative considered:** Always concatenating regardless of length. Rejected because long utterances would get diluted by irrelevant prior context, potentially shifting classifications.

### D3: LLM fallback receives conversation context (Layer 2)

**Decision:** When the LLM fallback is invoked (ambiguous embedding scores), include the previous turn's `user_text` in the `context` parameter already accepted by `LLMFallbackClient.classify()`.

**Why:** The LLM can reason about conversational flow natively — "the user said X, now says Y, therefore the intent is Z". The existing `context` parameter (`context: str = ""`) already supports this without API changes. The context string will be formatted as: `"language={lang}; previous_turn: {prev_text}"`.

**Alternative considered:** Sending full conversation history to the LLM. Rejected because it adds latency (more tokens) and the fallback must stay within 2s budget. One prior turn is sufficient for follow-up disambiguation.

### D4: Router.classify() gains optional `enriched_text` and `llm_context` parameters

**Decision:** Add two optional parameters to `Router.classify()`:
- `enriched_text: str | None = None` — used for embedding classification instead of `text` when provided
- `llm_context: str | None = None` — passed to LLM fallback's `context` parameter when provided

The `text` parameter remains the source of truth for lexicon check, short utterance check, and the RoutingResult.

**Why:** Minimal change to the router interface. Both parameters are optional with backward-compatible defaults. The router doesn't need to know about the buffer or why the text was enriched.

**Alternative considered:** Having the Coordinator call `Router.classify()` with the enriched text as the main `text` parameter. Rejected because lexicon and short-utterance checks must operate on the original text (e.g., "sí" must match the short utterance registry, not "tengo un problema con mi factura. sí").

### D5: Configuration via Settings

**Decision:** Add two new settings to `config.py`:
- `routing_context_window: int = 1` — number of prior turns to consider (currently only 1 supported)
- `routing_short_text_chars: int = 20` — threshold below which embedding text is enriched

**Why:** Allows tuning without code changes. Default values are conservative. Setting `routing_short_text_chars = 0` effectively disables Layer 1.

## Risks / Trade-offs

**[Embedding distance shift]** Concatenated text produces a different embedding than either turn alone — a "semantic average". This may shift classifications for edge cases where the prior turn is from a different domain than the current one.
-> Mitigation: Only enrich texts < 20 chars. At this length, the original embedding is already weak/ambiguous, so the enriched version is likely an improvement. The LLM fallback provides a safety net.

**[Stale context after barge-in]** If a user barge-ins and the cancelled turn was not appended to the buffer, the "previous turn" may be from 2+ turns ago.
-> Mitigation: This is correct behavior — cancelled turns should not influence routing. The buffer already excludes cancelled turns (Coordinator only appends after voice start).

**[Concatenation breaks lexicon/short-utterance]** If enriched text were used for lexicon or short-utterance checks, matches would fail (e.g., "idiota" wouldn't match in "mi factura. idiota").
-> Mitigation: D4 explicitly keeps the original `text` for lexicon and short-utterance checks. Only embedding classification uses `enriched_text`.

**[LLM fallback latency]** Adding previous turn text to the LLM prompt slightly increases token count (~20 tokens).
-> Mitigation: Negligible impact. The fallback prompt is already short (~100 tokens). Well within 2s budget.
