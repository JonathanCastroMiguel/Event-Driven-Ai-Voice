## Why

The observability spec requires structured logging for every routing decision (router_version, language, route_a_label, route_a_score, route_b_label, route_b_score, margin, fallback_used, final_action). This is critical for threshold calibration with real traffic data. Currently, the Router emits partial logs (lexicon match, short utterance match, LLM fallback result) but has no unified "routing_completed" log entry with all calibration fields. Without this, we cannot recalibrate thresholds from production data.

## What Changes

- Add a single unified `routing_completed` structured log at the end of `Router.classify()` emitting all fields required by the observability spec.
- Include `router_version` from `ThresholdsConfig` in the log.
- Compute and log `margin` (top1 - top2 score) for both Route A and Route B.
- Log `short_circuit` field to distinguish lexicon/short_utterance fast paths.
- Ensure the log is emitted for every code path (lexicon match, short utterance, embedding, LLM fallback).

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `observability`: Implementing the existing "Router calibration logging" requirement (spec lines 34-43) which specifies the structured log fields but has no code yet.

## Impact

- **Code**: `backend/src/routing/router.py` — add unified log call at end of `classify()` and `_classify_route_b()`.
- **Code**: `backend/src/routing/registry.py` — expose `router_version` from `ThresholdsConfig`.
- **Tests**: Unit tests to verify log fields are emitted for each classification path.
- **No API changes, no data model changes, no frontend impact.**
