## Context

The `Router.classify()` method returns a `RoutingResult` dataclass with all classification fields, but no unified structured log is emitted. Partial logs exist for individual steps (lexicon match, LLM fallback), but there is no single log entry per classification with all calibration-relevant fields. The observability spec requires this for threshold recalibration from production data.

## Goals / Non-Goals

**Goals:**
- Emit one `routing_completed` structured log per `Router.classify()` call with all fields from the observability spec.
- Cover every code path: lexicon short-circuit, short utterance, embedding-only, LLM fallback, and ambiguous Route B.

**Non-Goals:**
- Prometheus metrics for routing (separate concern, already spec'd independently).
- Outcome tracking (barge-in rate, success flag) — requires data from other actors, not available at Router level.
- Persisting logs to a database — structlog + stdout is the current pattern.

## Decisions

### D1: Log at the end of `classify()`, not inside each branch

**Decision:** Add a single `logger.info("routing_completed", ...)` call just before returning from `classify()`. For Route B paths, the log is emitted in `_classify_route_b()` before its return.

**Rationale:** One log per classification, always. Avoids scattered partial logs and ensures every path is covered. The existing partial logs (lexicon match, LLM fallback) remain as debug-level breadcrumbs.

**Alternative considered:** Log only in `classify()` after both Route A and B resolve. Rejected because `_classify_route_b` returns directly, so we'd need to restructure the method or duplicate the log call anyway.

### D2: Extract `router_version` from `ThresholdsConfig`

**Decision:** `ThresholdsConfig.version` already exists (loaded from `thresholds.yaml`). Pass it through as a log field.

**Rationale:** No new state needed. The version is already parsed and available on `self._registry.thresholds.version`.

### D3: Compute margin inline

**Decision:** `margin` (top1 - top2) is already computed in `classify()` as `margin_a` and in `_classify_route_b()` as `margin_b`. Log the relevant one.

**Rationale:** No additional computation needed.

### D4: Log field schema

```
routing_completed:
  router_version: str        # from thresholds.yaml
  language: str              # detected language
  route_a_label: str         # simple/disallowed/out_of_scope/domain
  route_a_score: float       # best score (1.0 for short-circuits)
  route_a_margin: float      # top1 - top2 (0.0 for short-circuits)
  route_b_label: str | None  # sales/billing/support/retention or None
  route_b_score: float | None
  route_b_margin: float | None
  short_circuit: str | None  # "lexicon" / "short_utterance" / None
  fallback_used: bool
```

**Note:** `final_action` (guided_response/tool/clarify/handoff) is determined by the Coordinator/Agent FSM, not the Router. The Router logs classification results; the action log belongs to the Coordinator layer. This is consistent with the separation of concerns.

## Risks / Trade-offs

- **[Low] Log volume**: One log per turn is negligible. Structured logging via structlog keeps it efficient.
- **[Low] Score precision**: Floats logged as-is. For log aggregation, 4 decimal places are sufficient — structlog handles this.
